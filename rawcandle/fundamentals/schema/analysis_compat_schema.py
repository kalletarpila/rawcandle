"""Current shared analysis schema retained for V2 and legacy-layout compatibility."""

LIFECYCLE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS lifecycle_revised_result (
    lifecycle_revised_result_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    security_id INTEGER,
    ticker TEXT,
    quarter_id INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter TEXT NOT NULL CHECK (fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    fiscal_sequence INTEGER NOT NULL,
    period_end TEXT NOT NULL,
    source_available_date TEXT,
    history_mode TEXT NOT NULL CHECK (history_mode = 'REVISED_HISTORY'),
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    source_input_fingerprint TEXT NOT NULL,
    raw_state TEXT NOT NULL,
    final_state TEXT,
    lifecycle_status TEXT NOT NULL,
    startup_profile TEXT,
    final_startup_profile TEXT,
    reason_code TEXT NOT NULL,
    transition_reason TEXT NOT NULL,
    missing_inputs_json TEXT NOT NULL,
    last_confirmed_state TEXT,
    candidate_state TEXT,
    candidate_count INTEGER NOT NULL CHECK (candidate_count IN (0,1)),
    revenue_growth_yoy_ttm REAL,
    ebit_margin_ttm REAL,
    ebit_margin_direction REAL,
    fcf_margin_ttm REAL,
    evidence_json TEXT NOT NULL,
    generated_at_utc TEXT NOT NULL,
    UNIQUE(company_id, fiscal_year, fiscal_quarter, model_fingerprint, history_mode)
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_revised_current
    ON lifecycle_revised_result(model_fingerprint, history_mode, company_id, fiscal_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_lifecycle_revised_class
    ON lifecycle_revised_result(model_fingerprint, history_mode, lifecycle_status, final_state, final_startup_profile);
"""

VALUATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS valuation_revised_result (
    valuation_revised_result_id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    security_id INTEGER,
    ticker TEXT,
    security_active INTEGER CHECK (security_active IN (0,1)),
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter TEXT NOT NULL CHECK (fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    fiscal_sequence INTEGER NOT NULL,
    quarter_id INTEGER NOT NULL,
    period_end TEXT NOT NULL,
    fundamental_available_date TEXT,
    price_date TEXT,
    price_age_calendar_days INTEGER,
    selected_price REAL,
    shares_outstanding REAL,
    market_cap REAL,
    cash REAL,
    total_debt REAL,
    net_debt REAL,
    enterprise_value REAL,
    ttm_ebit REAL,
    ttm_free_cashflow REAL,
    ttm_net_income_common REAL,
    ebit_yield REAL,
    ebit_points REAL,
    fcf_yield REAL,
    fcf_points REAL,
    earnings_yield REAL,
    earnings_points REAL,
    total_valuation_score REAL,
    valuation_status TEXT NOT NULL CHECK (valuation_status IN ('VALUATION_FULL','VALUATION_NOT_READY','VALUATION_NOT_APPLICABLE')),
    reason_code TEXT NOT NULL,
    applicability_classification TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    engine_result_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    history_mode TEXT NOT NULL CHECK (history_mode='REVISED_HISTORY'),
    calculated_at_utc TEXT NOT NULL,
    UNIQUE(company_id,fiscal_year,fiscal_quarter,model_fingerprint,history_mode)
);
CREATE INDEX IF NOT EXISTS idx_valuation_revised_current
    ON valuation_revised_result(model_fingerprint,history_mode,company_id,fiscal_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_valuation_revised_status
    ON valuation_revised_result(model_fingerprint,history_mode,valuation_status,reason_code);
"""

DELTA_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fundamental_delta_package (
    package_id INTEGER PRIMARY KEY,
    persistence_version TEXT NOT NULL CHECK (persistence_version='V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V2'),
    layout_fingerprint TEXT NOT NULL CHECK (layout_fingerprint='001d4d86ff3f279b2c44f497d536883a8f63bf281ee34c9086881e14635997c0'),
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    semantic_mode TEXT NOT NULL CHECK (semantic_mode='CURRENTLY_REVISED_FUNDAMENTAL_HISTORY_DELTA'),
    history_mode TEXT NOT NULL CHECK (history_mode='REVISED_HISTORY'),
    score_model_fingerprint TEXT NOT NULL,
    fundamental_source_fingerprint TEXT NOT NULL,
    fundamental_result_fingerprint TEXT NOT NULL,
    lifecycle_model_fingerprint TEXT NOT NULL,
    lifecycle_source_fingerprint TEXT NOT NULL,
    lifecycle_result_fingerprint TEXT NOT NULL,
    valuation_model_fingerprint TEXT NOT NULL,
    valuation_source_fingerprint TEXT NOT NULL,
    valuation_result_fingerprint TEXT NOT NULL,
    economic_package_fingerprint TEXT NOT NULL,
    physical_content_fingerprint TEXT NOT NULL,
    total_row_count INTEGER NOT NULL CHECK (total_row_count>=0),
    component_row_count INTEGER NOT NULL CHECK (component_row_count>=0),
    applied_at_utc TEXT NOT NULL,
    UNIQUE(model_fingerprint,history_mode)
);

CREATE TABLE IF NOT EXISTS fundamental_delta_status (
    status_id INTEGER PRIMARY KEY,
    status_text TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS fundamental_delta_reason (
    reason_id INTEGER PRIMARY KEY,
    reason_text TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS fundamental_delta_component_type (
    component_id INTEGER PRIMARY KEY,
    component_name TEXT NOT NULL UNIQUE,
    maximum_points REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS fundamental_delta_result (
    endpoint_id INTEGER PRIMARY KEY,
    package_id INTEGER NOT NULL REFERENCES fundamental_delta_package(package_id),
    company_id INTEGER NOT NULL,
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER NOT NULL CHECK (fiscal_quarter BETWEEN 1 AND 4),
    fiscal_sequence INTEGER NOT NULL,
    current_available_date TEXT NOT NULL,
    current_score_result_id INTEGER NOT NULL,
    qoq_prior_score_result_id INTEGER,
    qoq_delta REAL,
    qoq_status_id INTEGER NOT NULL REFERENCES fundamental_delta_status(status_id),
    qoq_reason_id INTEGER NOT NULL REFERENCES fundamental_delta_reason(reason_id),
    two_quarter_prior_score_result_id INTEGER,
    two_quarter_delta REAL,
    two_quarter_status_id INTEGER NOT NULL REFERENCES fundamental_delta_status(status_id),
    two_quarter_reason_id INTEGER NOT NULL REFERENCES fundamental_delta_reason(reason_id),
    yoy_prior_score_result_id INTEGER,
    yoy_delta REAL,
    yoy_status_id INTEGER NOT NULL REFERENCES fundamental_delta_status(status_id),
    yoy_reason_id INTEGER NOT NULL REFERENCES fundamental_delta_reason(reason_id),
    reconciliation_status INTEGER NOT NULL CHECK (reconciliation_status IN (0,1)),
    maximum_reconciliation_error REAL,
    engine_result_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    UNIQUE(package_id,company_id,fiscal_sequence)
);

CREATE TABLE IF NOT EXISTS fundamental_delta_component (
    endpoint_id INTEGER NOT NULL REFERENCES fundamental_delta_result(endpoint_id) ON DELETE CASCADE,
    component_id INTEGER NOT NULL REFERENCES fundamental_delta_component_type(component_id),
    current_points REAL,
    qoq_prior_points REAL,
    qoq_delta REAL,
    qoq_status_id INTEGER NOT NULL REFERENCES fundamental_delta_status(status_id),
    qoq_reason_id INTEGER NOT NULL REFERENCES fundamental_delta_reason(reason_id),
    two_quarter_prior_points REAL,
    two_quarter_delta REAL,
    two_quarter_status_id INTEGER NOT NULL REFERENCES fundamental_delta_status(status_id),
    two_quarter_reason_id INTEGER NOT NULL REFERENCES fundamental_delta_reason(reason_id),
    yoy_prior_points REAL,
    yoy_delta REAL,
    yoy_status_id INTEGER NOT NULL REFERENCES fundamental_delta_status(status_id),
    yoy_reason_id INTEGER NOT NULL REFERENCES fundamental_delta_reason(reason_id),
    result_fingerprint TEXT NOT NULL,
    PRIMARY KEY(endpoint_id,component_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_fundamental_delta_current
    ON fundamental_delta_result(package_id,company_id,fiscal_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_fundamental_delta_cross_section
    ON fundamental_delta_result(package_id,fiscal_year,fiscal_quarter,company_id);
"""

DIAGNOSTIC_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS diagnostic_flag_package(
 package_id INTEGER PRIMARY KEY,persistence_version TEXT NOT NULL,layout_fingerprint TEXT NOT NULL,
 model_version TEXT NOT NULL,model_fingerprint TEXT NOT NULL,semantic_mode TEXT NOT NULL,history_mode TEXT NOT NULL,
 evidence_schema_version TEXT NOT NULL,source_fingerprint TEXT NOT NULL,economic_result_fingerprint TEXT NOT NULL,
 physical_content_fingerprint TEXT NOT NULL,endpoint_count INTEGER NOT NULL,evaluation_count INTEGER NOT NULL,
 applied_at_utc TEXT NOT NULL,UNIQUE(model_fingerprint,history_mode));
CREATE TABLE IF NOT EXISTS diagnostic_flag_type(flag_id INTEGER PRIMARY KEY,flag_name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS diagnostic_flag_status(status_id INTEGER PRIMARY KEY,status_text TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS diagnostic_flag_reason(reason_id INTEGER PRIMARY KEY,reason_text TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS diagnostic_flag_source_status(source_status_id INTEGER PRIMARY KEY,source_status_text TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS diagnostic_flag_applicability(applicability_id INTEGER PRIMARY KEY,applicability_text TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS diagnostic_flag_endpoint(
 endpoint_id INTEGER PRIMARY KEY,package_id INTEGER NOT NULL REFERENCES diagnostic_flag_package(package_id),company_id INTEGER NOT NULL,
 quarter_id INTEGER NOT NULL,fiscal_year INTEGER NOT NULL,fiscal_quarter INTEGER NOT NULL CHECK(fiscal_quarter BETWEEN 1 AND 4),
 fiscal_sequence INTEGER NOT NULL,period_end TEXT NOT NULL,source_available_date TEXT,ttm_available_date TEXT,
 source_status_id INTEGER REFERENCES diagnostic_flag_source_status(source_status_id),result_fingerprint TEXT NOT NULL,
 UNIQUE(package_id,company_id,fiscal_sequence));
CREATE TABLE IF NOT EXISTS diagnostic_flag_evaluation(
 endpoint_id INTEGER NOT NULL REFERENCES diagnostic_flag_endpoint(endpoint_id) ON DELETE CASCADE,
 flag_id INTEGER NOT NULL REFERENCES diagnostic_flag_type(flag_id),status_id INTEGER NOT NULL REFERENCES diagnostic_flag_status(status_id),
 reason_id INTEGER NOT NULL REFERENCES diagnostic_flag_reason(reason_id),applicability_id INTEGER REFERENCES diagnostic_flag_applicability(applicability_id),
 comparison_quarter_id INTEGER,effective_available_date TEXT,triggered INTEGER CHECK(triggered IN(0,1) OR triggered IS NULL),
 bool_mask INTEGER NOT NULL DEFAULT 0,
 n01 REAL,n02 REAL,n03 REAL,n04 REAL,n05 REAL,n06 REAL,n07 REAL,n08 REAL,n09 REAL,n10 REAL,n11 REAL,n12 REAL,n13 REAL,n14 REAL,n15 REAL,n16 REAL,result_fingerprint TEXT NOT NULL,
 PRIMARY KEY(endpoint_id,flag_id)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_diagnostic_flag_current ON diagnostic_flag_endpoint(package_id,company_id,fiscal_sequence DESC);
CREATE INDEX IF NOT EXISTS idx_diagnostic_flag_cross_section ON diagnostic_flag_endpoint(package_id,fiscal_year,fiscal_quarter,company_id);
CREATE INDEX IF NOT EXISTS idx_diagnostic_flag_filter ON diagnostic_flag_evaluation(flag_id,status_id,endpoint_id);
"""

RELATIVE_POSITION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS relative_position_schema_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton=1),
    schema_version TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relative_position_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    semantic_mode TEXT NOT NULL CHECK (semantic_mode='CURRENT_REVISED_SNAPSHOT'),
    snapshot_date TEXT NOT NULL,
    calculation_source_fingerprint TEXT NOT NULL,
    source_content_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('WRITING','COMPLETE')),
    result_row_count INTEGER NOT NULL CHECK (result_row_count>=0),
    coverage_row_count INTEGER NOT NULL CHECK (coverage_row_count>=0),
    ready_row_count INTEGER NOT NULL CHECK (ready_row_count>=0),
    created_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    UNIQUE(model_fingerprint,source_content_fingerprint)
);

CREATE TABLE IF NOT EXISTS relative_position_active_snapshot (
    model_fingerprint TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL UNIQUE
        REFERENCES relative_position_snapshot(snapshot_id) ON DELETE RESTRICT,
    activated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relative_position_result (
    relative_position_result_id INTEGER PRIMARY KEY,
    snapshot_id TEXT NOT NULL
        REFERENCES relative_position_snapshot(snapshot_id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL,
    security_id INTEGER,
    ticker TEXT,
    measure TEXT NOT NULL CHECK (measure IN ('FUNDAMENTAL_SCORE','ABSOLUTE_VALUATION_SCORE')),
    peer_scope TEXT NOT NULL CHECK (peer_scope IN ('UNIVERSE','SECTOR','INDUSTRY','ECOSYSTEM')),
    peer_group_id TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    source_observation_date TEXT NOT NULL,
    source_score REAL NOT NULL CHECK (source_score>=0 AND source_score<=100),
    percentile REAL CHECK (percentile IS NULL OR (percentile>=0 AND percentile<=100)),
    rank_low INTEGER NOT NULL CHECK (rank_low>=1),
    rank_high INTEGER NOT NULL CHECK (rank_high>=rank_low),
    average_rank REAL NOT NULL,
    peer_count INTEGER NOT NULL CHECK (peer_count>=1),
    tie_count INTEGER NOT NULL CHECK (tie_count>=1),
    result_status TEXT NOT NULL CHECK (result_status IN ('RELATIVE_POSITION_READY','PEER_GROUP_TOO_SMALL')),
    reason_code TEXT NOT NULL,
    model_version TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    UNIQUE(snapshot_id,company_id,measure,peer_scope,peer_group_id)
);

CREATE TABLE IF NOT EXISTS relative_position_coverage (
    relative_position_coverage_id INTEGER PRIMARY KEY,
    snapshot_id TEXT NOT NULL
        REFERENCES relative_position_snapshot(snapshot_id) ON DELETE CASCADE,
    source_observation_id TEXT NOT NULL,
    company_id INTEGER,
    measure TEXT NOT NULL CHECK (measure IN ('FUNDAMENTAL_SCORE','ABSOLUTE_VALUATION_SCORE')),
    peer_scope TEXT NOT NULL CHECK (peer_scope IN ('UNIVERSE','SECTOR','INDUSTRY','ECOSYSTEM')),
    peer_group_id TEXT NOT NULL DEFAULT '',
    coverage_status TEXT NOT NULL CHECK (coverage_status IN (
        'RELATIVE_POSITION_READY','SOURCE_MEASURE_NOT_ELIGIBLE',
        'PEER_CLASSIFICATION_MISSING','NOT_ECOSYSTEM_MEMBER',
        'PEER_GROUP_TOO_SMALL','INVALID_SOURCE_VALUE','IDENTITY_MAPPING_UNRESOLVED'
    )),
    reason_code TEXT NOT NULL,
    peer_count INTEGER CHECK (peer_count IS NULL OR peer_count>=0),
    UNIQUE(snapshot_id,source_observation_id,measure,peer_scope,peer_group_id)
);

CREATE TABLE IF NOT EXISTS relative_position_refresh_audit (
    refresh_audit_id INTEGER PRIMARY KEY,
    model_fingerprint TEXT NOT NULL,
    checked_at_utc TEXT NOT NULL,
    requested_snapshot_date TEXT NOT NULL,
    calculation_source_fingerprint TEXT NOT NULL,
    source_content_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('ACTIVATED','NO_CHANGE')),
    active_snapshot_id TEXT NOT NULL
        REFERENCES relative_position_snapshot(snapshot_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_relative_position_snapshot_model
    ON relative_position_snapshot(model_fingerprint,status,created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_relative_position_result_company
    ON relative_position_result(snapshot_id,company_id,measure,peer_scope);
CREATE INDEX IF NOT EXISTS idx_relative_position_result_group
    ON relative_position_result(snapshot_id,measure,peer_scope,peer_group_id,company_id);
CREATE INDEX IF NOT EXISTS idx_relative_position_coverage_company
    ON relative_position_coverage(snapshot_id,company_id,measure,peer_scope);
CREATE INDEX IF NOT EXISTS idx_relative_position_audit_model
    ON relative_position_refresh_audit(model_fingerprint,refresh_audit_id DESC);
"""

RELATIVE_POSITION_SCHEMA_VERSION = "V4_RELATIVE_POSITION_CURRENT_SNAPSHOT_V1"
