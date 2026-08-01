CREATE TABLE IF NOT EXISTS ec_watchlist_reconciliation_audit (
    reconciliation_id INTEGER PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_code TEXT NULL,
    watchlist_id INTEGER NOT NULL,
    watchlist_code TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_member_count INTEGER NOT NULL,
    previous_member_count INTEGER NOT NULL,
    new_member_count INTEGER NOT NULL,
    added_count INTEGER NOT NULL,
    removed_count INTEGER NOT NULL,
    added_tickers_json TEXT NOT NULL,
    removed_tickers_json TEXT NOT NULL,
    invocation_source TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('APPLIED', 'FAILED')),
    error TEXT NULL,
    applied_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (watchlist_id) REFERENCES ec_watchlist (watchlist_id)
);

CREATE INDEX IF NOT EXISTS idx_ec_watchlist_reconciliation_audit_lookup
ON ec_watchlist_reconciliation_audit (
    ecosystem_id,
    watchlist_code,
    applied_at_utc
);
