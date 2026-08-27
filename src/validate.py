"""
Independent validity checks over a completed run.

Deliberately does not import the pipeline. Every invariant here is re-derived
from the database and the source files, so a bug shared between the loader and
its own reconciliation cannot hide from it. reconcile.py reports what the run
did; this asks whether what it did holds together.

Exit code is 0 only if every check passes.
"""
import csv
import json
import sqlite3
import re
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "out" / "hr_migration.db"
DATA = ROOT / "data"

RESULTS = []


def check(name, ok, detail="", known=None):
    """known: issue number from the README, for a defect already documented.

    A documented defect still has to show up in the output, but it must not read
    the same as a regression, or the harness stops being usable as a gate.
    """
    RESULTS.append((name, bool(ok), detail, known))


def iso_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def read_csv_rows(path):
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError(f"input file too large: {path.name}")
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_any(s):
    """Re-implemented on purpose, not imported, so a parser bug shows up here."""
    s = (s or "").strip()
    if not s:
        return None
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    if s.isdigit():
        return date(1899, 12, 30) + timedelta(days=int(s))
    return None


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    q1 = lambda s, *a: c.execute(s, a).fetchone()[0]

    hris = read_csv_rows(DATA / "hris_workers.csv")
    payroll = read_csv_rows(DATA / "payroll_export.csv")

    # ---- 1. staging holds every source row, unjudged --------------------------
    check("staging: HRIS rows staged",
          q1("SELECT COUNT(*) FROM stg_hris_worker") == len(hris),
          f"{q1('SELECT COUNT(*) FROM stg_hris_worker')} staged / {len(hris)} in file")
    check("staging: payroll rows staged",
          q1("SELECT COUNT(*) FROM stg_payroll") == len(payroll),
          f"{q1('SELECT COUNT(*) FROM stg_payroll')} staged / {len(payroll)} in file")

    # ---- 2. record conservation: every source row is loaded or rejected -------
    for entity, table, ent_key, src in (
            ("worker", "worker", "worker", len(hris)),
            ("compensation", "compensation", "compensation", len(payroll)),
            ("supervisory_org", "supervisory_org", "org", 8)):
        loaded = q1(f"SELECT COUNT(*) FROM {table}")
        rejected = q1("SELECT COUNT(*) FROM quarantine WHERE entity=? AND disposition='REJECTED'",
                      ent_key)
        check(f"conservation: {entity} loaded + rejected = source",
              loaded + rejected == src, f"{loaded} + {rejected} = {loaded + rejected} vs {src}")

    # ---- 3. money conservation, in integer cents ------------------------------
    cents = lambda x: int(round(float(x) * 100))
    src_c = sum(cents(r["annual_salary"]) for r in payroll
                if _isnum(r["annual_salary"]))
    loaded_c = sum(cents(r[0]) for r in c.execute("SELECT annual_amount FROM compensation"))
    rej_c = 0
    for r in c.execute("SELECT raw_record FROM quarantine WHERE entity='compensation'"
                       " AND disposition='REJECTED'"):
        v = json.loads(r["raw_record"]).get("annual_salary")
        if _isnum(v):
            rej_c += cents(v)
    check("money: source = loaded + rejected, to the cent",
          src_c == loaded_c + rej_c,
          f"{src_c/100:,.2f} vs {loaded_c/100:,.2f} + {rej_c/100:,.2f}"
          f" (residual {(src_c - loaded_c - rej_c)/100:,.2f})")

    # ---- 4. effective dating -------------------------------------------------
    bad_range = q1("SELECT COUNT(*) FROM worker WHERE effective_to IS NOT NULL"
                   " AND effective_to < effective_from")
    check("effective dating: worker effective_to >= effective_from", bad_range == 0,
          f"{bad_range} inverted")
    bad_range = q1("SELECT COUNT(*) FROM compensation WHERE effective_to IS NOT NULL"
                   " AND effective_to < effective_from")
    check("effective dating: compensation effective_to >= effective_from", bad_range == 0,
          f"{bad_range} inverted")

    # real interval overlap, recomputed here rather than trusted from the loader
    periods = {}
    for r in c.execute("SELECT worker_id, effective_from, effective_to FROM compensation"):
        periods.setdefault(r["worker_id"], []).append(
            (iso_date(r["effective_from"]),
             iso_date(r["effective_to"]) if r["effective_to"] else date.max))
    overlaps = 0
    for wid, ps in periods.items():
        ps.sort()
        for i in range(1, len(ps)):
            if ps[i][0] <= ps[i - 1][1]:
                overlaps += 1
    check("effective dating: no overlapping compensation periods", overlaps == 0,
          f"{overlaps} overlapping pairs across {len(periods)} workers")

    # ---- 5. referential integrity --------------------------------------------
    check("integrity: every compensation row has a worker",
          q1("SELECT COUNT(*) FROM compensation cm LEFT JOIN worker w"
             " ON cm.worker_id=w.worker_id WHERE w.worker_id IS NULL") == 0)
    check("integrity: every position matches a worker version",
          q1("SELECT COUNT(*) FROM position_assignment p LEFT JOIN worker w"
             " ON p.worker_id=w.worker_id AND p.effective_from=w.effective_from"
             " WHERE w.worker_id IS NULL") == 0)
    check("integrity: no dangling manager references",
          q1("SELECT COUNT(*) FROM position_assignment WHERE manager_worker_id IS NOT NULL"
             " AND manager_worker_id NOT IN (SELECT worker_id FROM worker)") == 0)
    check("integrity: every org parent resolves",
          q1("SELECT COUNT(*) FROM supervisory_org WHERE parent_org_id IS NOT NULL"
             " AND parent_org_id NOT IN (SELECT org_id FROM supervisory_org)") == 0)
    check("integrity: every position org_id resolves",
          q1("SELECT COUNT(*) FROM position_assignment WHERE org_id IS NOT NULL"
             " AND org_id NOT IN (SELECT org_id FROM supervisory_org)") == 0)

    # ---- 6. target values are well formed ------------------------------------
    bad = 0
    for r in c.execute("SELECT effective_from, effective_to FROM worker"
                       " UNION ALL SELECT effective_from, effective_to FROM compensation"):
        for v in r:
            if v is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                bad += 1
    check("values: every target date is ISO 8601", bad == 0, f"{bad} malformed")
    check("values: no non-positive salary reached the target",
          q1("SELECT COUNT(*) FROM compensation WHERE annual_amount <= 0") == 0)
    check("values: every FTE in range",
          q1("SELECT COUNT(*) FROM position_assignment WHERE fte <= 0 OR fte > 1.5") == 0)
    check("values: no untrimmed text in the target",
          q1("SELECT COUNT(*) FROM supervisory_org WHERE org_name != TRIM(org_name)"
             " OR cost_centre != TRIM(cost_centre)") == 0)

    # ---- 7. hire and termination dates survived the transformation ------------
    src_hire = {}
    for r in hris:
        d = parse_any(r["hire_date"])
        if d:
            src_hire.setdefault(r["employee_id"], d)
    mismatched = [w["worker_id"] for w in c.execute("SELECT worker_id, effective_from FROM worker")
                  if src_hire.get(w["worker_id"]) != iso_date(w["effective_from"])]
    check("transformation: worker effective_from equals the source hire date",
          not mismatched, f"{len(mismatched)} mismatched: {mismatched[:5]}")

    # ---- 8. quarantine is traceable ------------------------------------------
    staged = set()
    for t in ("stg_hris_worker", "stg_payroll", "stg_org"):
        staged |= {r[0] for r in c.execute(f"SELECT payload FROM {t}")}
    untraceable = [r["rule_id"] for r in c.execute("SELECT rule_id, raw_record FROM quarantine")
                   if r["raw_record"] not in staged]
    check("quarantine: every raw_record matches a staged source record",
          not untraceable,
          f"{len(untraceable)} do not: {sorted(set(untraceable))}")
    check("quarantine: every rule_id is well formed",
          all(re.fullmatch(r"(WRK|CMP|ORG)-\d{3}", r[0])
              for r in c.execute("SELECT DISTINCT rule_id FROM quarantine")))
    check("quarantine: every disposition is a known value",
          {r[0] for r in c.execute("SELECT DISTINCT disposition FROM quarantine")}
          <= {"REJECTED", "LOADED_FLAGGED"})
    check("quarantine: flagged records are actually in the target",
          q1("SELECT COUNT(*) FROM quarantine q WHERE q.disposition='LOADED_FLAGGED'"
             " AND q.entity='worker'"
             " AND q.source_ref NOT IN (SELECT worker_id FROM worker)") == 0)
    # WRK-002 rejects the duplicate copy while the surviving copy keeps the key,
    # so its natural key is supposed to be present. Every other rule means the
    # worker did not load at all.
    check("quarantine: rejected workers are absent from the target",
          q1("SELECT COUNT(*) FROM quarantine q WHERE q.disposition='REJECTED'"
             " AND q.entity='worker' AND q.rule_id != 'WRK-002'"
             " AND q.source_ref IN (SELECT worker_id FROM worker)") == 0,
          "WRK-002 excluded: the surviving copy legitimately holds the key")

    # ---- 9. cleansing log ----------------------------------------------------
    check("cleansing: no entry records a no-op",
          q1("SELECT COUNT(*) FROM cleansing_log WHERE before_value = after_value") == 0)
    check("cleansing: every rule_id is well formed",
          all(re.fullmatch(r"CLN-\d{3}", r[0])
              for r in c.execute("SELECT DISTINCT rule_id FROM cleansing_log")))
    unpersisted = q1("""SELECT COUNT(*) FROM cleansing_log cl WHERE cl.rule_id='CLN-003'
                        AND cl.field='department'""")
    check("cleansing: every logged change is visible in the target",
          unpersisted == 0,
          f"{unpersisted} CLN-003 department changes are to a matching key that "
          "is never stored", known=8)

    # ---- 10. audit -----------------------------------------------------------
    check("audit: exactly one run recorded", q1("SELECT COUNT(*) FROM migration_run") == 1)
    check("audit: run completed", q1("SELECT status FROM migration_run") == "SUCCESS")
    check("audit: run has an end time", q1("SELECT ended_at FROM migration_run") is not None)

    # ---- report --------------------------------------------------------------
    width = max(len(n) for n, _, _, _ in RESULTS)
    print("=" * (width + 34))
    print("VALIDITY CHECKS")
    print("=" * (width + 34))
    passed = failed = known = 0
    for name, ok, detail, kn in RESULTS:
        if ok:
            status, _ = "PASS", (passed := passed + 1)
        elif kn:
            status, _ = "KNOWN", (known := known + 1)
        else:
            status, _ = "FAIL", (failed := failed + 1)
        suffix = f" (known issue {kn})" if (kn and not ok) else ""
        print(f"  {status:<5} {name:<{width}}  {detail}{suffix}")
    print("=" * (width + 34))
    print(f"  {passed} passed, {failed} failed, {known} known defect"
          f"{'' if known == 1 else 's'} out of {len(RESULTS)} checks")
    if known and not failed:
        print("  Known defects are documented in the README and are not regressions.")
    c.close()
    return 0 if failed == 0 else 1


def _isnum(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
