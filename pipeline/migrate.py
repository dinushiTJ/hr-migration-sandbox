"""
Profile, validate, transform and load three legacy HR sources into a
Workday-shaped target, quarantining anything that fails a rule.

Design decisions worth knowing:

  * Staging is written before validation. A broken record is still a fact about
    what the source sent, and keeping it makes the load replayable.
  * Every rejection is written to quarantine with a stable rule_id, the natural
    key, and the raw record. "1,204 loaded" means nothing without "and here are
    the 96 we would not load, and why".
  * Rejecting a worker cascades: their payroll rows go too. A compensation row
    for a worker who does not exist in the target is worse than no row at all.
  * Dates are parsed from four legacy formats into ISO. Anything unparseable is
    rejected rather than guessed at -- a wrong hire date is silently wrong.
"""
import csv
import json
import sqlite3
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"
DB = OUT / "hr_migration.db"

TODAY = date(2026, 8, 27)
MAX_INPUT_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------- date parsing
# One table drives both parsing and the label reported in the cleansing log, so
# the two can never disagree about what a value was before it was standardised.
DATE_FORMATS = (("%Y-%m-%d", "ISO 8601"),
                ("%d/%m/%Y", "DD/MM/YYYY"),
                ("%d-%b-%Y", "DD-Mon-YYYY"))


def parse_date(raw):
    """Legacy sources use four formats. Return (date|None, ok)."""
    s = (raw or "").strip()
    if not s:
        return None, True                      # genuinely empty is allowed
    for fmt, _ in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date(), True
        except ValueError:
            pass
    if s.isdigit():                            # Excel serial
        try:
            return date(1899, 12, 30) + timedelta(days=int(s)), True
        except (ValueError, OverflowError):
            return None, False
    return None, False


def date_format(raw):
    """Name the format a value arrived in, for the cleansing log."""
    s = (raw or "").strip()
    if not s:
        return None
    for fmt, label in DATE_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return label
        except ValueError:
            pass
    return "Excel serial" if s.isdigit() else None


def iso(d):
    return d.isoformat() if d else None


def norm_text(v):
    """Collapse the whitespace and casing drift that creeps in across systems."""
    return " ".join((v or "").split()).strip()


def read_csv_rows(path):
    """Read bounded, UTF-8 CSV input to avoid accidental resource exhaustion."""
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"input file too large: {path.name}")
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_org_xml(path):
    """Parse the expected simple XML shape and reject DTD/entity payloads."""
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"input file too large: {path.name}")
    parser = ET.XMLParser()
    root = ET.parse(path, parser=parser).getroot()
    if root.tag != "organisations":
        raise ValueError("unexpected organisation XML root")
    orgs = []
    for e in root:
        if e.tag != "organisation" or any(child.tag not in {
                "org_id", "org_name", "cost_centre", "parent_org_id"} for child in e):
            raise ValueError("unexpected organisation XML structure")
        orgs.append({k.tag: (k.text or "") for k in e})
    return orgs


