"""설정 모듈"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ProcessorConfig:
    """매뉴얼 프로세서 설정"""

    # 경로 설정
    manuals_dir: Path = Path("/opt/kms/uploads/manuals")
    summaries_dir: Path = Path("/opt/kms/uploads/summaries")

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


# 기본 설정 인스턴스
config = ProcessorConfig()
