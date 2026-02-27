"""설정 모듈

ChatGPT-Quality Pipeline 개선:
- Windows/Linux 크로스 플랫폼 경로 지원
- 환경변수 또는 프로젝트 루트 기준 자동 경로 탐지
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List


def _get_project_root() -> Path:
    """프로젝트 루트 경로 탐지"""
    # 현재 파일에서 상위로 올라가면서 CLAUDE.md 또는 docker-compose.yml 찾기
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "CLAUDE.md").exists() or (parent / "docker-compose.yml").exists():
            return parent
    # 기본값: 현재 작업 디렉토리
    return Path.cwd()


def _resolve_path(env_var: str, default_relative: str, default_linux: str) -> Path:
    """환경변수 또는 기본 경로 반환"""
    # 1. 환경변수 확인
    if env_var in os.environ:
        return Path(os.environ[env_var])

    # 2. 프로젝트 상대 경로 확인
    project_root = _get_project_root()
    relative_path = project_root / default_relative
    if relative_path.exists():
        return relative_path

    # 3. Linux 기본 경로 확인
    linux_path = Path(default_linux)
    if linux_path.exists():
        return linux_path

    # 4. 상대 경로 반환 (존재하지 않아도)
    return relative_path


@dataclass
class ProcessorConfig:
    """매뉴얼 프로세서 설정"""

    # 경로 설정 (크로스 플랫폼 지원)
    manuals_dir: Path = field(default_factory=lambda: _resolve_path(
        "KMS_MANUALS_DIR", "uploads/manuals", "/opt/kms/uploads/manuals"
    ))
    summaries_dir: Path = field(default_factory=lambda: _resolve_path(
        "KMS_SUMMARIES_DIR", "uploads/summaries", "/opt/kms/uploads/summaries"
    ))

    # 파일명 패턴 (정규식)
    # OF_<Component>_<Platform>_<Version>_<GuideType>_<DocVersion>_<Language>.pdf
    filename_pattern: str = (
        r"(?P<prefix>OF|OFManager|Tibero|Tmax)_"
        r"(?P<component>[A-Za-z]+)_"
        r"(?:(?P<platform>XSP|MSP|MVS)_)?"
        r"(?P<version>[\d.]+)_"
        r"(?P<guide_type>[A-Za-z-]+)_"
        r"v(?P<doc_version>[\d.]+)_"
        r"(?P<language>ja|jp|en)\.pdf"
    )

    # 에러 코드 범위 매핑
    error_code_modules: Dict[str, Dict] = field(default_factory=lambda: {
        # BASE 모듈
        "Non-VSAM": {"range": (0, 999), "prefix": "BASE"},
        "TSAM": {"range": (1000, 1999), "prefix": "BASE"},
        "DSIO": {"range": (2000, 2999), "prefix": "BASE"},
        "ICF": {"range": (3000, 3999), "prefix": "BASE"},
        "AMS": {"range": (4000, 4999), "prefix": "BASE"},
        "DSALC": {"range": (5000, 5999), "prefix": "BASE"},
        "VOLM": {"range": (6000, 6999), "prefix": "BASE"},
        "LOCKM": {"range": (7000, 7999), "prefix": "BASE"},
        "PGMDD": {"range": (8000, 8999), "prefix": "BASE"},
        "AMSX": {"range": (10000, 10999), "prefix": "BASE"},
        "SMS": {"range": (11000, 11999), "prefix": "BASE"},
        "DSCOM": {"range": (12000, 12999), "prefix": "BASE"},
        "CPMLIB": {"range": (15000, 15999), "prefix": "BASE"},
        "SAF": {"range": (17000, 17999), "prefix": "BASE"},
        "OFCOM": {"range": (22000, 22999), "prefix": "BASE"},
        "SAFX": {"range": (23000, 23999), "prefix": "BASE"},
        "SAFO": {"range": (24000, 24999), "prefix": "BASE"},
        "SAF_BAT": {"range": (26000, 26999), "prefix": "BASE"},
        "MEMM": {"range": (27000, 27999), "prefix": "BASE"},
        "TLIC": {"range": (28000, 28999), "prefix": "BASE"},
        "TTREE": {"range": (29000, 29999), "prefix": "BASE"},
        "SVRCOM": {"range": (32000, 32999), "prefix": "BASE"},
        "CONSOLE": {"range": (34000, 34499), "prefix": "BASE"},
        "COMMAND": {"range": (34500, 34999), "prefix": "BASE"},
        "SPIO": {"range": (36000, 36999), "prefix": "BASE"},
        "SMF": {"range": (93000, 93999), "prefix": "BASE"},
        # BATCH 모듈
        "TJES": {"range": (9000, 9999), "prefix": "BATCH"},
        "SPOOL": {"range": (13000, 13999), "prefix": "BATCH"},
        "MVSSYS": {"range": (16000, 16999), "prefix": "BATCH"},
        "TSO": {"range": (92000, 92999), "prefix": "BATCH"},
        # TACF 모듈
        "TACF": {"range": (18000, 18999), "prefix": "TACF"},
        # AIM 모듈
        "PSAM": {"range": (21000, 21999), "prefix": "AIM"},
        "AIMCOM": {"range": (80000, 80999), "prefix": "AIM"},
        "AIMACP": {"range": (82000, 82999), "prefix": "AIM"},
        "AIMCTL": {"range": (84000, 84099), "prefix": "AIM"},
        "AIMAIS": {"range": (84100, 84999), "prefix": "AIM"},
        "AIMSMR": {"range": (85000, 85999), "prefix": "AIM"},
        "AIMCMD": {"range": (86000, 86999), "prefix": "AIM"},
        "AIM": {"range": (87000, 87999), "prefix": "AIM"},
        "ADL": {"range": (88000, 88099), "prefix": "AIM"},
        "AIMTOOL": {"range": (88000, 88099), "prefix": "AIM"},
        "DDMS": {"range": (89000, 89999), "prefix": "AIM"},
        # NDB 모듈
        "NDB": {"range": (38000, 38999), "prefix": "NDB"},
        "NDBMETA": {"range": (40000, 40999), "prefix": "NDB"},
        "NDBRSTD": {"range": (99000, 99999), "prefix": "NDB"},
    })

    # 가이드 타입 분류
    guide_types: Dict[str, str] = field(default_factory=lambda: {
        "Error-Reference-Guide": "error",
        "Installation-Guide": "installation",
        "Configuration-Guide": "configuration",
        "User-Guide": "user",
        "Administrator-Guide": "admin",
        "Developer-Guide": "developer",
        "Migration-Guide": "migration",
        "Tool-Reference-Guide": "tool",
        "Utility-Reference-Guide": "utility",
        "JCL-Reference-Guide": "jcl",
        "Base-Guide": "overview",
        "Batch-Guide": "overview",
        "TJES-Guide": "overview",
        "Dataset-Guide": "overview",
        "NDB-Guide": "overview",
        "RDBII-Guide": "overview",
        "Sort-Utility-Guide": "utility",
        "IPF-Reference-Guide": "reference",
        "Command-Reference-Guide": "command",
        "Resource-Guide": "resource",
        "Resource-Definition-Guide": "resource",
        "System-Definition-Guide": "system",
        "TSO-Administrator-Guide": "admin",
        "WebTerminal-Guide": "user",
        "Language-Reference-Guide": "language",
        "SQL-Reference-Guide": "sql",
        "Reference-Guide": "reference",
    })

    # 제품 분류
    products: Dict[str, Dict] = field(default_factory=lambda: {
        "Base": {
            "name": "OpenFrame Base",
            "description": "OpenFrame基盤製品",
            "components": ["TSAM", "DSIO", "ICF", "AMS", "DSALC", "VOLM"]
        },
        "Batch": {
            "name": "OpenFrame Batch",
            "description": "バッチ処理システム",
            "components": ["TJES", "tjclrun", "obmjschd"]
        },
        "TACF": {
            "name": "OpenFrame TACF",
            "description": "セキュリティ製品",
            "components": ["SAF"]
        },
        "AIM": {
            "name": "OpenFrame AIM",
            "description": "Application Integration Module",
            "components": ["PSAM", "AIMCOM", "AIMACP", "AIMCTL"]
        },
        "GW": {
            "name": "OpenFrame Gateway",
            "description": "Webターミナル",
            "components": []
        },
        "OSC": {
            "name": "OpenFrame OSC",
            "description": "Online System for CICS",
            "components": []
        },
        "OSI": {
            "name": "OpenFrame OSI",
            "description": "Online System for IMS",
            "components": []
        },
        "NDB": {
            "name": "OpenFrame NDB",
            "description": "Network Database",
            "components": []
        },
        "COBOL": {
            "name": "OpenFrame COBOL",
            "description": "COBOLコンパイラ",
            "components": []
        },
        "ASM": {
            "name": "OpenFrame Assembler",
            "description": "アセンブラ",
            "components": []
        },
        "Manager": {
            "name": "OpenFrame Manager",
            "description": "管理ツール",
            "components": []
        },
    })

    # 지원 언어
    languages: Dict[str, str] = field(default_factory=lambda: {
        "ja": "日本語",
        "jp": "日本語",
        "en": "English",
        "ko": "한국어",
    })

    # 학습 데이터 출력 경로
    training_output_dir: str = "uploads/training/v10"

    # I-01: PDF 중복 제거 전략
    # "largest" = 같은 컴포넌트+가이드 유형 중 가장 큰 PDF만 사용
    pdf_dedup_strategy: str = "largest"

    # I-04: 소량 제품 증강 최소 레코드 수
    augmentation_min_records: int = 100


# 기본 설정 인스턴스
config = ProcessorConfig()

# ============================================
# 디렉토리명 → Multi-LoRA 제품 ID 매핑
# ============================================
DIRECTORY_TO_PRODUCT = {
    "MVS_Openframe 7.1_v3.1.3_JP": "openframe_common_v2",
    "MSP_Openframe 7.3_v2.1.1_JP": "openframe_common_v2",
    "XSP_Openframe 7.3_v3.2.1_JP": "openframe_common_v2",
    "VOS3_Openframe 2.0 _v2.1.1 _JP": "openframe_vos3_v2",
    "Tibero 7 FixSet01 Manual Set v2.1.1_jp": "tibero7_v2",
    "Tmax_6.0_v2.1.1_JP": "tmax_v2",
    "JEUS_8.5_v2.1.1_KR": "jeus_v2",
    "JEUS_8_v2.1.1_JP": "jeus_v2",
    "OFCOBOL_4_v3.1.2_JP": "ofcobol_v2",
    "OFAsm_4_v3.1.2_JP": "ofasm_v2",
    "OFGW_7_v2.1.3_JP": "openframe_gateway_v2",
    "OFManager_7.2_v3.1.2_JP": "ofmanager_v2",
    "OFMiner_7Fix1_v2.1.5_JP": "ofminer_v2",
    "OFPli_3_v2.1.2_JP": "ofpli_v2",
    "OFStudio_7_v2.1.1_JP": "ofstudio_v2",
    "ProSort_2SP3_v2.1.3_JP": "prosort_v2",
    "ProSync_FS01_JP": "prosync_v2",
    "ProTrieve_v2_1_JP": "protrieve_v2",
    "WebtoB_5Fix2_v2.1.3_JP": "webtob_v2",
}

# ============================================
# PDF 파일명 컴포넌트 → 제품 ID 매핑
# MVS/MSP/XSP 디렉토리 내 PDF는 파일명으로 컴포넌트 구분
# 예: OF_Base_7.1_Base-Guide_v3.1.2_jp.pdf → "Base" → openframe_base_v2
# ============================================
PDF_COMPONENT_TO_PRODUCT = {
    "Base": "openframe_base_v2",
    "HiDB": "openframe_hidb_v2",
    "AIM": "openframe_aim_v2",
    "Batch": "openframe_batch_v2",
    "OSC": "openframe_osc_v2",
    "OSI": "openframe_osi_v2",
    "TACF": "openframe_tacf_v2",
    "GW": "openframe_gateway_v2",
    "Manager": "ofmanager_v2",
    "NDB": "openframe_ndb_v2",
    "Common": "openframe_common_v2",
}

# 컴포넌트 분리 대상 디렉토리 (이 디렉토리들은 PDF 파일명으로 product_id 결정)
COMPONENT_SPLIT_DIRS = {
    "MVS_Openframe 7.1_v3.1.3_JP",
    "MSP_Openframe 7.3_v2.1.1_JP",
    "XSP_Openframe 7.3_v3.2.1_JP",
}

# 디렉토리명 → 언어
DIRECTORY_LANGUAGE = {
    "JEUS_8.5_v2.1.1_KR": "ko",
}

# 제품별 시스템 프롬프트
PRODUCT_SYSTEM_PROMPTS = {
    "openframe_common_v2": {
        "ja": "あなたはOpenFrame専門のテクニカルアシスタントです。OpenFrameに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame 전문 기술 어시스턴트입니다. OpenFrame에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame technical expert assistant. Answer questions about OpenFrame accurately.",
    },
    "openframe_batch_v2": {
        "ja": "あなたはOpenFrame Batch専門のテクニカルアシスタントです。バッチ処理に関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame Batch 전문 기술 어시스턴트입니다. 배치 처리에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame Batch technical expert assistant. Answer questions about batch processing accurately.",
    },
    "openframe_vos3_v2": {
        "ja": "あなたはOpenFrame VOS3専門のテクニカルアシスタントです。VOS3に関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame VOS3 전문 기술 어시스턴트입니다. VOS3에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame VOS3 technical expert assistant. Answer questions about VOS3 accurately.",
    },
    "tibero7_v2": {
        "ja": "あなたはTibero専門のテクニカルアシスタントです。Tiberoに関する質問に正確に回答してください。",
        "ko": "당신은 Tibero 전문 기술 어시스턴트입니다. Tibero에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a Tibero technical expert assistant. Answer questions about Tibero accurately.",
    },
    "tmax_v2": {
        "ja": "あなたはTmax専門のテクニカルアシスタントです。Tmaxに関する質問に正確に回答してください。",
        "ko": "당신은 Tmax 전문 기술 어시스턴트입니다. Tmax에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a Tmax technical expert assistant. Answer questions about Tmax accurately.",
    },
    "jeus_v2": {
        "ja": "あなたはJEUS専門のテクニカルアシスタントです。JEUSに関する質問に正確に回答してください。",
        "ko": "당신은 JEUS 전문 기술 어시스턴트입니다. JEUS에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a JEUS technical expert assistant. Answer questions about JEUS accurately.",
    },
    "webtob_v2": {
        "ja": "あなたはWebtoB専門のテクニカルアシスタントです。WebtoBに関する質問に正確に回答してください。",
        "ko": "당신은 WebtoB 전문 기술 어시스턴트입니다. WebtoB에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are a WebtoB technical expert assistant. Answer questions about WebtoB accurately.",
    },
    "ofcobol_v2": {
        "ja": "あなたはOFCOBOL専門のテクニカルアシスタントです。COBOLに関する質問に正確に回答してください。",
        "ko": "당신은 OFCOBOL 전문 기술 어시스턴트입니다. COBOL에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OFCOBOL technical expert assistant. Answer questions about COBOL accurately.",
    },
    "ofasm_v2": {
        "ja": "あなたはOFAsm専門のテクニカルアシスタントです。アセンブラに関する質問に正確に回答してください。",
        "ko": "당신은 OFAsm 전문 기술 어시스턴트입니다. 어셈블러에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OFAsm technical expert assistant. Answer questions about assembler accurately.",
    },
    "openframe_base_v2": {
        "ja": "あなたはOpenFrame Base専門のテクニカルアシスタントです。Baseモジュールに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame Base 전문 기술 어시스턴트입니다. Base 모듈에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame Base technical expert assistant. Answer questions about Base module accurately.",
    },
    "openframe_hidb_v2": {
        "ja": "あなたはOpenFrame HiDB専門のテクニカルアシスタントです。HiDBに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame HiDB 전문 기술 어시스턴트입니다. HiDB에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame HiDB technical expert assistant. Answer questions about HiDB accurately.",
    },
    "openframe_aim_v2": {
        "ja": "あなたはOpenFrame AIM専門のテクニカルアシスタントです。AIMに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame AIM 전문 기술 어시스턴트입니다. AIM에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame AIM technical expert assistant. Answer questions about AIM accurately.",
    },
    "openframe_osc_v2": {
        "ja": "あなたはOpenFrame OSC専門のテクニカルアシスタントです。OSCに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame OSC 전문 기술 어시스턴트입니다. OSC에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame OSC technical expert assistant. Answer questions about OSC accurately.",
    },
    "openframe_osi_v2": {
        "ja": "あなたはOpenFrame OSI専門のテクニカルアシスタントです。OSIに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame OSI 전문 기술 어시스턴트입니다. OSI에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame OSI technical expert assistant. Answer questions about OSI accurately.",
    },
    "openframe_tacf_v2": {
        "ja": "あなたはOpenFrame TACF専門のテクニカルアシスタントです。TACFに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame TACF 전문 기술 어시스턴트입니다. TACF에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame TACF technical expert assistant. Answer questions about TACF accurately.",
    },
    "openframe_ndb_v2": {
        "ja": "あなたはOpenFrame NDB専門のテクニカルアシスタントです。NDBに関する質問に正確に回答してください。",
        "ko": "당신은 OpenFrame NDB 전문 기술 어시스턴트입니다. NDB에 관한 질문에 정확하게 답변해주세요.",
        "en": "You are an OpenFrame NDB technical expert assistant. Answer questions about NDB accurately.",
    },
}

# 에러코드 prefix → 제품 매핑
ERROR_PREFIX_TO_PRODUCT = {
    "BASE": "openframe_base_v2",
    "BATCH": "openframe_batch_v2",
    "TACF": "openframe_tacf_v2",
    "AIM": "openframe_aim_v2",
    "NDB": "openframe_ndb_v2",
    "OSC": "openframe_osc_v2",
    "OSI": "openframe_osi_v2",
    "HIDB": "openframe_hidb_v2",
    "UNKNOWN": "openframe_common_v2",
}

# ============================================
# 통합 LoRA 시스템 프롬프트 (25번째 어댑터용)
# ============================================
UNIFIED_SYSTEM_PROMPTS = {
    "ja": (
        "あなたはTmaxSoft製品群全体の統合テクニカルアシスタントです。\n"
        "OpenFrame（Base, Batch, OSC, OSI, TACF, HiDB, NDB, AIM, Gateway）、\n"
        "Tibero、JEUS、Tmax、WebtoB、OFCOBOL、OFAsm、OFManager、\n"
        "ProSort、ProSync、ProTrieve、OFMiner、OFStudioを含む\n"
        "全製品の連携・比較・依存関係について正確に回答してください。\n"
        "製品間の関係性、起動順序、マイグレーションパス、\n"
        "エラーの伝播範囲について特に詳しく答えてください。"
    ),
    "ko": (
        "당신은 TmaxSoft 제품군 전체의 통합 기술 어시스턴트입니다.\n"
        "OpenFrame(Base, Batch, OSC, OSI, TACF, HiDB, NDB, AIM, Gateway),\n"
        "Tibero, JEUS, Tmax, WebtoB, OFCOBOL, OFAsm, OFManager,\n"
        "ProSort, ProSync, ProTrieve, OFMiner, OFStudio를 포함한\n"
        "전체 제품의 연동/비교/의존관계에 대해 정확하게 답변해주세요.\n"
        "제품 간 관계성, 기동 순서, 마이그레이션 경로,\n"
        "에러 전파 범위에 대해 특히 상세하게 답변해주세요."
    ),
    "en": (
        "You are a unified technical assistant for the entire TmaxSoft product suite.\n"
        "Covering OpenFrame (Base, Batch, OSC, OSI, TACF, HiDB, NDB, AIM, Gateway),\n"
        "Tibero, JEUS, Tmax, WebtoB, OFCOBOL, OFAsm, OFManager,\n"
        "ProSort, ProSync, ProTrieve, OFMiner, OFStudio.\n"
        "Answer accurately about product integration, comparison, dependencies,\n"
        "boot sequences, migration paths, and error propagation."
    ),
}

# ============================================
# 통합 LoRA 질문 감지 키워드 (vLLM 라우팅용)
# ============================================
UNIFIED_QUERY_KEYWORDS = {
    "ja": ["連携", "起動順", "全体", "比較", "違い", "共通", "一覧",
           "依存", "影響", "マイグレーション", "移行", "システム構成",
           "全製品", "全コンポーネント", "統合"],
    "ko": ["연동", "기동순서", "전체", "비교", "차이", "공통", "목록",
           "의존", "영향", "마이그레이션", "이행", "시스템 구성",
           "전 제품", "전체 컴포넌트", "통합"],
    "en": ["integration", "boot order", "overall", "comparison", "difference",
           "common", "dependency", "migration", "architecture", "all products",
           "all components", "unified"],
}

# ============================================
# 제품 ID → 표시명 매핑 (통합 Q-A 템플릿에서 사용)
# ============================================
PRODUCT_DISPLAY_NAMES = {
    "openframe_base_v2": "OpenFrame Base",
    "openframe_batch_v2": "OpenFrame Batch (TJES)",
    "openframe_osc_v2": "OpenFrame OSC",
    "openframe_osi_v2": "OpenFrame OSI",
    "openframe_tacf_v2": "OpenFrame TACF",
    "openframe_hidb_v2": "OpenFrame HiDB",
    "openframe_ndb_v2": "OpenFrame NDB",
    "openframe_aim_v2": "OpenFrame AIM",
    "openframe_gateway_v2": "OpenFrame Gateway",
    "openframe_common_v2": "OpenFrame",
    "openframe_vos3_v2": "OpenFrame VOS3",
    "tibero7_v2": "Tibero",
    "tmax_v2": "Tmax",
    "jeus_v2": "JEUS",
    "webtob_v2": "WebtoB",
    "ofcobol_v2": "OFCOBOL",
    "ofasm_v2": "OFAsm",
    "ofmanager_v2": "OFManager",
    "ofminer_v2": "OFMiner",
    "ofstudio_v2": "OFStudio",
    "prosort_v2": "ProSort",
    "prosync_v2": "ProSync",
    "protrieve_v2": "ProTrieve",
    "ofpli_v2": "OFPli",
}

# 다른 제품 감지용 키워드 (PDF 크로스참조 추출에서 사용)
OTHER_PRODUCT_KEYWORDS = {
    "Base": "openframe_base_v2",
    "TACF": "openframe_tacf_v2",
    "TJES": "openframe_batch_v2",
    "Batch": "openframe_batch_v2",
    "OSC": "openframe_osc_v2",
    "OSI": "openframe_osi_v2",
    "HiDB": "openframe_hidb_v2",
    "NDB": "openframe_ndb_v2",
    "AIM": "openframe_aim_v2",
    "Gateway": "openframe_gateway_v2",
    "Tibero": "tibero7_v2",
    "JEUS": "jeus_v2",
    "WebtoB": "webtob_v2",
    "Tmax": "tmax_v2",
    "OFCOBOL": "ofcobol_v2",
    "OFAsm": "ofasm_v2",
    "OFManager": "ofmanager_v2",
    # v2 추가: 누락 제품 + 기술 키워드
    "VOS3": "openframe_vos3_v2",
    "OFMiner": "ofminer_v2",
    "OFStudio": "ofstudio_v2",
    "OFPli": "ofpli_v2",
    "PL/I": "ofpli_v2",
    "ProSync": "prosync_v2",
    "ProTrieve": "protrieve_v2",
    "ProSort": "prosort_v2",
    "RDBII": "openframe_aim_v2",
    "PSAM": "openframe_aim_v2",
    "BMS": "openframe_osc_v2",
    "MFS": "openframe_osi_v2",
    "CTG": "openframe_osc_v2",
    "AIMPED": "openframe_aim_v2",
}

# 관계 유형 감지 패턴 (PDF 크로스참조 추출에서 사용)
CROSS_REFERENCE_PATTERNS = {
    "R-01": r"(?:必要|requires?|依存|前提|なければ|ないと)",
    "R-02": r"(?:連携|接続|アクセス|connect|interface|設定|config)",
    "R-03": r"(?:違い|差異|比較|differ|vs\.?|一方|に対して)",
    "R-04": r"(?:起動順|停止順|boot|shutdown|先に|before|after|順序)",
    "R-05": r"(?:影響|伝播|波及|propagat|impact|affect|障害|エラー)",
    "R-06": r"(?:移行|マイグレーション|migrat|変換|convert|互換)",
    "R-07": r"(?:共通設定|共有|common.+config|shared|oframe\.conf)",
    "R-08": r"(?:プラットフォーム|platform|플랫폼|MVS.+MSP|MSP.+XSP|MVS.+XSP|差異|違い|異なる|차이|다른)",
}

# 관계 유형 이름
RELATION_TYPE_NAMES = {
    "R-01": {"ja": "依存関係", "ko": "의존관계", "en": "Dependency"},
    "R-02": {"ja": "連携方法", "ko": "연동방법", "en": "Integration"},
    "R-03": {"ja": "比較", "ko": "비교", "en": "Comparison"},
    "R-04": {"ja": "起動順序", "ko": "기동순서", "en": "Boot Sequence"},
    "R-05": {"ja": "エラー伝播", "ko": "에러전파", "en": "Error Propagation"},
    "R-06": {"ja": "マイグレーション", "ko": "마이그레이션", "en": "Migration Path"},
    "R-07": {"ja": "共通設定", "ko": "공통설정", "en": "Shared Config"},
    "R-08": {"ja": "プラットフォーム差異", "ko": "플랫폼차이", "en": "Platform Difference"},
}

# 기본 시스템 프롬프트 (매핑 없는 제품용)
DEFAULT_SYSTEM_PROMPT = {
    "ja": "あなたはTmaxSoft製品専門のテクニカルアシスタントです。正確に回答してください。",
    "ko": "당신은 TmaxSoft 제품 전문 기술 어시스턴트입니다. 정확하게 답변해주세요.",
    "en": "You are a TmaxSoft product technical expert assistant. Answer accurately.",
}
