# HR Data Migration Sandbox

Preparing messy legacy HR and payroll data for load into a Workday-shaped
target: profile, cleanse, map, validate, load, reconcile.

Runs on Python 3 and SQLite. No dependencies, no services, no setup. A full
rebuild from an empty directory takes 0.17 seconds:
generate 0.03s, migrate 0.06s, export 0.05s, build page 0.02s, reconcile 0.01s.

> **Publication and data handling:** `src/generate_sources.py` creates synthetic
> data only. The generated `data/` extracts and `out/` artefacts contain raw
> records and are ignored by Git; do not replace them with real HR or payroll
> data in a public checkout. See [SECURITY.md](SECURITY.md) before publishing.

**New here?** The [FAQ](FAQ.md) explains what this project does and why in plain English,
with no technical background assumed. It is also published as a page at
[dinushitj.github.io/hr-migration-sandbox/faq.html](https://dinushitj.github.io/hr-migration-sandbox/faq.html).

GitHub Pages is configured through `.github/workflows/pages.yml`. It rebuilds
the synthetic sources in CI, runs validation as a deployment gate, and publishes
the generated replay page as `index.html` and the rendered FAQ as `faq.html`.
Enable **GitHub Actions** as the Pages source in the repository settings.

```bash
python3 src/generate_sources.py   # build three inconsistent legacy sources
python3 src/migrate.py            # profile, cleanse, validate, transform, load
python3 src/reconcile.py          # reconciliation report
python3 src/validate.py           # independent validity checks
```

Two further steps build a visual replay of the run. They are optional and
change nothing about the pipeline:

```bash
python3 src/export_viz.py         # export the completed run as JSON
python3 src/build_viz.py          # render out/control_room.html
```

## At a glance

| | |
|---|---|
| Source records in | **943** (309 workers, 626 payroll, 8 orgs) |
| Loaded to target | **1,145** rows (8 orgs, 297 workers, 297 positions, 543 compensation) |
| Rejected | **95** records under 8 rules |
| Loaded but flagged | **18** records under 2 rules |
| Values cleansed | **1,633** under 5 rules |
| Money reconciled | **$58,055,893.15** in, residual **0.00** |
| Integrity checks | **4 of 4** return zero |
| Full rebuild | **0.17s** end to end |

---

## What this demonstrates

The subject is HR domain knowledge and migration discipline, not
infrastructure. Specifically:

- **Effective dating**, the concept that shapes Workday's data model and trips
  up loads that treat a worker as one mutable row.
- **Rejection with attribution**: every record that does not load is traceable
  to a numbered rule, so rejection counts can be compared across runs.
- **Cleansing with attribution**: every value the load rewrote is recorded with
  its before and after, because a migration that cannot say what it changed is
  asking the business to take the target on trust.
- **Financial control totals**, the only check that proves *values* survived the
  transformation rather than just row counts.

---

## Pipeline, start to end

### Stage 1: generate the sources (`src/generate_sources.py`)

Builds three files standing in for three separate legacy systems:

| File | Format | Rows | Stands in for |
|---|---|---|---|
| `data/hris_workers.csv` | CSV | 309 | Core HR extract: names, hire and termination dates, job, department, manager, FTE |
| `data/payroll_export.csv` | CSV | 626 | Payroll export: pay periods, annual salary, cost centre, pay group |
| `data/org_hierarchy.xml` | XML | 8 | Org structure from a third system: supervisory orgs, parents, cost centres |

300 workers, of which 9 are duplicated to give 309 rows. The random seed is
fixed, so every run produces identical data. Rejection counts are meaningless
if they move between runs for reasons unrelated to the rules.

Faults are injected deliberately and at a known rate. Without them the
rejection path never executes and the reconciliation report is a page of zeros.

Two columns matter here and they are not the same number. What is *in the file*
is not what a rule *catches*, because rules also catch knock-on damage.

| Fault | In the file | Rule | Caught |
|---|---|---|---|
| Duplicate `employee_id`, conflicting job title and FTE | 9 | `WRK-002` | 9 |
| `manager_id` pointing outside the file entirely | 9 | `WRK-010` | 17 |
| Employees in payroll but absent from HRIS | 6 rows | `CMP-001` | 12 |
| Pay periods beginning after termination | 41 | `CMP-007` | 41 |
| Empty salary | 16 | `CMP-002` | 16 |
| Zero salary | 6 | `CMP-003` | 7 |
| Negative salary | 1 | `CMP-003` | (same rule) |
| Department with leading or trailing whitespace | 22 | `CLN-002` | 20 |
| Department in the wrong case | 17 | `CLN-003` | 281 |
| FTE outside any plausible range | 3 | `WRK-008` | 3 |
| Org whose parent is not in the file | 1 | `ORG-001` | 1 |

Where the two columns differ, the gap is the interesting part:

- **`WRK-010` catches 17 where only 9 were injected.** The other 8 are workers
  whose manager exists in the file but was itself rejected. Broken references
  are not only the ones pointed at nothing to begin with.
- **`CMP-001` catches 12 where only 6 rows are for unknown employees.** The
  other 6 are the cascade: payroll rows belonging to workers a `WRK` rule
  rejected.
- **`CMP-007` catches 41 where only 8 were deliberately injected.** The other 33
  emerged on their own from random pay periods landing after random termination
  dates. Realistic faults do not need to be planted to appear.
- **`CLN-003` touches 281 departments where 17 were given the wrong case.** The
  rule folds case on every value it compares, not only the dirty ones, which is
  issue 8 in Known issues below.

Four date formats are mixed within single columns:

| Format | `hire_date` | `pay_period_start` |
|---|---|---|
| ISO 8601 (`2010-03-09`) | 124 | 312 |
| DD/MM/YYYY (`09/03/2010`) | 71 | 314 |
| DD-Mon-YYYY (`09-Mar-2010`) | 52 | 0 |
| Excel serial (`40246`) | 62 | 0 |

### Stage 2: stage the raw records (`src/migrate.py`)

Every source record is written to `stg_hris_worker`, `stg_payroll` or `stg_org`
verbatim, as JSON, before anything is validated: 309, 626 and 8 rows
respectively, 943 in total, none of them judged. A broken record is still a
fact about what the source sent. Keeping it is what makes the load replayable
and lets any rejection be traced back to raw input.

The run row is written to `migration_run` as `RUNNING` and committed
immediately, before the work starts, so a crash leaves a visible record rather
than nothing.

### Stage 3: cleanse

Five cleansing rules, each with a stable ID, writing every changed value to
`cleansing_log` with its before and after.

| Rule | What it does | Values touched |
|---|---|---|
| `CLN-001` | Legacy date parsed to ISO 8601, source format recorded | 763 |
| `CLN-002` | Leading, trailing and repeated whitespace collapsed | 68 |
| `CLN-003` | Case standardised | 453 |
| `CLN-004` | Department name resolved to a supervisory org | 297 |
| `CLN-005` | Salary normalised to two decimal places | 52 |

Broken down by field:

| Rule | Field | Values |
|---|---|---|
| `CLN-001` | `pay_period_end` | 281 |
| `CLN-001` | `pay_period_start` | 276 |
| `CLN-001` | `hire_date` | 174 |
| `CLN-001` | `termination_date` | 32 |
| `CLN-002` | `cost_centre` | 48 |
| `CLN-002` | `department` | 20 |
| `CLN-003` | `department` | 281 |
| `CLN-003` | `currency` | 124 |
| `CLN-003` | `cost_centre` | 48 |
| `CLN-004` | `department` | 297 |
| `CLN-005` | `annual_salary` | 52 |

The 763 date conversions by the format they arrived in:

| Source format | Converted |
|---|---|
| DD/MM/YYYY | 632 |
| Excel serial | 71 |
| DD-Mon-YYYY | 60 |

1,633 values across the run. Whitespace and case are separate rules on purpose:
collapsing whitespace is uncontroversial, while forcing case is a
standardisation decision a data owner should get to see and argue with.

Order matters more than it looks. Normalisation happens *before* comparison,
never after. Deduplicate departments on the raw value and `"  FACILITIES "` and
`"Facilities"` become two different supervisory orgs. All 297 loaded workers
resolved to an org, which is the evidence that ordering is right.

Dates are parsed from four formats into ISO. Anything unparseable is rejected
rather than guessed at, because a silently wrong hire date is worse than a
visibly missing one. `parse_date` and the format-label helper share one table
of formats so the log can never disagree with the parser.

### Stage 4: validate and load

Rules are numbered by entity. Rejected records go to `quarantine` with the rule
ID, the natural key, a human-readable reason and the original raw record.

Not every failure is a rejection. Every quarantine row carries a `disposition`
of `REJECTED` or `LOADED_FLAGGED`, because dropping a record sometimes costs
more than the fault does:

- `ORG-001`: an org whose parent is missing is loaded as a root, not deleted.
- `WRK-010`: a worker whose manager cannot be resolved is loaded without a
  supervisor.

Both are recorded, neither is silent. This distinction matters to the headline
number: 17 flagged workers were loaded, and counting them as rejections would
have reported a 9.4% worker rejection rate instead of the true 3.9%.

**Rejections cascade.** A payroll row for a worker who failed validation is
rejected too (`CMP-001`), because compensation attached to a worker who does
not exist in the target is worse than no compensation row at all.

**Manager references are resolved in a second pass.** They cannot be checked
while iterating the first time, because the manager may appear later in the
file. The whole set is validated first, then references are resolved against
the survivors.

### Stage 5: reconcile (`src/reconcile.py`)

Row counts per entity, rejections by rule, cleansing by rule, a financial
control total, and four referential integrity checks against the loaded target.

### Stage 6: validate (`src/validate.py`)

30 checks that re-derive every invariant from the database and the source files
and deliberately do **not** import the pipeline, so a bug shared between the
loader and its own reconciliation cannot hide from them. The overlap check, the
date parser and the money arithmetic are all reimplemented here rather than
reused.

They cover staging completeness, record conservation, money conservation,
effective dating, referential integrity, target value shape, transformation
fidelity, quarantine traceability, cleansing consistency and the audit trail.

Current result: **29 passed, 0 failed, 1 known defect.** A defect already
documented under Known issues is reported as `KNOWN` rather than `FAIL`, so the
harness stays usable as a gate while staying honest about what is wrong.

Writing it found two things. `WRK-010` was storing a synthetic stand-in record
rather than the source row, so 17 quarantine entries could not be traced back to
staging; it now stores the raw record like every other rule. The second was a
badly specified check of my own: it asserted that no rejected worker appears in
the target, which is wrong for `WRK-002`, where the duplicate copy is rejected
while the surviving copy legitimately keeps the key.

---

## Target model

Shaped on Workday's core objects: `supervisory_org`, `worker`,
`position_assignment`, `compensation`.

The concept that drives the design is **effective dating**. Workday does not
hold a worker as one mutable row that gets updated; it holds a series of dated
versions, each valid for a period. So the worker, position and compensation
tables carry `effective_from` / `effective_to` (null meaning currently in
effect), and a worker may not hold two records whose periods overlap.

That check is subtler than it looks. Testing for a duplicate start date is not
enough: 1 March to 31 March and 15 March to 14 April have different start dates
and still overlap. It needs real interval comparison, sorting each worker's
records by start date and testing every candidate against the periods already
accepted. The first version of this pipeline made exactly that mistake and let
six overlapping records through. The integrity check in `reconcile.py` is what
caught it, which is the argument for building the check before trusting the
rule.

Supporting tables: `migration_run` (audit), `quarantine`, `cleansing_log`,
`reconciliation` (metrics), and the three `stg_*` staging tables.

---

## Production equivalents

This is a sandbox, so every step is done in the standard library. On a real
Workday programme each step has an established tool, and knowing which one goes
where is most of the job. Tool names below are used descriptively; the choice
varies by programme and by what the client already owns.

<!-- TOOLS:START -->
| Step | In this sandbox | In production |
|---|---|---|
| **Extract from legacy** | A seeded Python generator writes CSV and XML, standing in for three source systems. | Informatica, Talend, Fivetran, Airbyte, SAP SuccessFactors, Oracle HCM, PeopleSoft |
| **Land and stage raw** | SQLite stg_ tables holding each source record verbatim as JSON, before any judgement. | Snowflake, BigQuery, Databricks, S3 / ADLS landing zone, Azure Synapse |
| **Cleanse and standardise** | Python normalisation with every changed value written to cleansing_log under a CLN rule. | dbt, Informatica Data Quality, Talend Data Quality, Alteryx, OpenRefine |
| **Validate and quarantine** | 24 numbered rules; failures go to quarantine with rule id, key, reason and raw record. | Great Expectations, Soda Core, dbt tests, Monte Carlo, Collibra DQ |
| **Effective dating and history** | Hand-rolled interval logic with a real overlap check, because that is the thing being demonstrated. | dbt snapshots (SCD2), Kimball SCD loads, Data Vault satellites |
| **Load into Workday** | Nothing. The target is Workday-shaped and has never been loaded into a tenant. | Workday EIB, iLoad, Workday Studio, Core Connectors, Workday Web Services |
| **Orchestrate** | Five commands run by hand, in order. | Airflow, Dagster, Prefect, Azure Data Factory, Control-M |
| **Reconcile and report** | reconcile.py for the control total and integrity checks, validate.py for 30 independent invariants. | dbt tests, Power BI, Tableau, Workday delivered audit reports |
| **Govern, audit and lineage** | migration_run, quarantine and cleansing_log give a per-run audit trail. | Collibra, Alation, Unity Catalog, OpenLineage |
| **Version control and CI** | None. The pipeline is deterministic, which is what makes counts comparable between runs. | Git, GitHub Actions, Azure DevOps |
| **Test data and PII** | Wholly synthetic. No real people, so no masking is required. | Delphix, Informatica TDM, Static masking, Restricted tenants |
<!-- TOOLS:END -->

The table is generated from `viz/tools.json`, which is also what the page renders
as chips, so the two cannot drift apart.

The step that matters most for interview purposes is the one this project does
not do at all: **loading into Workday**. A real conversion runs through EIB
spreadsheets or iLoad into a series of mock-conversion tenants (commonly P1, P2,
P3), each one reconciled and signed off by the data owners before the next.
Everything here stops at the point where that would begin.

---

## Results

From a clean rebuild. These numbers are reproducible: delete `out/` and `data/`,
re-run, and they are identical.

### Records

| Entity | Source | Loaded | Rejected | Flagged | Rejection rate |
|---|---|---|---|---|---|
| `supervisory_org` | 8 | 8 | 0 | 1 | 0.0% |
| `worker` | 309 | 297 | 12 | 17 | 3.9% |
| `compensation` | 626 | 543 | 83 | 0 | 13.3% |

Target contents: 8 orgs, 297 workers, 297 position assignments and 543
compensation records, 1,145 rows in total.

The replay page reports 848 rather than 1,145 because it folds each position
assignment into its worker row, which is how they are always created and always
read: one row per worker version, carrying the job that version held.

Quarantine holds 113 rows: 95 rejected and 18 loaded-but-flagged. The flagged
18 appear in both the target and quarantine, which is the `LOADED_FLAGGED`
disposition being honest rather than filing each record under one heading.

Payroll is dirtier than core HR, which is the realistic direction for that
asymmetry to point.

### Rejections by rule

| Rule | Count | Disposition | Reason |
|---|---|---|---|
| `CMP-007` | 41 | rejected | Pay period starts after the worker's termination date |
| `WRK-010` | 17 | loaded, flagged | `manager_id` not found among valid workers |
| `CMP-002` | 16 | rejected | Missing or non-numeric salary |
| `CMP-001` | 12 | rejected | Payroll record for a worker not present in the target |
| `WRK-002` | 9 | rejected | Duplicate `employee_id`, first occurrence retained |
| `CMP-003` | 7 | rejected | Salary must be greater than zero |
| `CMP-008` | 7 | rejected | Compensation period overlaps an existing period |
| `WRK-008` | 3 | rejected | FTE outside plausible range |
| `ORG-001` | 1 | loaded, flagged | Parent org not found in source, loaded as root |

Ten further rules are implemented but do not fire on this seed: `WRK-001`,
`WRK-003` to `WRK-007`, `WRK-009`, `CMP-004`, `CMP-005`, `CMP-006`. They cover
missing IDs, unparseable dates, termination before hire, non-numeric FTE,
missing names, and pay periods that are unparseable, reversed or before the
hire date.

### Financial control total

```
source file total                        58,055,893.15
loaded total (queried from target)       52,397,145.78
rejected total (quarantined value)        5,658,747.37
                                      ----------------
residual (source - loaded - rejected)             0.00
```

This is the check that matters. Row counts prove nothing about whether values
survived the transformation, because a salary silently divided by 12 leaves the
row count identical. Every pound that entered the pipeline either landed in the
target or is itemised in quarantine under a numbered rule.

The loaded figure is queried back out of the target rather than taken from the
pipeline's own counter, so the check tests the data that was actually written.
The counter is compared separately as a secondary tie-out. Money is accumulated
in integer cents rather than floats, because float drift prints `-0.00` on a run
that genuinely balances, which is exactly the artefact the control total exists
to rule out.

### Integrity checks

All four return zero:

- overlapping compensation periods
- positions with no matching worker version
- compensation for an unknown worker
- dangling manager references

---

## The visual replay

`src/export_viz.py` exports the completed run to `out/run.json`, and
`src/build_viz.py` injects it into `viz/template.html` to produce a
self-contained `out/control_room.html` (679 KB, no external assets).

It opens with a flow figure of the whole pipeline: three sources, staged
verbatim, cleansed, validated, and then either loaded or quarantined. Its counts
are driven from the same computed state as the panels below it, so the picture
cannot drift from the numbers, and they fill in as the run plays. The figure
exists to show the one thing prose keeps fumbling: there are three outcomes, not
two, and the flagged path goes to the target and to quarantine at the same time.
The cascade edge is drawn too, since a rejected worker rejecting that worker's
payroll rows is an arrow, not a sentence.

It replays the run record by record with play, step, speed and scrub controls.
Each record shows its raw fields, the format each date arrived in (`41022`
tagged as an Excel serial resolving to `2010-08-22`), and the rule that accepted
or stopped it. The control total ticks alongside and the residual holds at 0.00
for the whole run.

Four tabs browse the same records: **Before** (source as received), **After**
(rows in the target, each expandable to the source record beside it with changed
fields highlighted), **Quarantine** (all 113 held-back records), and **Cleansed**
(all 1,633 transformations with before and after).

The page also carries its own documentation: this README rendered in full, and
the live output of the validity checks, both injected at build time. The checks
are executed during the build rather than pasted in, so the page cannot show a
green result from an earlier state of the code.

The page is generated, never hand-written, so it cannot drift from the run. The
export reconstructs a per-record event stream by joining staged raw records back
to quarantine rows, reuses `parse_date` from the pipeline rather than
reimplementing it, and hard-fails if any target row cannot be traced to a source
record. All 848 pair (positions travel with their worker row).

---

## How this was verified

- **Reproducibility**: deleting `out/` and `data/` and re-running produces
  identical counts and totals.
- **Control total**: residual is 0.00 to the cent, with the loaded side queried
  from the target rather than trusted from a counter.
- **Integrity**: all four checks return zero.
- **The page against the report**: Node executes the published page's own
  JavaScript against a stubbed DOM, drives the scrubber to the end of the run,
  and reads back what the page would display. All four money figures, all nine
  rule counts, all entity counts and all four tab counts tie to the terminal
  report.
- **Layout**: rendered in headless Chrome at 1400px, 900px and 640px in both
  themes, with two probes: one measuring every element against the page width,
  one testing every pair of text boxes for intersection while accounting for
  clipping ancestors. No overflow, no overlaps. A third probe checks that every
  label inside the flow figure fits its box.
- **Invariants**: `src/validate.py`, 30 checks re-derived without importing the
  pipeline. 29 pass, 1 is a known documented defect, 0 fail.
- **Contrast**: `src/check_contrast.py` reads the theme tokens out of the template
  and computes all 42 foreground and background pairs across both themes against
  the WCAG AA 4.5:1 threshold. It runs in CI as a deployment gate. Two tokens
  failed when this was first measured; see
  [the accessibility review](docs/accessibility-review.md).

One bug this caught: the export's raw-record join marked *both* copies of the
byte-identical duplicate `E00075` as rejected, over-counting rejections by one
and losing a worker that had in fact loaded. The join now consumes each
quarantine row once and assigns it to the trailing duplicate, matching
`WRK-002`'s "first occurrence retained".

---

## Known issues

Found by auditing the finished pipeline. They are listed because they are real,
not because they are theoretical.

1. **The survivorship rule for duplicates is arbitrary.** The load keeps
   whichever copy appears first in the file. For the 8 duplicates that genuinely
   conflict on job title and FTE, that is an undefended choice about which
   version of a person's job is true. A real migration needs a stated rule
   (most recent, most complete, source-system priority) agreed with the data
   owner.
2. **The control total cannot see money it cannot parse.** A salary arriving as
   `"12,345.67"` is excluded from the source total and valued at zero in the
   rejected total, so the residual stays 0.00 and the check reports BALANCES.
   The row is quarantined and visible under `CMP-002`, but the check whose job
   is proving no value went missing is blind to the case where value arrives in
   an unexpected format. Thousands separators, bracketed negatives and currency
   symbols are all normal in payroll extracts.
3. **`CLN-005` is mislabelled in intent.** All 52 values it touches are
   formatting (`125907.2` to `125907.20`); none lost precision. The rule is
   named for rounding that never happens.
4. **`WRK-002` asserts a conflict it does not check.** It reports "conflicting
   attributes" on the strength of a repeated ID alone. `E00075` is a
   byte-identical duplicate, which is a different data problem (usually a double
   extract) and warrants its own rule.
5. **A duplicate whose first copy is invalid loses the worker entirely.** The
   duplicate check runs before date and FTE validation, so if the first
   occurrence fails a later rule, it is rejected on its own merits and every
   subsequent copy is rejected as a duplicate. It does not fire on this seed.
6. **Three of the four integrity checks cannot fail by construction.** Only the
   compensation overlap check does real work. Positions always match a worker
   version because both are inserted in the same loop; compensation only inserts
   for valid workers; `WRK-010` nulls unresolvable managers before insert. They
   are regression guards against a future loader change, not evidence about this
   run.
7. **`supervisory_org` is not effective-dated**, unlike the other three target
   tables. Orgs are current-state only.
8. **`CLN-003` logs 281 changes to a value that is never stored.** Department is
   lowercased only as a matching key; the target keeps `org_id`.
9. **Effective dating is never exercised for workers.** One version per worker
   means the no-overlap rule is trivially satisfied there; only compensation
   proves the discipline. The generator produces no job changes or promotions,
   which is the case Workday's model exists for.

---

## Limitations

Stated because a reviewer will find them anyway, and finding them yourself is
the more convincing signal.

- **The data is generated.** Names, salaries and org structures are synthetic.
  The faults are realistic; the records are not real people.
- **Workday-shaped, not Workday-validated.** The target mirrors the object model
  and the effective-dating rule. It has not been loaded into a Workday tenant,
  and real Workday load files (EIB / iLoad) have requirements this does not
  attempt.
- **Compensation history is thin.** Pay periods are generated independently
  rather than as a continuous salary history, so the effective-dating check is
  exercised but the sequences are not realistic career progressions.
- **No incremental or delta load.** Every run rebuilds the target from scratch.
  A real mock migration cycle would need delta handling and a rollback path.
- **Cleansing rules are applied, not agreed.** In a real migration the
  standardisation rules would be signed off by the data owners in HR and Payroll
  before anything was loaded. Here they are asserted in code. The
  `cleansing_log` exists so that conversation has something concrete to happen
  over, but the conversation has not happened.
- **The visual replay is a view, not a tool.** `control_room.html` renders one
  exported run. It does not connect to anything, and re-running the pipeline
  means re-exporting to update it.

---

## Layout

```
src/generate_sources.py   three inconsistent legacy sources
src/migrate.py            stage, cleanse, validate, load
src/reconcile.py          reconciliation report
src/validate.py           independent validity checks
src/markdown_lite.py      minimal Markdown renderer for the docs on the page
src/export_viz.py         export a completed run to JSON
src/build_viz.py          render the visual replay
src/build_faq.py          render FAQ.md as a standalone accessible page
sql/schema.sql            staging, target, audit and quarantine tables
viz/template.html         replay page template
FAQ.md                    plain-English FAQ, also published as faq.html
docs/                     design notes and the accessibility review
data/                     generated sources
out/                      SQLite target, run.json, control_room.html, faq.html
```

Artefact sizes: `hris_workers.csv` 23 KB, `payroll_export.csv` 37 KB,
`org_hierarchy.xml` 1 KB, `hr_migration.db` 648 KB, `run.json` 637 KB,
`control_room.html` 744 KB, `faq.html` 8 KB.