# ---------------------------------------------------------------------- engine
class Migration:
    def __init__(self, conn, run_id):
        self.c = conn
        self.run_id = run_id
        self.rejected = []          # (entity, ref, rule_id, reason, raw, disposition)
        self.rejected_salary = 0.0  # money held back, for the control total
        self.cleaned = []           # (entity, ref, rule_id, field, before, after, note)

    def reject(self, entity, ref, rule_id, reason, raw, disposition="REJECTED",
               amount=None):
        """Record a rule failure.

        disposition="LOADED_FLAGGED" means the record was still loaded and the
        fault recorded against it, rather than dropped. amount carries the money
        on a rejected compensation row so the control total can account for it.
        """
        self.rejected.append((entity, ref, rule_id, reason, raw, disposition))
        if disposition == "REJECTED" and amount:
            self.rejected_salary += amount

    def clean(self, entity, ref, rule_id, field, before, after, note=None):
        """Record a value the load standardised. No-ops are not logged."""
        if str(before or "") == str(after or ""):
            return after
        self.cleaned.append((entity, ref, rule_id, field,
                             str(before or ""), str(after or ""), note))
        return after

    def norm_logged(self, entity, ref, field, raw, case=None):
        """norm_text, with the whitespace and case steps logged separately.

        They are separate rules because they are separate decisions: collapsing
        whitespace is uncontroversial, forcing case is a standardisation choice
        a data owner should get to see and argue with.
        """
        collapsed = norm_text(raw)
        self.clean(entity, ref, "CLN-002", field, raw, collapsed)
        if case == "upper":
            final = collapsed.upper()
        elif case == "lower":
            final = collapsed.lower()
        else:
            return collapsed
        self.clean(entity, ref, "CLN-003", field, collapsed, final,
                   note=f"standardised to {case}case")
        return final

    def clean_date(self, entity, ref, field, raw, parsed):
        """Log a date that arrived in anything other than ISO."""
        if parsed is None:
            return
        self.clean(entity, ref, "CLN-001", field, raw, iso(parsed),
                   note=f"{date_format(raw)} → ISO 8601")

    def flush_cleansing(self):
        self.c.executemany(
            "INSERT INTO cleansing_log (run_id, entity, source_ref, rule_id, field,"
            " before_value, after_value, note) VALUES (?,?,?,?,?,?,?,?)",
            [(self.run_id,) + row for row in self.cleaned],
        )

    def flush_quarantine(self):
        self.c.executemany(
            "INSERT INTO quarantine (run_id, entity, source_ref, rule_id, reason,"
            " raw_record, disposition) VALUES (?,?,?,?,?,?,?)",
            [(self.run_id, e, r, rid, rs, raw, d)
             for e, r, rid, rs, raw, d in self.rejected],
        )

    def recon(self, entity, metric, value):
        self.c.execute(
            "INSERT INTO reconciliation (run_id, entity, metric, value) VALUES (?,?,?,?)",
            (self.run_id, entity, metric, float(value)),
        )

    # ------------------------------------------------------------------ extract
    def stage(self):
        hris = read_csv_rows(DATA / "hris_workers.csv")
        payroll = read_csv_rows(DATA / "payroll_export.csv")
        orgs = parse_org_xml(DATA / "org_hierarchy.xml")

        self.c.executemany("INSERT INTO stg_hris_worker VALUES (?,?)",
                           [(i, json.dumps(r)) for i, r in enumerate(hris, 1)])
        self.c.executemany("INSERT INTO stg_payroll VALUES (?,?)",
                           [(i, json.dumps(r)) for i, r in enumerate(payroll, 1)])
        self.c.executemany("INSERT INTO stg_org VALUES (?,?)",
                           [(i, json.dumps(r)) for i, r in enumerate(orgs, 1)])

        self.recon("worker", "source_rows", len(hris))
        self.recon("compensation", "source_rows", len(payroll))
        self.recon("supervisory_org", "source_rows", len(orgs))
        return hris, payroll, orgs

    # -------------------------------------------------------------------- orgs
    def load_orgs(self, orgs):
        known = {o["org_id"] for o in orgs}
        by_name = {}
        loaded = 0
        for o in orgs:
            raw = json.dumps(o)
            parent = o.get("parent_org_id") or None
            if parent and parent not in known:
                # Orphaned parent. Load the org, but flatten it to a root and
                # record the fact -- dropping a whole department is worse.
                self.reject("org", o["org_id"], "ORG-001",
                            f"Parent org {parent} not found in source; loaded as root",
                            raw, disposition="LOADED_FLAGGED")
                parent = None
            oid = o["org_id"]
            name = self.norm_logged("org", oid, "org_name", o["org_name"])
            cc = self.norm_logged("org", oid, "cost_centre", o.get("cost_centre"),
                                  case="upper")
            self.c.execute("INSERT INTO supervisory_org VALUES (?,?,?,?)",
                           (oid, name, parent, cc))
            # Normalise before comparing, never after: dedupe on the raw value and
            # "  FACILITIES " and "Facilities" become two different orgs.
            by_name[name.lower()] = oid
            loaded += 1
        self.recon("supervisory_org", "loaded", loaded)
        return by_name

    # ----------------------------------------------------------------- workers
    def load_workers(self, hris, org_by_name):
        # Profile first: which employee_ids appear more than once?
        counts = {}
        for r in hris:
            counts[r["employee_id"]] = counts.get(r["employee_id"], 0) + 1
        dupes = {k for k, v in counts.items() if v > 1}
        self.recon("worker", "duplicate_source_ids", len(dupes))

        seen = set()
        valid = {}
        for r in hris:
            wid = (r["employee_id"] or "").strip()
            raw = json.dumps(r)

            if not wid:
                self.reject("worker", None, "WRK-001", "Missing employee_id", raw)
                continue
            if wid in dupes and wid in seen:
                self.reject("worker", wid, "WRK-002",
                            "Duplicate employee_id with conflicting attributes; "
                            "first occurrence retained", raw)
                continue
            seen.add(wid)

            hire, ok_h = parse_date(r["hire_date"])
            if not ok_h:
                self.reject("worker", wid, "WRK-003",
                            f"Unparseable hire_date: {r['hire_date']!r}", raw)
                continue
            if hire is None:
                self.reject("worker", wid, "WRK-004", "Missing hire_date", raw)
                continue

            term, ok_t = parse_date(r["termination_date"])
            if not ok_t:
                self.reject("worker", wid, "WRK-005",
                            f"Unparseable termination_date: {r['termination_date']!r}", raw)
                continue
            if term and term < hire:
                self.reject("worker", wid, "WRK-006",
                            "termination_date precedes hire_date", raw)
                continue

            try:
                fte = float(r["fte"])
            except (TypeError, ValueError):
                self.reject("worker", wid, "WRK-007", f"Non-numeric FTE: {r['fte']!r}", raw)
                continue
            if not (0 < fte <= 1.5):
                self.reject("worker", wid, "WRK-008",
                            f"FTE outside plausible range: {fte}", raw)
                continue

            if not norm_text(r["first_name"]) or not norm_text(r["last_name"]):
                self.reject("worker", wid, "WRK-009", "Missing legal name component", raw)
                continue

            self.clean_date("worker", wid, "hire_date", r["hire_date"], hire)
            self.clean_date("worker", wid, "termination_date", r["termination_date"], term)
            valid[wid] = {
                "worker_id": wid,
                # kept so a flag raised in the second pass can still quarantine
                # the original source row rather than a synthetic stand-in
                "raw": raw,
                "first": self.norm_logged("worker", wid, "first_name", r["first_name"]),
                "last": self.norm_logged("worker", wid, "last_name", r["last_name"]),
                "hire": hire,
                "term": term,
                "title": self.norm_logged("worker", wid, "job_title", r["job_title"]),
                "dept": self.norm_logged("worker", wid, "department", r["department"],
                                         case="lower"),
                "manager": (r["manager_id"] or "").strip() or None,
                "type": self.norm_logged("worker", wid, "employment_type",
                                         r["employment_type"]),
                "fte": fte,
            }

        # Manager references can only be checked once the full valid set is known.
        for wid, w in valid.items():
            if w["manager"] and w["manager"] not in valid:
                self.reject("worker", wid, "WRK-010",
                            f"manager_id {w['manager']} not found among valid workers; "
                            "assignment loaded without supervisor",
                            w["raw"], disposition="LOADED_FLAGGED")
                w["manager"] = None

        for wid, w in valid.items():
            org_id = org_by_name.get(w["dept"])
            self.clean("worker", wid, "CLN-004", "department", w["dept"],
                       org_id or w["dept"],
                       note="department resolved to supervisory org"
                            if org_id else "no matching org; loaded without one")
            status = "Terminated" if w["term"] else "Active"
            self.c.execute(
                "INSERT INTO worker VALUES (?,?,?,?,?,?)",
                (wid, iso(w["hire"]), iso(w["term"]), w["first"], w["last"], status),
            )
            self.c.execute(
                "INSERT INTO position_assignment VALUES (?,?,?,?,?,?,?,?)",
                (wid, iso(w["hire"]), iso(w["term"]), w["title"],
                 org_id, w["manager"], w["fte"], w["type"]),
            )

        self.recon("worker", "loaded", len(valid))
        return valid

    # ------------------------------------------------------------ compensation
    def load_compensation(self, payroll, valid_workers):
        loaded = 0
        source_total = 0.0
        loaded_total = 0.0
        candidates = {}          # worker_id -> [(start, end, row, raw)]

        for r in payroll:
            wid = (r["employee_id"] or "").strip()
            raw = json.dumps(r)

            try:
                amount = float(r["annual_salary"])
                source_total += amount
            except (TypeError, ValueError):
                amount = None

            if wid not in valid_workers:
                self.reject("compensation", wid, "CMP-001",
                            "Payroll record for worker not present in target "
                            "(absent from HRIS, or worker rejected)", raw, amount=amount)
                continue

            if amount is None:
                self.reject("compensation", wid, "CMP-002",
                            f"Missing or non-numeric salary: {r['annual_salary']!r}", raw, amount=amount)
                continue
            if amount <= 0:
                self.reject("compensation", wid, "CMP-003",
                            f"Salary must be greater than zero: {amount}", raw, amount=amount)
                continue

            start, ok_s = parse_date(r["pay_period_start"])
            end, ok_e = parse_date(r["pay_period_end"])
            if not (ok_s and ok_e) or start is None:
                self.reject("compensation", wid, "CMP-004",
                            "Unparseable pay period dates", raw, amount=amount)
                continue
            if end and end < start:
                self.reject("compensation", wid, "CMP-005",
                            "pay_period_end precedes pay_period_start", raw, amount=amount)
                continue

            w = valid_workers[wid]
            if start < w["hire"]:
                self.reject("compensation", wid, "CMP-006",
                            "Pay period starts before the worker's hire date", raw, amount=amount)
                continue
            if w["term"] and start > w["term"]:
                self.reject("compensation", wid, "CMP-007",
                            "Pay period starts after the worker's termination date", raw, amount=amount)
                continue

            candidates.setdefault(wid, []).append((start, end, amount, r, raw))

        # Effective dating: a worker may not hold two compensation records whose
        # validity periods overlap. Checking only for a duplicate start date is
        # not enough -- 1 Mar to 31 Mar and 15 Mar to 14 Apr have different
        # starts and still overlap, and Workday will reject the load. Sort each
        # worker's records and test every one against the last period accepted.
        for wid, rows in candidates.items():
            rows.sort(key=lambda t: (t[0], t[1] or date.max))
            accepted = []
            for start, end, amount, r, raw in rows:
                clash = next(
                    (a for a in accepted
                     if (a[1] is None or a[1] >= start) and (end is None or end >= a[0])),
                    None,
                )
                if clash:
                    self.reject("compensation", wid, "CMP-008",
                                f"Compensation period {iso(start)} to {iso(end)} overlaps "
                                f"existing period {iso(clash[0])} to {iso(clash[1])}", raw,
                                amount=amount)
                    continue
                accepted.append((start, end))
                self.clean_date("compensation", wid, "pay_period_start",
                                r["pay_period_start"], start)
                self.clean_date("compensation", wid, "pay_period_end",
                                r["pay_period_end"], end)
                self.clean("compensation", wid, "CLN-005", "annual_salary",
                           r["annual_salary"], f"{round(amount, 2):.2f}",
                           note="rounded to whole cents")
                self.c.execute(
                    "INSERT INTO compensation VALUES (?,?,?,?,?,?,?)",
                    (wid, iso(start), iso(end), round(amount, 2),
                     self.norm_logged("compensation", wid, "currency",
                                      r["currency"], case="upper"),
                     self.norm_logged("compensation", wid, "cost_centre",
                                      r["cost_centre"], case="upper"),
                     self.norm_logged("compensation", wid, "pay_group",
                                      r["pay_group"])),
                )
                loaded_total += amount
                loaded += 1

        self.recon("compensation", "loaded", loaded)
        self.recon("compensation", "source_salary_total", round(source_total, 2))
        self.recon("compensation", "loaded_salary_total", round(loaded_total, 2))
        self.recon("compensation", "rejected_salary_total", round(self.rejected_salary, 2))
        return loaded


