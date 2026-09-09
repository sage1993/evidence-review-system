PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;

CREATE TABLE IF NOT EXISTS matter_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR REPLACE INTO matter_meta(key, value)
VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS matters (
    matter_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    document_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matter_baselines (
    matter_id TEXT PRIMARY KEY,
    document_json TEXT NOT NULL,
    FOREIGN KEY (matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS matter_events (
    matter_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    matter_revision INTEGER NOT NULL CHECK (matter_revision >= 1),
    event_json TEXT NOT NULL,
    PRIMARY KEY (matter_id, sequence),
    FOREIGN KEY (matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS matter_projections (
    matter_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    document_json TEXT NOT NULL,
    FOREIGN KEY (matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS matter_source_dependencies (
    matter_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    PRIMARY KEY (matter_id, issue_id, source_key),
    FOREIGN KEY (matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS matter_evidence_bindings (
    matter_id TEXT PRIMARY KEY,
    evidence_snapshot_hash TEXT NOT NULL,
    evidence_db_sha256 TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    bound_revision INTEGER NOT NULL CHECK (bound_revision >= 1),
    FOREIGN KEY (matter_id) REFERENCES matters(matter_id) ON DELETE CASCADE
);
