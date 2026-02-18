"""Enumerations shared across the Legacy Modernization platform."""

from enum import Enum


class AssetType(str, Enum):
    COBOL = "cobol"
    JCL = "jcl"
    MAP = "map"
    ASSEMBLER = "assembler"


class FeatureCategory(str, Enum):
    # COBOL
    FILE_IO = "file_io"
    CICS = "cics"
    DB2 = "db2"
    IMS = "ims"
    STRING_OP = "string_op"
    ARITHMETIC = "arithmetic"
    FLOW_CONTROL = "flow_control"
    COPYBOOK = "copybook"
    SPECIAL = "special"
    # JCL
    JOB_CARD = "job_card"
    EXEC_STEP = "exec_step"
    DD_STATEMENT = "dd_statement"
    DATASET = "dataset"
    PROCEDURE = "procedure"
    UTILITY = "utility"
    JES_CONTROL = "jes_control"
    CONDITIONAL = "conditional"
    GDG = "gdg"
    VSAM = "vsam"
    # MAP
    SCREEN_LAYOUT = "screen_layout"
    FIELD_DEFINITION = "field_definition"
    ATTRIBUTE = "attribute"
    CURSOR_CONTROL = "cursor_control"
    MAPSET_STRUCTURE = "mapset_structure"
    MAP_FIELD_LINK = "map_field_link"
    # ASM
    MACRO_USAGE = "macro_usage"
    REGISTER_USAGE = "register_usage"
    ADDRESSING = "addressing"
    BRANCH = "branch"
    SUPERVISOR_CALL = "supervisor_call"
    DSECT_STRUCTURE = "dsect_structure"
    DATA_DEFINITION = "data_definition"
    SYSTEM_MACRO = "system_macro"


class OpenFrameProduct(str, Enum):
    """OpenFrame 제품군 (11개)"""
    AIM_XSP = "aim_xsp"
    AIM_MSP = "aim_msp"
    OSC = "osc"
    OSI = "osi"
    ASM = "asm"
    COBOL_OSVS = "cobol_osvs"
    COBOL_ENT = "cobol_ent"
    COBOL_MVS = "cobol_mvs"
    BATCH = "batch"
    HIDB = "hidb"
    TACF = "tacf"


class ComplexityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SupportLevel(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    WORKAROUND = "workaround"


class EffortLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    COBOL_EXPERT = "cobol_expert"
    JCL_EXPERT = "jcl_expert"
    MAP_EXPERT = "map_expert"
    ASM_EXPERT = "asm_expert"
    LEGACY_KNOWLEDGE = "legacy_knowledge"
    REVIEWER = "reviewer"
    QA = "qa"
    E2E_TEST = "e2e_test"
    RISK_INTELLIGENCE = "risk_intelligence"
    COMPETITOR_INTELLIGENCE = "competitor_intelligence"


class AgentStatus(str, Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING_REVIEW = "waiting_review"
    ERROR = "error"
    COMPLETED = "completed"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    KNOWLEDGE_ENRICHMENT = "knowledge_enrichment"
    COMPATIBILITY_ANALYSIS = "compatibility_analysis"
    RISK_ASSESSMENT = "risk_assessment"
    REVIEWING = "reviewing"
    QA_VALIDATION = "qa_validation"
    E2E_TESTING = "e2e_testing"
    REPORT_GENERATION = "report_generation"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class MessageType(str, Enum):
    TASK = "task"
    RESULT = "result"
    STATUS_UPDATE = "status_update"
    CHANGE_REQUEST = "change_request"
    CHANGE_APPROVED = "change_approved"
    CHANGE_REJECTED = "change_rejected"
    REVIEW_REQUEST = "review_request"
    REVIEW_RESULT = "review_result"
    REANALYSIS = "reanalysis"
    QA_REQUEST = "qa_request"
    QA_PASS = "qa_pass"
    VETO = "veto"
    ESCALATION = "escalation"


class ChangeRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REANALYSIS_REQUIRED = "reanalysis_required"


class AuditAction(str, Enum):
    WORKSPACE_CREATED = "workspace_created"
    TASK_ASSIGNED = "task_assigned"
    FIELD_UPDATED = "field_updated"
    CHANGE_REQUEST_SUBMITTED = "change_request_submitted"
    CHANGE_REQUEST_RESOLVED = "change_request_resolved"
    REVIEW_COMPLETED = "review_completed"
    QA_VETOED = "qa_vetoed"
    QA_PASSED = "qa_passed"
    PIPELINE_STATE_CHANGED = "pipeline_state_changed"
    REANALYSIS_TRIGGERED = "reanalysis_triggered"