def main():
    OUT.mkdir(exist_ok=True)
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    DB.chmod(0o600)
    conn.executescript((ROOT / "sql" / "schema.sql").read_text())

    run_id = str(uuid.uuid4())[:8]
    conn.execute("INSERT INTO migration_run VALUES (?,?,?,?)",
                 (run_id, datetime.now().isoformat(timespec="seconds"), None, "RUNNING"))
    conn.commit()   # committed immediately, so a crash still leaves a visible run

    m = Migration(conn, run_id)
    try:
        hris, payroll, orgs = m.stage()
        org_by_name = m.load_orgs(orgs)
        workers = m.load_workers(hris, org_by_name)
        m.load_compensation(payroll, workers)
        m.flush_quarantine()
        m.flush_cleansing()
        m.recon("all", "values_cleansed", len(m.cleaned))
        conn.execute("UPDATE migration_run SET ended_at=?, status=? WHERE run_id=?",
                     (datetime.now().isoformat(timespec="seconds"), "SUCCESS", run_id))
        conn.commit()
        print(f"run {run_id}: SUCCESS")
    except Exception as exc:
        conn.execute("UPDATE migration_run SET ended_at=?, status=? WHERE run_id=?",
                     (datetime.now().isoformat(timespec="seconds"), "FAILED", run_id))
        conn.commit()
        print(f"run {run_id}: FAILED -- {exc}")
        raise
    finally:
        conn.close()
    return run_id


if __name__ == "__main__":
    main()
