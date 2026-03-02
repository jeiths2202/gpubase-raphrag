"""
IMS Pipeline Configuration
제품 매핑, 경로, 임베딩/Neo4j 상수
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env 파일 로드 (프로젝트 루트)
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")

# ── 경로 ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "uploads" / "ims_issues"
DEFAULT_CSV = PROJECT_ROOT / "SearchIssue_template.csv"
DEFAULT_CREDENTIALS = PROJECT_ROOT / "scripts" / "ims_login.json"

# ── IMS 서버 ──────────────────────────────────────────────────────
IMS_BASE_URL = os.getenv("IMS_BASE_URL", "https://ims.tmaxsoft.com")
IMS_LOGIN_PATH = "/tody/auth/login.do"
IMS_ISSUE_VIEW_PATH = "/tody/ims/issue/issueView.do"

# ── BGE-M3 임베딩 ─────────────────────────────────────────────────
BGE_M3_URL = os.getenv("BGE_M3_BASE_URL", "http://192.168.8.11:12801")
EMBEDDING_MODEL = "bge-m3"
EMBEDDING_DIM = 1024
EMBEDDING_BATCH_SIZE = 64
EMBEDDING_TIMEOUT = 30.0

# ── Neo4j ─────────────────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# ── 크롤링 ────────────────────────────────────────────────────────
DEFAULT_CONCURRENCY = 5
CRAWL_TIMEOUT = 60  # seconds per request
REQUEST_DELAY = 0.5  # seconds between requests (polite crawling)

# ── IMS 제품 → product_id 매핑 ────────────────────────────────────
IMS_PRODUCT_TO_PRODUCT_ID: dict[str, str] = {
    "OpenFrame AIM": "openframe_aim",
    "OpenFrame ASM": "ofasm_4",
    "OpenFrame Base": "mvs_openframe_7.1",
    "OpenFrame Batch": "mvs_openframe_7.1",
    "OpenFrame COBOL": "ofcobol_4",
    "OpenFrame Common": "openframe_common",
    "OpenFrame GW": "openframe_gw",
    "OpenFrame HiDB": "openframe_hidb",
    "OpenFrame ISPF": "openframe_ispf",
    "OpenFrame Manager": "openframe_manager",
    "OpenFrame Map GUI Editor": "openframe_mapeditor",
    "OpenFrame Miner": "openframe_miner",
    "OpenFrame OSC": "mvs_openframe_7.1",
    "OpenFrame OSI": "openframe_osi",
    "OpenFrame OpenStudio Web": "openframe_studio_web",
    "OpenFrame PLI": "openframe_pli",
    "OpenFrame Studio": "openframe_studio",
    "OpenFrame TACF": "openframe_tacf",
    "ProSort": "prosort",
    "ProTrieve": "protrieve",
}

# CSV 컬럼 인덱스 (헤더 없는 CSV)
CSV_COLUMNS = [
    "ims_id",       # 0: Issue Number (352305)
    "category",     # 1: Technical Support / Enhancement Request / Binary Request
    "product",      # 2: OpenFrame COBOL
    "version",      # 3: 4, 7.3
    "module",       # 4: General, JCL, NDB
    "subject",      # 5: Issue title
    "link",         # 6: 바로가기 (link placeholder)
    "customer",     # 7: Company name
    "organization", # 8: Department/Project
    "reporter",     # 9: Reporter name
    "issued_date",  # 10: Created date
    "assignee",     # 11: Assignee name
    "assigned_date",# 12: Assigned date
    "status",       # 13: Open, Assigned, Resolved, Closed, New
    "col_14",       # 14: (empty or unknown)
    "priority",     # 15: N/A, General
    "resolution",   # 16: NONE, etc.
    "resolved_date",# 17: Resolved date
    "col_18",       # 18: (empty)
    "handler",      # 19: Handler name
    "handler_grade",# 20: Handler grade
    "last_updated", # 21: Last updated date
    "col_22",       # 22: Y/N flag
    "col_23",       # 23: (empty)
    "col_24",       # 24: (empty)
    "col_25",       # 25: resolved date 2
    "col_26",       # 26: (empty)
    "col_27",       # 27: Y/N flag
    "col_28",       # 28: (empty)
    "col_29",       # 29: (empty)
    "col_30",       # 30: (empty)
]
