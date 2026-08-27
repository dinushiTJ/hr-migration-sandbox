"""
Export one completed run as JSON for the visual walkthrough.

Reconstructs a per-record event stream by matching each staged raw record back
to its quarantine row. Staging holds every source record verbatim and
quarantine stores the same verbatim record, so anything with no quarantine row
was loaded. That is the same replayability the staging layer exists to provide
-- the visualisation is derived from the run, not re-narrated by hand.

The join has to consume each quarantine row exactly once. Some duplicate source
records are byte-identical (E00075 appears twice with the same payload), and a
plain lookup marks every copy rejected, over-counting rejections and losing a
worker that was in fact loaded. Where a raw record has n staged copies and m
quarantine rows, the m rows are assigned to the *trailing* copies, matching
WRK-002's "first occurrence retained".
"""
import json
import sqlite3
from pathlib import Path

# parse_date is reused rather than reimplemented: pairing a loaded target row
# back to the source row it came from means resolving the same four legacy date
# formats the load resolved, and a second implementation could disagree.
from migrate import iso, parse_date

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "out" / "hr_migration.db"
OUT = ROOT / "out" / "run.json"


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    run = c.execute("SELECT * FROM migration_run ORDER BY started_at DESC LIMIT 1").fetchone()
    run_id = run["run_id"]

    metrics = {(r["entity"], r["metric"]): r["value"] for r in
               c.execute("SELECT * FROM reconciliation WHERE run_id=?", (run_id,))}

    rules = [dict(r) for r in c.execute(
        "SELECT rule_id, COUNT(*) n, MIN(disposition) disposition, MIN(reason) reason,"
        " MIN(entity) entity FROM quarantine WHERE run_id=? GROUP BY rule_id"
        " ORDER BY COUNT(*) DESC", (run_id,))]

    # raw record -> its quarantine rows. WRK-010 stores a synthetic record
    # rather than the source row, so it is keyed by worker instead.
    by_raw, flagged_workers = {}, {}
    for q in c.execute("SELECT * FROM quarantine WHERE run_id=?", (run_id,)):
        if q["rule_id"] == "WRK-010":
            flagged_workers[q["source_ref"]] = (q["rule_id"], q["reason"])
        else:
            by_raw.setdefault(q["raw_record"], []).append(
                (q["rule_id"], q["reason"], q["disposition"]))

    events = []

    def emit(entity, table, key_field, label):
        staged = [r["payload"] for r in
                  c.execute(f"SELECT payload FROM {table} ORDER BY source_row")]

        # Assign each raw record's quarantine rows to its trailing copies.
        positions = {}
        for i, raw in enumerate(staged):
            positions.setdefault(raw, []).append(i)
        hits = {}
        for raw, idxs in positions.items():
            found = by_raw.get(raw, [])
            for i, hit in zip(idxs[len(idxs) - len(found):], found):
                hits[i] = hit

        for i, raw in enumerate(staged):
            rec = json.loads(raw)
            hit = hits.get(i)
            if hit:
                rule_id, reason, disp = hit
                outcome = "flagged" if disp == "LOADED_FLAGGED" else "rejected"
            elif entity == "worker" and rec.get(key_field) in flagged_workers:
                rule_id, reason = flagged_workers[rec[key_field]]
                outcome, disp = "flagged", "LOADED_FLAGGED"
            else:
                rule_id = reason = None
                outcome = "loaded"
            ev = {"e": entity, "k": rec.get(key_field, ""), "o": outcome,
                  "r": rule_id, "why": reason, "raw": rec, "label": label(rec)}
            if entity == "compensation":
                try:
                    ev["amt"] = float(rec.get("annual_salary"))
                except (TypeError, ValueError):
                    ev["amt"] = 0.0
            events.append(ev)

    emit("org", "stg_org", "org_id", lambda r: r.get("org_name", ""))
    emit("worker", "stg_hris_worker", "employee_id",
         lambda r: f"{r.get('first_name','')} {r.get('last_name','')}".strip())
    emit("compensation", "stg_payroll", "employee_id",
         lambda r: r.get("pay_period_start", ""))

    integrity = {
        "overlapping compensation periods": c.execute("""
            SELECT COUNT(*) FROM compensation a JOIN compensation b
              ON a.worker_id=b.worker_id AND a.effective_from<b.effective_from
             AND (a.effective_to IS NULL OR a.effective_to>b.effective_from)""").fetchone()[0],
        "positions with no matching worker version": c.execute("""
            SELECT COUNT(*) FROM position_assignment p LEFT JOIN worker w
              ON p.worker_id=w.worker_id AND p.effective_from=w.effective_from
            WHERE w.worker_id IS NULL""").fetchone()[0],
        "compensation for unknown worker": c.execute("""
            SELECT COUNT(*) FROM compensation cm LEFT JOIN worker w
              ON cm.worker_id=w.worker_id WHERE w.worker_id IS NULL""").fetchone()[0],
        "dangling manager references": c.execute("""
            SELECT COUNT(*) FROM position_assignment p WHERE p.manager_worker_id IS NOT NULL
              AND p.manager_worker_id NOT IN (SELECT worker_id FROM worker)""").fetchone()[0],
    }

    # ---- target rows, each paired to the source record it came from ----
    src_ix = {}
    for i, ev in enumerate(events):
        if ev["o"] == "rejected":
            continue
        if ev["e"] == "compensation":
            d, ok = parse_date(ev["raw"].get("pay_period_start"))
            if ok and d:
                src_ix[("compensation", ev["k"], iso(d))] = i
        else:
            src_ix.setdefault((ev["e"], ev["k"]), i)

    target = {"supervisory_org": [], "worker": [], "compensation": []}

    for r in c.execute("SELECT * FROM supervisory_org ORDER BY org_id"):
        target["supervisory_org"].append({"row": dict(r), "src": src_ix.get(("org", r["org_id"]))})

    for r in c.execute("""
            SELECT w.worker_id, w.effective_from, w.effective_to, w.legal_first_name,
                   w.legal_last_name, w.employment_status, p.job_title, p.org_id,
                   p.manager_worker_id, p.fte, p.employment_type
            FROM worker w JOIN position_assignment p
              ON w.worker_id=p.worker_id AND w.effective_from=p.effective_from
            ORDER BY w.worker_id"""):
        target["worker"].append({"row": dict(r), "src": src_ix.get(("worker", r["worker_id"]))})

    for r in c.execute("SELECT * FROM compensation ORDER BY worker_id, effective_from"):
        target["compensation"].append({
            "row": dict(r),
            "src": src_ix.get(("compensation", r["worker_id"], r["effective_from"])),
        })

    unpaired = sum(1 for k in target for t in target[k] if t["src"] is None)
    if unpaired:
        raise SystemExit(f"{unpaired} target rows could not be paired to a source record")

    # ---- cleansing log, tied back to the record that produced each change ----
    ev_by_key = {}
    for i, ev in enumerate(events):
        ev_by_key.setdefault((ev["e"], ev["k"]), i)

    def locate(entity, ref, field, before):
        """Index of the event this change came from.

        Matched on the field's own before-value where that is still the raw
        source value, which pins the change to the exact row. CLN-004 compares a
        value that has already been normalised, so it falls back to the first
        event for that key.
        """
        for i, ev in enumerate(events):
            if ev["e"] == entity and ev["k"] == ref and str(ev["raw"].get(field, "")) == before:
                return i
        return ev_by_key.get((entity, ref), 0)

    cl_summary = [dict(r) for r in c.execute(
        "SELECT rule_id, field, COUNT(*) n, MIN(note) note FROM cleansing_log"
        " WHERE run_id=? GROUP BY rule_id, field ORDER BY rule_id, COUNT(*) DESC", (run_id,))]

    cl_rows = []
    for r in c.execute("SELECT * FROM cleansing_log WHERE run_id=? ORDER BY rowid", (run_id,)):
        ent = {"org": "org", "worker": "worker", "compensation": "compensation"}[r["entity"]]
        cl_rows.append([ent, r["source_ref"], r["rule_id"], r["field"],
                        r["before_value"], r["after_value"], r["note"] or "",
                        locate(ent, r["source_ref"], r["field"], r["before_value"])])

    payload = {
        "run_id": run_id, "started_at": run["started_at"], "status": run["status"],
        "entities": [
            {"name": "supervisory_org", "source": metrics[("supervisory_org", "source_rows")],
             "loaded": metrics[("supervisory_org", "loaded")]},
            {"name": "worker", "source": metrics[("worker", "source_rows")],
             "loaded": metrics[("worker", "loaded")]},
            {"name": "compensation", "source": metrics[("compensation", "source_rows")],
             "loaded": metrics[("compensation", "loaded")]},
        ],
        "control": {
            "source": metrics[("compensation", "source_salary_total")],
            "loaded": metrics[("compensation", "loaded_salary_total")],
            "rejected": metrics[("compensation", "rejected_salary_total")],
        },
        "rules": rules, "integrity": integrity, "events": events, "target": target,
        "cleansing": {"summary": cl_summary, "rows": cl_rows},
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"{OUT.name}  {len(events)} events  "
          f"{sum(len(v) for v in target.values())} target rows  "
          f"{len(cl_rows)} cleansed values  {OUT.stat().st_size/1024:.0f} KB")
    c.close()


if __name__ == "__main__":
    main()
