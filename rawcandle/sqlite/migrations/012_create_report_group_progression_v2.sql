CREATE TABLE IF NOT EXISTS dc_report_ecosystem_window_change_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    group_scope TEXT NOT NULL CHECK (group_scope IN ('LAYER', 'SUBINDUSTRY', 'ECOSYSTEM', 'WATCHLIST', 'MARKET')),
    group_key TEXT NOT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    change_type TEXT NOT NULL CHECK (
        change_type IN (
            'IMPROVED',
            'DETERIORATED',
            'APPEARED',
            'DISAPPEARED',
            'UNCHANGED',
            'WORSENED',
            'RECOVERED',
            'ROTATED_IN',
            'ROTATED_OUT',
            'UNKNOWN'
        )
    ),
    previous_value REAL NULL,
    current_value REAL NULL,
    delta_value REAL NULL,
    delta_pct REAL NULL,
    rank_previous INTEGER NULL,
    rank_current INTEGER NULL,
    rank_delta INTEGER NULL,
    status TEXT NOT NULL CHECK (status IN ('OK', 'WARN', 'ERROR', 'MISSING', 'INCOMPLETE', 'UNKNOWN')),
    reason TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        run_id,
        signal_date,
        taxonomy_version,
        report_window,
        group_scope,
        group_key,
        change_type
    ),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE TABLE IF NOT EXISTS dc_report_group_overheat_progression_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    group_scope TEXT NOT NULL CHECK (group_scope IN ('LAYER', 'SUBINDUSTRY', 'ECOSYSTEM', 'WATCHLIST', 'MARKET')),
    group_key TEXT NOT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    overheat_status TEXT NOT NULL CHECK (overheat_status IN ('NONE', 'LOW', 'MODERATE', 'HIGH', 'EXTREME', 'UNKNOWN')),
    rotation_risk_status TEXT NOT NULL CHECK (
        rotation_risk_status IN ('NONE', 'LOW', 'MODERATE', 'HIGH', 'EXTREME', 'UNKNOWN')
    ),
    previous_overheat_score REAL NULL,
    current_overheat_score REAL NULL,
    overheat_delta REAL NULL,
    previous_rotation_risk_score REAL NULL,
    current_rotation_risk_score REAL NULL,
    rotation_risk_delta REAL NULL,
    progression_class TEXT NOT NULL CHECK (
        progression_class IN (
            'HEATING_UP',
            'COOLING_DOWN',
            'STABLE',
            'ROTATION_RISK_INCREASING',
            'ROTATION_RISK_DECREASING',
            'NORMALIZING',
            'UNKNOWN'
        )
    ),
    reason TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        run_id,
        signal_date,
        taxonomy_version,
        report_window,
        group_scope,
        group_key
    ),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE TABLE IF NOT EXISTS dc_report_group_relative_change_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    group_scope TEXT NOT NULL CHECK (group_scope IN ('LAYER', 'SUBINDUSTRY', 'ECOSYSTEM', 'WATCHLIST', 'MARKET')),
    group_key TEXT NOT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    metric_name TEXT NOT NULL,
    previous_value REAL NULL,
    current_value REAL NULL,
    delta_value REAL NULL,
    delta_pct REAL NULL,
    direction TEXT NOT NULL CHECK (direction IN ('IMPROVING', 'DETERIORATING', 'FLAT', 'MIXED', 'UNKNOWN')),
    relative_rank INTEGER NULL,
    relative_rank_delta INTEGER NULL,
    status TEXT NOT NULL CHECK (status IN ('OK', 'WARN', 'ERROR', 'MISSING', 'INCOMPLETE', 'UNKNOWN')),
    reason TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        run_id,
        signal_date,
        taxonomy_version,
        report_window,
        group_scope,
        group_key,
        metric_name
    ),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_report_ecosystem_window_change_v2_date_taxonomy_window_scope
ON dc_report_ecosystem_window_change_v2 (signal_date, taxonomy_version, report_window, group_scope);

CREATE INDEX IF NOT EXISTS idx_dc_report_ecosystem_window_change_v2_change_status
ON dc_report_ecosystem_window_change_v2 (signal_date, taxonomy_version, report_window, change_type, status);

CREATE INDEX IF NOT EXISTS idx_dc_report_group_overheat_progression_v2_date_taxonomy_window_scope
ON dc_report_group_overheat_progression_v2 (signal_date, taxonomy_version, report_window, group_scope);

CREATE INDEX IF NOT EXISTS idx_dc_report_group_overheat_progression_v2_progression
ON dc_report_group_overheat_progression_v2 (signal_date, taxonomy_version, report_window, progression_class);

CREATE INDEX IF NOT EXISTS idx_dc_report_group_relative_change_v2_date_taxonomy_window_scope
ON dc_report_group_relative_change_v2 (signal_date, taxonomy_version, report_window, group_scope);

CREATE INDEX IF NOT EXISTS idx_dc_report_group_relative_change_v2_metric_direction
ON dc_report_group_relative_change_v2 (signal_date, taxonomy_version, report_window, metric_name, direction);
