"""
Reconciliation report: source counts against loaded counts, every rejection
accounted for by rule, and a financial control total.

The control total is the part that matters. Row counts tell you nothing about
whether the numbers survived the transformation intact -- a salary silently
divided by 12 leaves the row count identical. Summing the money on both sides
and proving the difference equals exactly what was rejected is the check that
would actually catch it.
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "out" / "hr_migration.db"


def rule(title):
    print(f"\n{title}")
    print("-" * 74)


def main():
    c = sqlite3.connect(DB)
    run_id, started, status = c.execute(
        "SELECT run_id, started_at, status FROM migration_run"
        " ORDER BY started_at DESC LIMIT 1").fetchone()

    print("=" * 74)
    print(f"HR MIGRATION RECONCILIATION REPORT      run {run_id}   {status}   {started}")
    print("=" * 74)

    metrics = dict(
        ((e, m), v) for e, m, v in c.execute(
            "SELECT entity, metric, value FROM reconciliation WHERE run_id=?", (run_id,))
    )

    rule("RECORD COUNTS BY ENTITY")
    print(f"{'entity':<20}{'source':>9}{'loaded':>9}{'rejected':>10}"
          f"{'flagged':>9}{'rate':>8}")
    entity_table = {"worker": "worker", "compensation": "compensation",
                    "supervisory_org": "org"}
    for entity in ("supervisory_org", "worker", "compensation"):
        src = metrics.get((entity, "source_rows"), 0)
        got = metrics.get((entity, "loaded"), 0)
        rej, flag = c.execute(
            "SELECT COALESCE(SUM(disposition='REJECTED'),0),"
            "       COALESCE(SUM(disposition='LOADED_FLAGGED'),0)"
            " FROM quarantine WHERE run_id=? AND entity=?",
            (run_id, entity_table[entity])).fetchone()
        pct = f"{rej / src * 100:.1f}%" if src else "-"
        print(f"{entity:<20}{src:>9.0f}{got:>9.0f}{rej:>10}{flag:>9}{pct:>8}")
    print("\n  rejected = not loaded. flagged = loaded with the fault recorded,")
    print("  because dropping the record would cost more than the fault does.")

    rule("RULE FAILURES BY RULE ID")
    print(f"{'rule':<9}{'count':>6}  {'disposition':<15}reason")
    for rid, n, disp, reason in c.execute(
            "SELECT rule_id, COUNT(*), MIN(disposition), MIN(reason) FROM quarantine"
            " WHERE run_id=? GROUP BY rule_id ORDER BY COUNT(*) DESC", (run_id,)):
        reason = reason if len(reason) < 42 else reason[:39] + "..."
        print(f"{rid:<9}{n:>6}  {disp.lower():<15}{reason}")

    rule("VALUES CLEANSED BY RULE")
    total_clean = c.execute(
        "SELECT COUNT(*) FROM cleansing_log WHERE run_id=?", (run_id,)).fetchone()[0]
    if total_clean:
        print(f"{'rule':<9}{'count':>6}  {'field':<18}what changed")
        for rid, fld, n, note in c.execute(
                "SELECT rule_id, field, COUNT(*), MIN(note) FROM cleansing_log"
                " WHERE run_id=? GROUP BY rule_id, field"
                " ORDER BY rule_id, COUNT(*) DESC", (run_id,)):
            print(f"{rid:<9}{n:>6}  {fld:<18}{note or ''}")
        print(f"\n  {total_clean} values standardised across the load. These are"
              " changes, not rejections:")
        print("  the record loaded, but it is not byte-identical to what the source sent.")
    else:
        print("  nothing cleansed")

    rule("FINANCIAL CONTROL TOTAL (compensation)")
    src_total = metrics.get(("compensation", "source_salary_total"), 0)
    got_total = metrics.get(("compensation", "loaded_salary_total"), 0)
    rej_total = metrics.get(("compensation", "rejected_salary_total"), 0)
    db_total = c.execute("SELECT COALESCE(SUM(annual_amount),0) FROM compensation").fetchone()[0]
    residual = round(round(src_total, 2) - round(db_total, 2) - round(rej_total, 2), 2)
    residual = residual + 0.0 if residual else 0.0   # avoid printing "-0.00"

    print(f"{'source file total':<38}{src_total:>16,.2f}")
    print(f"{'loaded total (queried from target)':<38}{db_total:>16,.2f}")
    print(f"{'rejected total (quarantined value)':<38}{rej_total:>16,.2f}")
    print(f"{'':<38}{'':->16}")
    print(f"{'residual (source - loaded - rejected)':<38}{residual:>16,.2f}")
    balanced = abs(residual) < 0.005
    print(f"\n  control total: {'BALANCES' if balanced else 'DOES NOT BALANCE -- investigate'}")
    if not balanced:
        print("  money entered the pipeline and was neither loaded nor quarantined.")
    print("  Row counts cannot catch a salary silently divided by 12; this can.")
    if abs(got_total - db_total) >= 0.005:
        print(f"  WARNING: pipeline counter {got_total:,.2f} does not tie to target"
              f" {db_total:,.2f}")

    rule("EFFECTIVE DATING INTEGRITY")
    overlaps = c.execute("""
        SELECT COUNT(*) FROM (
            SELECT a.worker_id FROM compensation a
            JOIN compensation b
              ON a.worker_id = b.worker_id
             AND a.effective_from < b.effective_from
             AND (a.effective_to IS NULL OR a.effective_to > b.effective_from)
        )""").fetchone()[0]
    orphan_pos = c.execute("""
        SELECT COUNT(*) FROM position_assignment p
        LEFT JOIN worker w ON p.worker_id = w.worker_id
                          AND p.effective_from = w.effective_from
        WHERE w.worker_id IS NULL""").fetchone()[0]
    orphan_comp = c.execute("""
        SELECT COUNT(*) FROM compensation cm
        LEFT JOIN worker w ON cm.worker_id = w.worker_id
        WHERE w.worker_id IS NULL""").fetchone()[0]
    dangling_mgr = c.execute("""
        SELECT COUNT(*) FROM position_assignment p
        WHERE p.manager_worker_id IS NOT NULL
          AND p.manager_worker_id NOT IN (SELECT worker_id FROM worker)""").fetchone()[0]

    for label, n in (("overlapping compensation periods", overlaps),
                     ("positions with no matching worker version", orphan_pos),
                     ("compensation for unknown worker", orphan_comp),
                     ("dangling manager references", dangling_mgr)):
        print(f"  {label:<48}{n:>6}   {'ok' if n == 0 else 'FAIL'}")

    print("\n" + "=" * 74)
    c.close()


if __name__ == "__main__":
    main()
