#!/usr/bin/env python3
"""
전체 매뉴얼 구조 분석 및 전략 결정 스크립트

모든 PDF 매뉴얼의 TOC를 분석하여 최적의 파싱 전략을 결정하고
strategy_analysis.json 파일을 생성합니다.
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

import pymupdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


@dataclass
class TOCItem:
    """TOC 항목"""
    level: int
    title: str
    page: int


@dataclass
class ManualAnalysis:
    """매뉴얼 분석 결과"""
    file_path: str
    file_name: str
    product: str
    guide_type: str
    total_pages: int
    toc_items: int
    strategy_id: str
    strategy_name: str
    confidence: float
    toc_sample: List[Dict]
    analysis_notes: List[str]


# 16개 파싱 전략 정의
PARSING_STRATEGIES = {
    # Category 1: Reference Type (명령어/API 중심)
    "S01_TOOL_REFERENCE": {
        "name": "Tool Reference",
        "keywords": ["Tool-Reference", "Tool_Reference", "ツールリファレンス"],
        "toc_patterns": [r"\d+\.\d+\.\s+[a-z][a-z0-9_-]+", r"第\d+章.*ツール"],
        "priority": 1,
    },
    "S02_COMMAND_REFERENCE": {
        "name": "Command Reference",
        "keywords": ["Command-Reference", "Command_Reference", "コマンドリファレンス"],
        "toc_patterns": [r"[a-z]+(?:mgr|ctl|cmd)", r"コマンド"],
        "priority": 1,
    },
    "S03_UTILITY_REFERENCE": {
        "name": "Utility Reference",
        "keywords": ["Utility-Reference", "Utility_Reference", "ユーティリティ"],
        "toc_patterns": [r"IDCAMS|IEBGENER|IEBCOPY|DFSORT", r"ユーティリティ"],
        "priority": 1,
    },
    "S04_JCL_REFERENCE": {
        "name": "JCL Reference",
        "keywords": ["JCL-Reference", "JCL_Reference", "IPF-Reference"],
        "toc_patterns": [r"JOB|EXEC|DD|PROC", r"JCL"],
        "priority": 1,
    },
    "S05_ERROR_REFERENCE": {
        "name": "Error Reference",
        "keywords": ["Error-Reference", "Error_Reference", "エラーリファレンス", "Message-Reference"],
        "toc_patterns": [r"-?\d{4,5}", r"エラー|ERROR|メッセージ"],
        "priority": 1,
    },
    "S06_LANGUAGE_REFERENCE": {
        "name": "Language Reference",
        "keywords": ["Language-Reference", "言語リファレンス", "SQL_Reference", "tbPSM"],
        "toc_patterns": [r"DIVISION|SECTION|DECLARE|SELECT|INSERT", r"文法|構文"],
        "priority": 1,
    },

    # Category 2: Guide Type (관리/설정/개발)
    "S07_ADMIN_GUIDE": {
        "name": "Administrator Guide",
        "keywords": ["Administrator-Guide", "Administration-Guide", "管理者ガイド", "Admin"],
        "toc_patterns": [r"管理|運用|監視|制御|モニタリング", r"Administrator"],
        "priority": 2,
    },
    "S08_CONFIG_GUIDE": {
        "name": "Configuration Guide",
        "keywords": ["Configuration-Guide", "Configuration_Guide", "設定ガイド"],
        "toc_patterns": [r"設定|パラメータ|\.conf|環境変数", r"Configuration"],
        "priority": 2,
    },
    "S09_BATCH_GUIDE": {
        "name": "Batch Guide",
        "keywords": ["Batch-Guide", "Batch_Guide", "TJES-Guide", "TJES_Guide", "バッチガイド"],
        "toc_patterns": [r"バッチ|ジョブ|JOB|SUBMIT", r"Batch|TJES"],
        "priority": 2,
    },
    "S10_DEVELOPER_GUIDE": {
        "name": "Developer Guide",
        "keywords": ["Developer-Guide", "Developer_Guide", "開発者ガイド", "Application_Developer"],
        "toc_patterns": [r"API|関数|インターフェース|プログラミング", r"Developer"],
        "priority": 2,
    },
    "S11_RESOURCE_GUIDE": {
        "name": "Resource Guide",
        "keywords": ["Resource-Guide", "Resource-Definition", "MFS-Reference", "System-Definition"],
        "toc_patterns": [r"リソース|TRANSACTION|PROGRAM|MAPSET", r"Resource|Definition"],
        "priority": 2,
    },

    # Category 3: Concept Type (개념/소개/설치)
    "S12_INTRO_GUIDE": {
        "name": "Introduction Guide",
        "keywords": ["Introduction", "Getting-Start", "Getting_Started", "概要", "入門"],
        "toc_patterns": [r"概要|紹介|アーキテクチャ|Overview", r"Introduction|Getting"],
        "priority": 3,
    },
    "S13_USER_GUIDE": {
        "name": "User Guide",
        "keywords": ["User-Guide", "User_Guide", "ユーザーガイド", "使用ガイド"],
        "toc_patterns": [r"使い方|操作|画面|メニュー", r"User|使用"],
        "priority": 3,
    },
    "S14_INSTALL_GUIDE": {
        "name": "Installation Guide",
        "keywords": ["Installation-Guide", "Installation_Guide", "インストールガイド", "installation-guide"],
        "toc_patterns": [r"インストール|セットアップ|環境構築|前提条件", r"Install"],
        "priority": 3,
    },
    "S15_MIGRATION_GUIDE": {
        "name": "Migration Guide",
        "keywords": ["Migration-Guide", "Migration_Guide", "移行ガイド"],
        "toc_patterns": [r"移行|マイグレーション|変換|Migration", r"移行"],
        "priority": 3,
    },
    "S16_RELEASE_NOTE": {
        "name": "Release Note",
        "keywords": ["Release-Note", "Release_Note", "リリースノート", "Release-note"],
        "toc_patterns": [r"リリース|変更履歴|新機能|バージョン", r"Release"],
        "priority": 4,
    },
}

# 제품 분류 패턴
PRODUCT_PATTERNS = [
    (r"JEUS", "JEUS"),
    (r"WebtoB|WebT_", "WebtoB"),
    (r"Tibero", "Tibero"),
    (r"Tmax_", "Tmax"),
    (r"ProSort", "ProSort"),
    (r"ProSync", "ProSync"),
    (r"ProTrieve", "ProTrieve"),
    (r"OFManager|OF_Manager", "OFManager"),
    (r"OFMiner|OF_Miner", "OFMiner"),
    (r"OFStudio|OpenFrame_Studio", "OFStudio"),
    (r"OFPLI|OF_PLI", "OFPLI"),
    (r"OFCOBOL|OF_COBOL", "OFCOBOL"),
    (r"OFAsm|OF_ASM", "OFAsm"),
    (r"OF_GW", "OF_Gateway"),
    (r"OF_AIM", "OF_AIM"),
    (r"OF_OSC", "OF_OSC"),
    (r"OF_OSI", "OF_OSI"),
    (r"OF_HiDB", "OF_HiDB"),
    (r"OF_NDB", "OF_NDB"),
    (r"OF_TACF", "OF_TACF"),
    (r"OF_Batch", "OF_Batch"),
    (r"OF_Base", "OF_Base"),
    (r"OF_Common", "OF_Common"),
    (r"OF_VOS3", "OF_VOS3"),
]


def detect_product(filename: str) -> str:
    """파일명에서 제품명 추출"""
    for pattern, product in PRODUCT_PATTERNS:
        if re.search(pattern, filename):
            return product
    return "Other"


def detect_guide_type(filename: str) -> str:
    """파일명에서 가이드 유형 추출"""
    guide_patterns = [
        ("Error-Reference|Error_Reference", "error-reference"),
        ("Command-Reference", "command-reference"),
        ("Tool-Reference|Tool_Reference", "tool-reference"),
        ("Utility-Reference|Utility_Reference", "utility-reference"),
        ("Reference-Guide|Reference_Guide", "reference-guide"),
        ("Language-Reference", "language-reference"),
        ("SQL_Reference", "sql-reference"),
        ("JCL-Reference|JCL_Reference", "jcl-reference"),
        ("IPF-Reference", "ipf-reference"),
        ("MFS-Reference", "mfs-reference"),
        ("FDL-Reference", "fdl-reference"),
        ("Message-Reference", "message-reference"),
        ("Configuration-Guide", "configuration-guide"),
        ("Administrator-Guide|Administration-Guide", "administrator-guide"),
        ("Installation-Guide|Installation_Guide|installation-guide", "installation-guide"),
        ("Developer-Guide|Developer_Guide", "developer-guide"),
        ("User-Guide|User_Guide|User-guide", "user-guide"),
        ("Getting-Start|Getting_Started", "getting-started"),
        ("Introduction", "introduction"),
        ("Migration-Guide|Migration_Guide", "migration-guide"),
        ("Release-Note|Release_Note|Release-note", "release-note"),
        ("Batch-Guide|Batch_Guide", "batch-guide"),
        ("TJES-Guide|TJES_Guide", "tjes-guide"),
        ("Base-Guide", "base-guide"),
        ("Dataset-Guide", "dataset-guide"),
        ("Resource-Guide|Resource-Definition", "resource-guide"),
        ("System-Definition", "system-definition"),
        ("Mapping-Support", "mapping-support"),
        ("Sort-Utility|Sort_Guide", "sort-utility"),
        ("Gateway-Guide", "gateway-guide"),
        ("Programming-Guide", "programming-guide"),
        ("WebTerminal", "webterminal"),
        ("WebAdmin", "webadmin"),
        ("Glossary", "glossary"),
        ("NDB-Guide", "ndb-guide"),
        ("HiDB-Guide", "hidb-guide"),
        ("CTG-User", "ctg-user"),
    ]

    for pattern, gtype in guide_patterns:
        if re.search(pattern, filename, re.IGNORECASE):
            return gtype
    return "other"


def determine_strategy(filename: str, toc_items: List[TOCItem], product: str, guide_type: str) -> Tuple[str, str, float, List[str]]:
    """TOC 분석을 통한 전략 결정"""
    notes = []
    scores = {}

    # 1. 파일명 기반 키워드 매칭
    for strategy_id, strategy in PARSING_STRATEGIES.items():
        score = 0
        for keyword in strategy["keywords"]:
            if keyword.lower() in filename.lower():
                score += 10
                notes.append(f"Filename match: {keyword}")
        scores[strategy_id] = score

    # 2. TOC 타이틀 패턴 매칭
    toc_text = " ".join([item.title for item in toc_items])
    for strategy_id, strategy in PARSING_STRATEGIES.items():
        for pattern in strategy["toc_patterns"]:
            matches = len(re.findall(pattern, toc_text, re.IGNORECASE))
            if matches > 0:
                scores[strategy_id] = scores.get(strategy_id, 0) + matches * 2

    # 3. 가이드 유형 기반 매핑
    guide_to_strategy = {
        "error-reference": "S05_ERROR_REFERENCE",
        "command-reference": "S02_COMMAND_REFERENCE",
        "tool-reference": "S01_TOOL_REFERENCE",
        "utility-reference": "S03_UTILITY_REFERENCE",
        "jcl-reference": "S04_JCL_REFERENCE",
        "reference-guide": "S06_LANGUAGE_REFERENCE",
        "sql-reference": "S06_LANGUAGE_REFERENCE",
        "language-reference": "S06_LANGUAGE_REFERENCE",
        "administrator-guide": "S07_ADMIN_GUIDE",
        "configuration-guide": "S08_CONFIG_GUIDE",
        "batch-guide": "S09_BATCH_GUIDE",
        "tjes-guide": "S09_BATCH_GUIDE",
        "developer-guide": "S10_DEVELOPER_GUIDE",
        "resource-guide": "S11_RESOURCE_GUIDE",
        "system-definition": "S11_RESOURCE_GUIDE",
        "introduction": "S12_INTRO_GUIDE",
        "getting-started": "S12_INTRO_GUIDE",
        "user-guide": "S13_USER_GUIDE",
        "webadmin": "S13_USER_GUIDE",
        "webterminal": "S13_USER_GUIDE",
        "installation-guide": "S14_INSTALL_GUIDE",
        "migration-guide": "S15_MIGRATION_GUIDE",
        "release-note": "S16_RELEASE_NOTE",
        "glossary": "S12_INTRO_GUIDE",
        "base-guide": "S07_ADMIN_GUIDE",
        "dataset-guide": "S07_ADMIN_GUIDE",
        "ndb-guide": "S07_ADMIN_GUIDE",
        "hidb-guide": "S07_ADMIN_GUIDE",
        "sort-utility": "S03_UTILITY_REFERENCE",
        "gateway-guide": "S07_ADMIN_GUIDE",
        "programming-guide": "S10_DEVELOPER_GUIDE",
        "mapping-support": "S11_RESOURCE_GUIDE",
        "ctg-user": "S13_USER_GUIDE",
        "message-reference": "S05_ERROR_REFERENCE",
    }

    if guide_type in guide_to_strategy:
        mapped_strategy = guide_to_strategy[guide_type]
        scores[mapped_strategy] = scores.get(mapped_strategy, 0) + 15
        notes.append(f"Guide type mapping: {guide_type} -> {mapped_strategy}")

    # 4. 제품별 기본 전략 보정
    product_defaults = {
        "JEUS": "S07_ADMIN_GUIDE",
        "WebtoB": "S07_ADMIN_GUIDE",
        "Tibero": "S07_ADMIN_GUIDE",
        "Tmax": "S10_DEVELOPER_GUIDE",
        "ProSort": "S03_UTILITY_REFERENCE",
        "ProSync": "S07_ADMIN_GUIDE",
        "ProTrieve": "S10_DEVELOPER_GUIDE",
    }

    if product in product_defaults and max(scores.values(), default=0) < 10:
        default_strategy = product_defaults[product]
        scores[default_strategy] = scores.get(default_strategy, 0) + 5
        notes.append(f"Product default: {product} -> {default_strategy}")

    # 5. 최고 점수 전략 선택
    if not scores or max(scores.values()) == 0:
        # 기본값
        return "S13_USER_GUIDE", "User Guide", 0.5, ["No pattern matched, using default"]

    best_strategy = max(scores, key=scores.get)
    best_score = scores[best_strategy]
    total_score = sum(scores.values())
    confidence = min(best_score / max(total_score, 1), 1.0)

    return best_strategy, PARSING_STRATEGIES[best_strategy]["name"], confidence, notes


def analyze_pdf(pdf_path: Path) -> Optional[ManualAnalysis]:
    """단일 PDF 분석"""
    try:
        doc = pymupdf.open(str(pdf_path))

        # TOC 추출
        toc_raw = doc.get_toc()
        toc_items = [TOCItem(level=item[0], title=item[1], page=item[2]) for item in toc_raw]

        # 기본 정보
        filename = pdf_path.name
        product = detect_product(filename)
        guide_type = detect_guide_type(filename)

        # 전략 결정
        strategy_id, strategy_name, confidence, notes = determine_strategy(
            filename, toc_items, product, guide_type
        )

        # TOC 샘플 (최대 20개)
        toc_sample = [
            {"level": item.level, "title": item.title, "page": item.page}
            for item in toc_items[:20]
        ]

        analysis = ManualAnalysis(
            file_path=str(pdf_path.relative_to(pdf_path.parents[2])),
            file_name=filename,
            product=product,
            guide_type=guide_type,
            total_pages=len(doc),
            toc_items=len(toc_items),
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            confidence=round(confidence, 2),
            toc_sample=toc_sample,
            analysis_notes=notes,
        )

        doc.close()
        return analysis

    except Exception as e:
        logger.error(f"Failed to analyze {pdf_path.name}: {e}")
        return None


def analyze_all_manuals(manuals_dir: Path, output_path: Path) -> Dict:
    """모든 매뉴얼 분석"""
    pdfs = list(manuals_dir.rglob("*.pdf"))
    logger.info(f"Found {len(pdfs)} PDF files to analyze")

    results = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_files": len(pdfs),
            "manuals_dir": str(manuals_dir),
        },
        "strategy_summary": {},
        "product_summary": {},
        "analyses": [],
    }

    strategy_counts = {}
    product_counts = {}

    for i, pdf_path in enumerate(sorted(pdfs)):
        logger.info(f"[{i+1}/{len(pdfs)}] Analyzing: {pdf_path.name}")

        analysis = analyze_pdf(pdf_path)
        if analysis:
            results["analyses"].append(asdict(analysis))

            # 통계 업데이트
            strategy_counts[analysis.strategy_id] = strategy_counts.get(analysis.strategy_id, 0) + 1
            product_counts[analysis.product] = product_counts.get(analysis.product, 0) + 1

    # 요약 정보
    results["strategy_summary"] = dict(sorted(strategy_counts.items(), key=lambda x: -x[1]))
    results["product_summary"] = dict(sorted(product_counts.items(), key=lambda x: -x[1]))
    results["metadata"]["analyzed_files"] = len(results["analyses"])
    results["metadata"]["failed_files"] = len(pdfs) - len(results["analyses"])

    # 저장
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"Analysis saved to: {output_path}")
    return results


def print_summary(results: Dict):
    """분석 결과 요약 출력"""
    print("\n" + "=" * 70)
    print("MANUAL ANALYSIS SUMMARY")
    print("=" * 70)

    meta = results["metadata"]
    print(f"\nTotal Files: {meta['total_files']}")
    print(f"Analyzed: {meta['analyzed_files']}")
    print(f"Failed: {meta['failed_files']}")

    print("\n--- Strategy Distribution ---")
    for strategy, count in results["strategy_summary"].items():
        pct = count / meta["analyzed_files"] * 100
        print(f"  {strategy}: {count} ({pct:.1f}%)")

    print("\n--- Product Distribution ---")
    for product, count in results["product_summary"].items():
        pct = count / meta["analyzed_files"] * 100
        print(f"  {product}: {count} ({pct:.1f}%)")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    import sys

    # 프로젝트 루트 찾기
    current = Path(__file__).resolve()
    project_root = None
    for parent in [current] + list(current.parents):
        if (parent / "CLAUDE.md").exists():
            project_root = parent
            break

    if not project_root:
        project_root = Path.cwd()

    manuals_dir = project_root / "uploads" / "manuals"
    output_path = project_root / "uploads" / "summaries" / "strategy_analysis.json"

    if not manuals_dir.exists():
        print(f"Manuals directory not found: {manuals_dir}")
        sys.exit(1)

    # 분석 실행
    results = analyze_all_manuals(manuals_dir, output_path)
    print_summary(results)
