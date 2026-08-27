-- Staging: source data exactly as it arrived. Nothing judged, nothing cleaned.
-- Kept so any load can be replayed and any rejection traced back to raw input.
CREATE TABLE stg_hris_worker (
    source_row   INTEGER,
    payload      TEXT      -- the original record, verbatim, as JSON
);

CREATE TABLE stg_payroll (
    source_row   INTEGER,
    payload      TEXT
);

CREATE TABLE stg_org (
    source_row   INTEGER,
    payload      TEXT
);

-- ---------------------------------------------------------------------------
-- Target: shaped on Workday's core objects. The thing that matters here is
-- effective dating -- Workday holds a worker as a series of dated versions
-- rather than one mutable row, so every target table carries a validity period.
-- ---------------------------------------------------------------------------
CREATE TABLE supervisory_org (
    org_id         TEXT PRIMARY KEY,
    org_name       TEXT NOT NULL,
    parent_org_id  TEXT,
    cost_centre    TEXT
);

CREATE TABLE worker (
    worker_id         TEXT NOT NULL,
    effective_from    TEXT NOT NULL,
    effective_to      TEXT,             -- NULL = currently in effect
    legal_first_name  TEXT NOT NULL,
    legal_last_name   TEXT NOT NULL,
    employment_status TEXT NOT NULL,    -- Active | Terminated
    PRIMARY KEY (worker_id, effective_from)
);

CREATE TABLE position_assignment (
    worker_id         TEXT NOT NULL,
    effective_from    TEXT NOT NULL,
    effective_to      TEXT,
    job_title         TEXT NOT NULL,
    org_id            TEXT,
    manager_worker_id TEXT,
    fte               REAL NOT NULL,
    employment_type   TEXT,
    PRIMARY KEY (worker_id, effective_from),
    FOREIGN KEY (worker_id, effective_from) REFERENCES worker (worker_id, effective_from)
);

CREATE TABLE compensation (
    worker_id      TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to   TEXT,
    annual_amount  REAL NOT NULL,
    currency       TEXT NOT NULL,
    cost_centre    TEXT,
    pay_group      TEXT,
    PRIMARY KEY (worker_id, effective_from)
);

-- ---------------------------------------------------------------------------
-- Audit: what ran, and what it refused to load.
-- A migration that cannot say what it dropped has not been validated.
-- ---------------------------------------------------------------------------
CREATE TABLE migration_run (
    run_id     TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at   TEXT,
    status     TEXT NOT NULL           -- RUNNING | SUCCESS | FAILED
);

CREATE TABLE quarantine (
    run_id      TEXT NOT NULL,
    entity      TEXT NOT NULL,         -- worker | payroll | org
    source_ref  TEXT,                  -- the natural key, where one exists
    rule_id     TEXT NOT NULL,         -- stable ID so counts trend across runs
    reason      TEXT NOT NULL,
    raw_record  TEXT NOT NULL,
    -- REJECTED: not loaded. LOADED_FLAGGED: loaded with the fault recorded,
    -- because dropping the record would cost more than the fault does.
    disposition TEXT NOT NULL DEFAULT 'REJECTED'
);

-- What the load changed, as opposed to what it refused. A cleansing rule that
-- fires on 300 records is a standardisation decision worth showing a data owner,
-- and silently rewriting values is how a migration loses the trust of the
-- business it is migrating.
CREATE TABLE cleansing_log (
    run_id       TEXT NOT NULL,
    entity       TEXT NOT NULL,
    source_ref   TEXT,
    rule_id      TEXT NOT NULL,         -- CLN-nnn, stable across runs
    field        TEXT NOT NULL,
    before_value TEXT,
    after_value  TEXT,
    note         TEXT
);

CREATE TABLE reconciliation (
    run_id      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    metric      TEXT NOT NULL,
    value       REAL NOT NULL
);

CREATE INDEX idx_quarantine_rule ON quarantine (run_id, rule_id);
CREATE INDEX idx_cleansing_rule ON cleansing_log (run_id, rule_id);
CREATE INDEX idx_worker_eff ON worker (worker_id, effective_from);
