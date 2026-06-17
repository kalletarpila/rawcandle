# eco legacy DB preflight: data/analysis.db

## Executive summary

Read-only Phase 3C preflight was run against `/home/kalle/projects/rawcandle/data/analysis.db`.

Result: `ECO_TABLES_FOUND`.

The database contains 16 old `eco_*` tables with 72,931 total rows. `PRAGMA integrity_check` returned `ok`, and `PRAGMA foreign_key_check` reported 0 violations. Based on this preflight, later cleanup appears technically feasible, but only as `CLEANUP_CANDIDATE_WITH_BACKUP_REQUIRED`.

No DB writes were performed. No tables were dropped. No backup was created in this step. Any cleanup requires a separate approved prompt with backup and rollback.

## Inspected DB

| Field | Value |
|---|---|
| DB path | `/home/kalle/projects/rawcandle/data/analysis.db` |
| DB exists | yes |
| DB size | 4,609,150,976 bytes |
| WAL observed | `/home/kalle/projects/rawcandle/data/analysis.db-wal` existed, 158M |
| SHM observed | `/home/kalle/projects/rawcandle/data/analysis.db-shm` existed, 320K |
| Open mode | SQLite read-only URI mode via `mode=ro` |

## Commands Run

```bash
git status --short
ls -lh /home/kalle/projects/rawcandle/data/analysis.db
ls -lh /home/kalle/projects/rawcandle/data/analysis.db-wal /home/kalle/projects/rawcandle/data/analysis.db-shm
PYTHONPATH=. python3 -m rawcandle.cli.preflight_eco_legacy_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db
PYTHONPATH=. python3 -m rawcandle.cli.preflight_eco_legacy_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db --format json
```

## Preflight Summary

| Field | Value |
|---|---|
| Status | `ECO_TABLES_FOUND` |
| Assessment | `CLEANUP_CANDIDATE_WITH_BACKUP_REQUIRED` |
| eco table count | 16 |
| total eco rows | 72,931 |
| integrity_check | `ok` |
| foreign_key_check violation count | 0 |
| page_count | 1,125,401 |
| freelist_count | 0 |

## eco Table Inventory

| Table | Row count |
|---|---:|
| `eco_classification_decision` | 2,362 |
| `eco_ecosystem` | 1 |
| `eco_entity` | 291 |
| `eco_entity_coverage` | 2,328 |
| `eco_entity_event` | 13,213 |
| `eco_entity_metric_value` | 43,772 |
| `eco_entity_window_snapshot` | 2,328 |
| `eco_quality_summary` | 16 |
| `eco_report_run` | 2 |
| `eco_report_window` | 4 |
| `eco_signal_observation` | 8,125 |
| `eco_signal_relevance` | 89 |
| `eco_taxonomy_entity_relation` | 382 |
| `eco_taxonomy_version` | 1 |
| `eco_watchlist` | 1 |
| `eco_watchlist_member` | 16 |

## Related Schema Objects

Related indexes were found for old `eco_*` tables. No related triggers or views were found.

| Type | Count |
|---|---:|
| Indexes | 56 |
| Triggers | 0 |
| Views | 0 |

### Related indexes

