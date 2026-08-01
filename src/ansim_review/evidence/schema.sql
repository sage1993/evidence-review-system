PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS revisions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    source_hash TEXT NOT NULL CHECK(length(source_hash) = 64),
    byte_size INTEGER NOT NULL CHECK(byte_size >= 0),
    page_count INTEGER NOT NULL CHECK(page_count > 0),
    UNIQUE(document_id, source_hash)
) STRICT;

CREATE TABLE IF NOT EXISTS pages (
    id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL REFERENCES revisions(id),
    page_number INTEGER NOT NULL CHECK(page_number > 0),
    width REAL NOT NULL CHECK(width > 0),
    height REAL NOT NULL CHECK(height > 0),
    UNIQUE(revision_id, page_number)
) STRICT;

CREATE TABLE IF NOT EXISTS elements (
    id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL REFERENCES revisions(id),
    page_id TEXT NOT NULL REFERENCES pages(id),
    page_number INTEGER NOT NULL CHECK(page_number > 0),
    element_type TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    raw_text TEXT,
    normalized_text TEXT,
    raw_payload_hash TEXT NOT NULL CHECK(length(raw_payload_hash) = 64),
    bbox_json TEXT,
    parser_order INTEGER NOT NULL CHECK(parser_order >= 0)
) STRICT;

CREATE TABLE IF NOT EXISTS clauses (
    id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL REFERENCES revisions(id),
    title TEXT NOT NULL,
    raw_text TEXT,
    normalized_text TEXT,
    review_status TEXT NOT NULL DEFAULT 'AUTOMATIC'
) STRICT;

CREATE TABLE IF NOT EXISTS tables (
    id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL REFERENCES revisions(id),
    page_number INTEGER NOT NULL CHECK(page_number > 0),
    bbox_json TEXT,
    raw_json TEXT NOT NULL,
    normalized_json TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS visuals (
    id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL REFERENCES revisions(id),
    page_number INTEGER NOT NULL CHECK(page_number > 0),
    kind TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
    bbox_json TEXT,
    duplicate_group TEXT NOT NULL,
    UNIQUE(revision_id, relative_path)
) STRICT;

CREATE TABLE IF NOT EXISTS links (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    UNIQUE(source_id, target_id, relation_type)
) STRICT;

CREATE TABLE IF NOT EXISTS review_flags (
    id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    code TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS snapshot_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS retrieval_records (
    evidence_id TEXT PRIMARY KEY,
    evidence_type TEXT NOT NULL,
    document_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    page_number INTEGER NOT NULL CHECK(page_number > 0),
    bbox_json TEXT NOT NULL,
    source_hash TEXT NOT NULL CHECK(length(source_hash) = 64),
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL
) STRICT;

CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
    evidence_id UNINDEXED,
    title,
    raw_text,
    normalized_text,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS retrieval_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS idx_elements_revision_page
    ON elements(revision_id, page_number, parser_order);
CREATE INDEX IF NOT EXISTS idx_clauses_revision ON clauses(revision_id);
CREATE INDEX IF NOT EXISTS idx_tables_revision_page ON tables(revision_id, page_number);
CREATE INDEX IF NOT EXISTS idx_visuals_revision_page ON visuals(revision_id, page_number);
CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_review_flags_evidence ON review_flags(evidence_id, status);
CREATE INDEX IF NOT EXISTS idx_retrieval_records_source
    ON retrieval_records(document_id, revision_id, page_number, evidence_type);
