"""Stable table and layout identities shared by the current V2 package."""


class DeltaLayout:
    PERSISTENCE_VERSION = "V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V2"
    LAYOUT_FINGERPRINT = "001d4d86ff3f279b2c44f497d536883a8f63bf281ee34c9086881e14635997c0"
    SEMANTIC_MODE = "CURRENTLY_REVISED_FUNDAMENTAL_HISTORY_DELTA"
    PACKAGE_TABLE = "fundamental_delta_package"
    STATUS_TABLE = "fundamental_delta_status"
    REASON_TABLE = "fundamental_delta_reason"
    COMPONENT_TYPE_TABLE = "fundamental_delta_component_type"
    TOTAL_TABLE = "fundamental_delta_result"
    COMPONENT_TABLE = "fundamental_delta_component"


class DiagnosticLayout:
    PACKAGE_TABLE = "diagnostic_flag_package"
    FLAG_TABLE = "diagnostic_flag_type"
    STATUS_TABLE = "diagnostic_flag_status"
    REASON_TABLE = "diagnostic_flag_reason"
    SOURCE_STATUS_TABLE = "diagnostic_flag_source_status"
    APPLICABILITY_TABLE = "diagnostic_flag_applicability"
    ENDPOINT_TABLE = "diagnostic_flag_endpoint"
    EVALUATION_TABLE = "diagnostic_flag_evaluation"