| Table | Index |
|---|---|
| `eco_classification_decision` | `idx_eco_classification_decision_entity_window` |
| `eco_classification_decision` | `idx_eco_classification_decision_priority` |
| `eco_classification_decision` | `idx_eco_classification_decision_run_window_type` |
| `eco_classification_decision` | `idx_eco_classification_decision_state` |
| `eco_classification_decision` | `idx_eco_classification_decision_status` |
| `eco_classification_decision` | `sqlite_autoindex_eco_classification_decision_1` |
| `eco_ecosystem` | `sqlite_autoindex_eco_ecosystem_1` |
| `eco_entity` | `idx_eco_entity_ecosystem_type_status` |
| `eco_entity` | `idx_eco_entity_ticker` |
| `eco_entity` | `sqlite_autoindex_eco_entity_1` |
| `eco_entity_coverage` | `idx_eco_entity_coverage_date_taxonomy_window_status` |
| `eco_entity_coverage` | `idx_eco_entity_coverage_ecosystem_status` |
| `eco_entity_coverage` | `idx_eco_entity_coverage_entity_date` |
| `eco_entity_coverage` | `sqlite_autoindex_eco_entity_coverage_1` |
| `eco_entity_event` | `idx_eco_entity_event_date_type` |
| `eco_entity_event` | `idx_eco_entity_event_ecosystem_type_status` |
| `eco_entity_event` | `idx_eco_entity_event_source_run_id` |
| `eco_entity_event` | `idx_eco_entity_event_taxonomy_entity_date` |
| `eco_entity_event` | `sqlite_autoindex_eco_entity_event_1` |
| `eco_entity_metric_value` | `idx_eco_entity_metric_value_date_taxonomy_window_metric` |
| `eco_entity_metric_value` | `idx_eco_entity_metric_value_ecosystem_metric` |
| `eco_entity_metric_value` | `idx_eco_entity_metric_value_entity_metric_date` |
| `eco_entity_metric_value` | `sqlite_autoindex_eco_entity_metric_value_1` |
| `eco_entity_window_snapshot` | `idx_eco_entity_window_snapshot_date_taxonomy_window` |
| `eco_entity_window_snapshot` | `idx_eco_entity_window_snapshot_ecosystem_window_status` |
| `eco_entity_window_snapshot` | `idx_eco_entity_window_snapshot_entity_date` |
| `eco_entity_window_snapshot` | `sqlite_autoindex_eco_entity_window_snapshot_1` |
| `eco_quality_summary` | `idx_eco_quality_summary_date_taxonomy_window_status` |
| `eco_quality_summary` | `idx_eco_quality_summary_ecosystem_scope_status` |
| `eco_quality_summary` | `idx_eco_quality_summary_scope_entity_date` |
| `eco_quality_summary` | `sqlite_autoindex_eco_quality_summary_1` |
| `eco_report_run` | `idx_eco_report_run_ecosystem_signal_date` |
| `eco_report_run` | `idx_eco_report_run_status_signal_date` |
| `eco_report_run` | `idx_eco_report_run_taxonomy_signal_date` |
| `eco_report_run` | `sqlite_autoindex_eco_report_run_1` |
| `eco_report_window` | `sqlite_autoindex_eco_report_window_1` |
| `eco_signal_observation` | `idx_eco_signal_observation_date_taxonomy_window_entity` |
| `eco_signal_observation` | `idx_eco_signal_observation_ecosystem_family_status` |
| `eco_signal_observation` | `idx_eco_signal_observation_entity_name_observed_date` |
| `eco_signal_observation` | `idx_eco_signal_observation_source_run_id` |
| `eco_signal_observation` | `sqlite_autoindex_eco_signal_observation_1` |
| `eco_signal_relevance` | `idx_eco_signal_relevance_assigned_at_utc` |
| `eco_signal_relevance` | `idx_eco_signal_relevance_label` |
| `eco_signal_relevance` | `idx_eco_signal_relevance_signal_observation_id` |
| `eco_signal_relevance` | `sqlite_autoindex_eco_signal_relevance_1` |
| `eco_taxonomy_entity_relation` | `idx_eco_taxonomy_relation_child` |
| `eco_taxonomy_entity_relation` | `idx_eco_taxonomy_relation_parent` |
| `eco_taxonomy_entity_relation` | `sqlite_autoindex_eco_taxonomy_entity_relation_1` |
| `eco_taxonomy_version` | `idx_eco_taxonomy_version_ecosystem_status` |
| `eco_taxonomy_version` | `sqlite_autoindex_eco_taxonomy_version_1` |
| `eco_watchlist` | `idx_eco_watchlist_ecosystem_status` |
| `eco_watchlist` | `sqlite_autoindex_eco_watchlist_1` |
| `eco_watchlist_member` | `idx_eco_watchlist_member_entity` |
| `eco_watchlist_member` | `idx_eco_watchlist_member_watchlist_status` |
| `eco_watchlist_member` | `sqlite_autoindex_eco_watchlist_member_1` |

## Integrity And Foreign Keys

| Check | Result |
|---|---|
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violation count | 0 |
| First violations | none |

No integrity or foreign-key issue was detected that would block planning a later backup-confirmed cleanup.

## Assessment

Assessment: `CLEANUP_CANDIDATE_WITH_BACKUP_REQUIRED`.

Reasoning:

- Old `eco_*` tables exist and contain data.
- Integrity check is clean.
- Foreign-key check reports no violations.
- No related triggers or views were found.
- Cleanup still requires a separate approved prompt, a verified backup, rollback instructions, and post-cleanup integrity checks.

## Recommended Next Step

Prepare a separate backup-confirmed DB cleanup prompt if the 72,931 old `eco_*` rows are no longer needed. That later prompt should define the exact backup path, table-drop SQL, integrity checks, rollback procedure, and whether `VACUUM` is explicitly out of scope.

No cleanup should be run from this document alone.
