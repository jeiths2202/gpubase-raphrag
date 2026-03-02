"""
Strategy-Aware Parser

전략 분석 파일(strategy_analysis.json)을 활용하여
각 문서 유형에 최적화된 추출 패턴을 적용하는 파서입니다.

16개 전략 유형:
- Category 1 (Reference): S01-S06 - 명령어/API 중심 추출
- Category 2 (Guide): S07-S11 - 관리/설정/개발 가이드 추출
- Category 3 (Concept): S12-S16 - 개념/설치/마이그레이션 추출
"""

import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import codecs

import pymupdf

logger = logging.getLogger(__name__)


def extract_cjk_text(page) -> str:
    """CJK(한국어/일본어/중국어) PDF 페이지에서 텍스트 추출 (개선된 방법)

    pymupdf의 다양한 추출 옵션을 시도하여 최적의 결과를 반환합니다.
    한국어, 일본어, 중국어 문서 모두 지원합니다.
    """
    # 방법 1: 기본 텍스트 추출 (flags로 최적화)
    text = page.get_text("text", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)

    # CJK 문자 비율 확인 (일본어 + 한국어 + 중국어)
    # 일본어: 히라가나(3040-309F), 가타카나(30A0-30FF)
    # 한국어: 한글 자모(1100-11FF), 한글 음절(AC00-D7AF), 한글 호환 자모(3130-318F)
    # 한자: 기본 한자(4E00-9FFF), 확장 한자(3400-4DBF)
    cjk_pattern = r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\u1100-\u11FF\uAC00-\uD7AF\u3130-\u318F]'
    cjk_chars = len(re.findall(cjk_pattern, text))
    total_chars = len(text.strip())

    if total_chars > 0 and cjk_chars / total_chars < 0.1:
        # CJK 문자가 거의 없으면 다른 방법 시도
        # 방법 2: dict 추출 후 spans에서 텍스트 조합
        try:
            blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]
            text_parts = []
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        line_text = ""
                        for span in line["spans"]:
                            line_text += span["text"]
                        text_parts.append(line_text)
            alt_text = "\n".join(text_parts)

            # 더 많은 CJK 문자가 추출되면 사용
            alt_cjk = len(re.findall(cjk_pattern, alt_text))
            if alt_cjk > cjk_chars:
                text = alt_text
        except Exception:
            pass

    return text


# 하위 호환성을 위한 별칭
extract_japanese_text = extract_cjk_text


def clean_text(text: str) -> str:
    """Clean extracted text from PDF."""
    if not text:
        return ""

    # Remove common PDF artifacts
    text = re.sub(r'\x00', '', text)  # Null bytes
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f]', '', text)  # Control chars

    # Normalize whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


@dataclass
class LearningDataItem:
    """학습 데이터셋 항목"""
    name: str
    item_type: str  # command, config, api, concept, procedure, error, term
    description: str
    syntax: Optional[str] = None
    parameters: List[Dict[str, str]] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    related: List[str] = field(default_factory=list)
    source_file: str = ""
    source_page: int = 0
    product: str = ""
    category: str = ""
    strategy_id: str = ""
    confidence: float = 0.0


class StrategyAwareParser:
    """전략 인식 파서

    strategy_analysis.json 파일의 분석 결과를 기반으로
    각 문서에 최적화된 추출 패턴을 적용합니다.
    """

    # 전략별 추출 우선순위
    STRATEGY_EXTRACTION_CONFIG = {
        # Category 1: Reference Type - 명령어/API 중심
        "S01_TOOL_REFERENCE": {
            "primary": ["command", "api"],
            "secondary": ["config", "concept"],
            "patterns": "reference"
        },
        "S02_COMMAND_REFERENCE": {
            "primary": ["command"],
            "secondary": ["api", "config"],
            "patterns": "command"
        },
        "S03_API_REFERENCE": {
            "primary": ["api"],
            "secondary": ["concept", "config"],
            "patterns": "api"
        },
        "S04_UTILITY_REFERENCE": {
            "primary": ["command", "procedure"],
            "secondary": ["config", "concept"],
            "patterns": "utility"
        },
        "S05_ERROR_REFERENCE": {
            "primary": ["error"],
            "secondary": ["concept", "procedure"],
            "patterns": "error"
        },
        "S06_MESSAGE_REFERENCE": {
            "primary": ["error", "concept"],
            "secondary": ["procedure"],
            "patterns": "message"
        },

        # Category 2: Guide Type - 관리/설정/개발 가이드
        "S07_ADMIN_GUIDE": {
            "primary": ["procedure", "command"],
            "secondary": ["config", "concept"],
            "patterns": "admin"
        },
        "S08_CONFIG_GUIDE": {
            "primary": ["config"],
            "secondary": ["procedure", "concept"],
            "patterns": "config"
        },
        "S09_BATCH_GUIDE": {
            "primary": ["procedure", "command"],
            "secondary": ["config", "concept"],
            "patterns": "batch"
        },
        "S10_DEVELOPER_GUIDE": {
            "primary": ["api", "procedure"],
            "secondary": ["concept", "config"],
            "patterns": "developer"
        },
        "S11_RESOURCE_GUIDE": {
            "primary": ["config", "concept"],
            "secondary": ["procedure"],
            "patterns": "resource"
        },

        # Category 3: Concept Type - 개념/설치/마이그레이션
        "S12_INTRO_GUIDE": {
            "primary": ["concept", "term"],
            "secondary": ["procedure"],
            "patterns": "intro"
        },
        "S13_USER_GUIDE": {
            "primary": ["concept", "procedure"],
            "secondary": ["command", "config"],
            "patterns": "user"
        },
        "S14_INSTALL_GUIDE": {
            "primary": ["procedure", "config"],
            "secondary": ["concept"],
            "patterns": "install"
        },
        "S15_MIGRATION_GUIDE": {
            "primary": ["procedure", "concept"],
            "secondary": ["config"],
            "patterns": "migration"
        },
        "S16_RELEASE_NOTE": {
            "primary": ["concept"],
            "secondary": ["procedure"],
            "patterns": "release"
        }
    }

    # OpenFrame 명령어 목록 (정확한 추출을 위함)
    OPENFRAME_COMMANDS = {
        # Manager 명령어
        "tjesmgr", "tacfmgr", "oscmgr", "osimgr", "hidbmgr", "ndbmgr",
        "catmgr", "volmgr", "jesinit", "jesdown", "oscboot", "oscdown",
        "osiboot", "osidown", "tjesinit", "tjesdown", "dsmigin", "dsmigout",
        # 유틸리티
        "idcams", "iebgener", "iebcopy", "dfsort", "cobrun", "asmrun",
        "plirun", "tmboot", "tmdown", "tmadmin", "ofboot", "ofdown",
        # 기타
        "dsload", "dsutil", "cobcopy", "jcl2csv", "csvjob"
    }

    # 전략별 추출 패턴
    EXTRACTION_PATTERNS = {
        "reference": {
            "command": [
                # OpenFrame 명령어 (명시적 목록)
                r"\b(tjesmgr|tacfmgr|oscmgr|osimgr|hidbmgr|ndbmgr|catmgr|volmgr)\b",
                r"\b(jesinit|jesdown|oscboot|oscdown|osiboot|osidown)\b",
                r"\b(idcams|iebgener|iebcopy|dfsort|dsmigin|dsmigout)\b",
                r"\b(tmboot|tmdown|tmadmin|ofboot|ofdown)\b",
                # 일반 명령어 패턴
                r"^(?:\d+\.)+\s*([a-zA-Z][a-zA-Z0-9_-]{2,})\s*(?:コマンド|command|ユーティリティ|utility)",
                r"^([a-z]{3,}mgr)\s+([A-Z]+)\s*$",  # tjesmgr BOOT
                r"構文[:：]\s*([a-z][a-z0-9_-]+)\s+",  # 構文: command
            ],
            "api": [
                r"([a-z]{2,6}_[a-z_]+)\s*\(\)",
                r"(?:int|void|char\*?|long)\s+([a-z_][a-z0-9_]{3,})\s*\([^)]*\)",
            ]
        },
        "command": {
            "command": [
                r"^([a-zA-Z][a-zA-Z0-9_-]{2,})\s*$",
                r"^\s*([a-z]{3,}(?:mgr|ctl|boot|init|down))\b",
                r"構文[:：]?\s*\n?\s*([a-zA-Z][a-zA-Z0-9_-]+)",
            ]
        },
        "api": {
            "api": [
                r"^[A-Z]\.\d+\.\d+\.\s*([a-z_][a-z0-9_]+)\s*\(\)",
                r"([a-z]{2,6}_[a-z_]+)\s*\([^)]*\)",
                r"(?:int|void|char\*?|long|BOOL)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            ]
        },
        "utility": {
            "command": [
                r"(?:ユーティリティ|utility|ツール|tool)[:：]?\s*([a-zA-Z][a-zA-Z0-9_-]+)",
                r"^([a-z][a-z0-9_-]{2,})\s+(?:-|–|オプション|option)",
            ],
            "procedure": [
                r"(?:手順|procedure|step)[:：]?\s*(.+)",
            ]
        },
        "error": {
            "error": [
                r"(-\d{4,5})\s*[-–—:：]\s*(.+)",
                r"([A-Z]{2,}\d{4,})\s*[-–—:：]\s*(.+)",
                r"エラー(?:コード|番号)[:：]?\s*(-?\d+)",
            ]
        },
        "message": {
            "error": [
                r"^([A-Z]{3,}\d{3,}[A-Z]?)\s+(.+)",
                r"メッセージ(?:ID|コード)[:：]?\s*([A-Z0-9]+)",
            ]
        },
        "admin": {
            "procedure": [
                r"(?:手順|Steps|操作)[:：]?\s*\n(.+?)(?:\n\n|\Z)",
                r"(?:\d+)[.．]\s*(.+?)(?:を|します|する)",
            ],
            "command": [
                r"(?:コマンド|command)[:：]?\s*([a-zA-Z][a-zA-Z0-9_-]+)",
            ]
        },
        "config": {
            "config": [
                r"^([A-Z][A-Z0-9_]+)\s*[=:]\s*(.+?)(?:\s*#|$)",
                r"^([A-Z][A-Z0-9_]+)\s*[-–—]\s*(.+?)$",
                r"(?:パラメータ|parameter)[:：]?\s*([A-Z][A-Z0-9_]+)",
                r"設定項目[:：]?\s*([A-Z][A-Z0-9_]+)",
            ]
        },
        "batch": {
            "procedure": [
                r"(?:JOB|EXEC|DD)\s+.+",
                r"バッチ(?:処理|ジョブ)[:：]?\s*(.+)",
            ],
            "command": [
                r"(?:tjesmgr|dsjobcall|dssubmit)\s+(.+)",
            ]
        },
        "developer": {
            "api": [
                r"(?:API|関数|function)[:：]?\s*([a-zA-Z_][a-zA-Z0-9_]*)",
                r"(?:メソッド|method)[:：]?\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            ],
            "procedure": [
                r"(?:開発手順|development)[:：]?\s*(.+)",
            ]
        },
        "resource": {
            "config": [
                r"(?:リソース|resource)[:：]?\s*([A-Z][A-Z0-9_]+)",
                r"(?:定義|definition)[:：]?\s*(.+)",
            ]
        },
        "intro": {
            "concept": [
                r"(?:概要|overview)[:：]?\s*(.+)",
                r"(?:とは|とは何か)[:：]?\s*(.+)",
                r"^([A-Z][A-Za-z0-9_-]+(?:\s+[A-Z][A-Za-z0-9_-]+)*)\s*[:：]\s*(.+)",
            ],
            "term": [
                r"^([A-Z]{2,})\s*\(([^)]+)\)",
                r"(?:用語|term)[:：]?\s*([A-Z][A-Za-z0-9_-]+)",
            ]
        },
        "user": {
            "concept": [
                r"(?:機能|feature)[:：]?\s*(.+)",
                r"(?:使用方法|usage)[:：]?\s*(.+)",
            ],
            "procedure": [
                r"(?:操作|operation)[:：]?\s*(.+)",
            ],
            "command": [
                # 機械語命令 (Machine Instructions) - ASM User Guide 부록
                r"^([A-Z]{2,})\s+([A-Z0-9]+\([^)]+\))",  # OFATOE D1(L1,B1),D2(B2)
                r"●使用方法\s*\n?\s*([A-Z]{2,})\s+",  # ●使用方法 OFATOE
                r"^A\.\d+\.\s*([A-Z]{2,})\b",  # A.1. OFATOE
            ]
        },
        "install": {
            "procedure": [
                r"(?:インストール|install)[:：]?\s*(.+)",
                r"(?:手順|step)\s*(\d+)[:：]?\s*(.+)",
                r"(?:前提条件|prerequisites)[:：]?\s*(.+)",
            ],
            "config": [
                r"(?:環境変数|environment)[:：]?\s*([A-Z][A-Z0-9_]+)",
            ]
        },
        "migration": {
            "procedure": [
                r"(?:移行|migration)[:：]?\s*(.+)",
                r"(?:変更点|changes)[:：]?\s*(.+)",
            ],
            "concept": [
                r"(?:非互換|incompatible)[:：]?\s*(.+)",
            ]
        },
        "release": {
            "concept": [
                r"(?:新機能|new feature)[:：]?\s*(.+)",
                r"(?:改善|improvement)[:：]?\s*(.+)",
                r"(?:修正|fix)[:：]?\s*(.+)",
            ]
        }
    }

    def __init__(self, manuals_dir: Path, strategy_file: Optional[Path] = None):
        self.manuals_dir = manuals_dir

        # 전략 분석 파일 로드
        if strategy_file is None:
            strategy_file = manuals_dir.parent / "summaries" / "strategy_analysis.json"

        self.strategy_data = self._load_strategy_file(strategy_file)
        self.file_strategies = self._build_file_strategy_map()

        logger.info(f"Loaded strategy data for {len(self.file_strategies)} files")

    def _load_strategy_file(self, strategy_file: Path) -> Dict[str, Any]:
        """전략 분석 파일 로드"""
        if not strategy_file.exists():
            logger.warning(f"Strategy file not found: {strategy_file}")
            return {"analyses": []}

        with open(strategy_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _build_file_strategy_map(self) -> Dict[str, Dict[str, Any]]:
        """파일별 전략 맵 구축"""
        file_map = {}
        for analysis in self.strategy_data.get("analyses", []):
            file_name = analysis.get("file_name", "")
            file_map[file_name] = {
                "strategy_id": analysis.get("strategy_id", "S01_TOOL_REFERENCE"),
                "product": analysis.get("product", "Unknown"),
                "confidence": analysis.get("confidence", 0.0),
                "guide_type": analysis.get("guide_type", "other"),
                "toc_items": analysis.get("toc_items", 0)
            }
        return file_map

    def get_strategy_for_file(self, filename: str) -> Dict[str, Any]:
        """파일의 전략 정보 반환"""
        return self.file_strategies.get(filename, {
            "strategy_id": "S01_TOOL_REFERENCE",
            "product": "Unknown",
            "confidence": 0.0
        })

    def _is_toc_page(self, text: str) -> bool:
        """TOC(목차) 페이지인지 감지"""
        indicators = [
            len(re.findall(r'\.{3,}\s*\d+', text)) > 3,     # 점선+페이지 3개 이상
            len(re.findall(r'第\d+章', text)) > 2,          # 장 번호 3개 이상
            len(re.findall(r'\[図\s*\d+\.\d+\]', text)) > 2,  # 그림 참조 3개 이상
            '目次' in text[:200],                           # 페이지 상단에 "목차"
            'Contents' in text[:200],                       # 영문 목차
            len(re.findall(r'^\d+\.\d+\.', text, re.MULTILINE)) > 5,  # 섹션 번호 5개 이상
        ]
        return sum(indicators) >= 2

    def parse_pdf(self, pdf_path: Path) -> List[LearningDataItem]:
        """전략 기반 PDF 파싱"""
        items = []
        filename = pdf_path.name

        # 전략 정보 조회
        strategy_info = self.get_strategy_for_file(filename)
        strategy_id = strategy_info["strategy_id"]
        product = strategy_info["product"]
        confidence = strategy_info["confidence"]

        # 전략별 추출 설정 가져오기
        extraction_config = self.STRATEGY_EXTRACTION_CONFIG.get(
            strategy_id,
            self.STRATEGY_EXTRACTION_CONFIG["S01_TOOL_REFERENCE"]
        )
        pattern_type = extraction_config["patterns"]

        logger.info(f"Parsing: {filename} (strategy={strategy_id}, pattern={pattern_type})")

        try:
            doc = pymupdf.open(pdf_path)
            toc_pages_skipped = 0

            for page_num, page in enumerate(doc, 1):
                # CJK PDF 텍스트 추출 (한국어/일본어/중국어)
                text = extract_cjk_text(page)
                if not text.strip():
                    continue

                # 텍스트 정제
                text = clean_text(text)

                # TOC 페이지 건너뛰기
                if self._is_toc_page(text):
                    toc_pages_skipped += 1
                    continue

                # 전략별 항목 추출
                page_items = self._extract_by_strategy(
                    text=text,
                    strategy_id=strategy_id,
                    extraction_config=extraction_config,
                    pattern_type=pattern_type,
                    filename=filename,
                    page_num=page_num,
                    product=product,
                    confidence=confidence
                )
                items.extend(page_items)

            doc.close()

            if toc_pages_skipped > 0:
                logger.debug(f"  Skipped {toc_pages_skipped} TOC pages")

        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")

        return items

    def _extract_by_strategy(
        self,
        text: str,
        strategy_id: str,
        extraction_config: Dict[str, Any],
        pattern_type: str,
        filename: str,
        page_num: int,
        product: str,
        confidence: float
    ) -> List[LearningDataItem]:
        """전략에 따른 항목 추출"""
        items = []
        patterns = self.EXTRACTION_PATTERNS.get(pattern_type, {})

        # Primary 타입 추출
        for item_type in extraction_config["primary"]:
            type_patterns = patterns.get(item_type, [])
            for pattern in type_patterns:
                extracted = self._extract_with_pattern(
                    text=text,
                    pattern=pattern,
                    item_type=item_type,
                    filename=filename,
                    page_num=page_num,
                    product=product,
                    strategy_id=strategy_id,
                    confidence=confidence
                )
                items.extend(extracted)

        # Secondary 타입 추출
        # command 타입은 항상 추출 (기계어 명령, CLI 도구 등 중요)
        # 다른 타입은 primary가 충분하지 않을 때만 추출
        for item_type in extraction_config["secondary"]:
            # command는 항상 추출, 나머지는 primary < 3일 때만
            if item_type != "command" and len(items) >= 3:
                continue
            type_patterns = patterns.get(item_type, [])
            for pattern in type_patterns:
                extracted = self._extract_with_pattern(
                    text=text,
                    pattern=pattern,
                    item_type=item_type,
                    filename=filename,
                    page_num=page_num,
                    product=product,
                    strategy_id=strategy_id,
                    confidence=confidence
                )
                items.extend(extracted)

        # 공통 추출: 섹션 기반 개념 추출
        concept_items = self._extract_concepts_from_sections(
            text=text,
            filename=filename,
            page_num=page_num,
            product=product,
            strategy_id=strategy_id,
            confidence=confidence
        )
        items.extend(concept_items)

        return items

    def _extract_with_pattern(
        self,
        text: str,
        pattern: str,
        item_type: str,
        filename: str,
        page_num: int,
        product: str,
        strategy_id: str,
        confidence: float
    ) -> List[LearningDataItem]:
        """패턴 기반 추출"""
        items = []

        try:
            for match in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
                name = match.group(1) if match.lastindex >= 1 else match.group(0)
                description = match.group(2) if match.lastindex >= 2 else ""

                # 이름 정제 및 필터링
                name = self._clean_name(name)
                if not self._is_valid_name(name, item_type):
                    continue

                # 일반적인 단어 필터링
                if self._is_common_word(name):
                    continue

                # 설명 추출 (패턴에 없으면 다음 문장 사용)
                if not description:
                    description = self._extract_description_after_match(
                        text, match.end(), name
                    )

                # 설명 품질 검증 (command/api는 완화된 기준 적용)
                if not self._is_valid_description(description, item_type):
                    continue

                items.append(LearningDataItem(
                    name=name,
                    item_type=item_type,
                    description=description[:500] if description else f"{name} ({item_type})",
                    source_file=filename,
                    source_page=page_num,
                    product=product,
                    strategy_id=strategy_id,
                    confidence=confidence
                ))

        except re.error as e:
            logger.debug(f"Pattern error: {pattern} - {e}")

        return items

    def _clean_name(self, name: str) -> str:
        """이름 정제"""
        name = name.strip()
        # 끝의 페이지 번호 제거 (예: "항목명......... 123")
        name = re.sub(r'[\s\.]+\d+\s*$', '', name)
        # 앞뒤 특수문자 제거
        name = re.sub(r'^[\s\.\-_:：]+', '', name)
        name = re.sub(r'[\s\.\-_:：]+$', '', name)
        return name

    def _is_valid_name(self, name: str, item_type: str) -> bool:
        """이름 유효성 검증"""
        if not name:
            return False

        # 최소 길이 체크 (4자로 강화)
        if len(name) < 4:
            return False

        # 최대 길이 체크 (command/api는 50자, concept은 80자)
        max_len = 50 if item_type in ('command', 'api') else 80
        if len(name) > max_len:
            return False

        # 페이지 번호 패턴 제외
        if re.match(r'^[\d\s\.\-]+$', name):
            return False

        # 점으로만 이루어진 것 제외
        if re.match(r'^[\s\.]+$', name):
            return False

        # 특수문자로 시작하는 것 제외 (단, 에러코드의 - 제외)
        if item_type != 'error' and re.match(r'^[^\w\-]', name):
            return False

        # mojibake 패턴 감지
        if re.search(r'[\x80-\xFF]{3,}|�{2,}', name):
            return False

        # 일본어 조사로 시작하면 무효 (불완전 문장)
        if re.match(r'^[のをはがにでとからまでよりへ]', name):
            return False

        # 일본어 조사로 끝나고 짧으면 무효 (문장 중간 절단)
        if re.search(r'[のをはがにでとからまでよりへ]$', name) and len(name) < 10:
            return False

        # 명령어/API는 영문자로 시작해야 함
        if item_type in ('command', 'api'):
            if not re.match(r'^[a-zA-Z]', name):
                return False
            # 점 뒤에 숫자가 오면 페이지 참조일 가능성
            if re.search(r'\.{2,}\s*\d', name):
                return False
            # 명령어/API는 주로 영어+숫자+특수문자로 구성
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_\-\.]*$', name):
                return False

        return True

    def _is_valid_description(self, description: str, item_type: str = None) -> bool:
        """설명 유효성 검증

        Args:
            description: 설명 텍스트
            item_type: 항목 유형 (command, api 등) - command는 syntax로 충분할 수 있음
        """
        if not description:
            return False

        # 최소 길이 체크 (command/api는 syntax가 있으면 10자, 그 외는 30자)
        min_len = 10 if item_type in ('command', 'api') else 30
        if len(description) < min_len:
            return False

        # 깨진 인코딩 패턴 (hex escape)
        if re.search(r'[\\x][a-fA-F0-9]{2}', description):
            return False

        # 깨진 일본어 인코딩 (mojibake 패턴)
        # CP932/Shift-JIS가 UTF-8로 잘못 해석된 패턴
        mojibake_patterns = [
            r'[\x80-\xFF]{3,}',  # 연속된 high bytes
            r'�{2,}',  # 대체 문자
            r'\\u[0-9a-fA-F]{4}',  # 유니코드 이스케이프
            r'[\\][0-9]{3}',  # 8진수 이스케이프
        ]
        for pattern in mojibake_patterns:
            if re.search(pattern, description):
                return False

        # 페이지 참조만 있는 경우
        if re.match(r'^[\d\s\.\-]+$', description):
            return False

        # TOC 패턴 감지 (점선+페이지, 그림 참조, 장 목차)
        toc_patterns = [
            r'\.{3,}\s*\d+',           # 점선+페이지 번호 (예: ".............. 19")
            r'\[図\s*\d+\.\d+\]',      # 그림 참조 (예: "[図 3.7]")
            r'第\d+章\s+.+\.{2,}',     # 장 목차 (예: "第3章 xxx....")
            r'^\s*\d+\.\d+\.\s*.+\.\.\.',  # 섹션 목차 (예: "3.1. xxx...")
        ]
        for pattern in toc_patterns:
            if re.search(pattern, description):
                return False

        # 의미 있는 문자 비율 확인 (CJK 문자, 영어, 숫자)
        # 한국어(AC00-D7AF, 1100-11FF, 3130-318F), 일본어(3040-309F, 30A0-30FF), 한자(4E00-9FFF, 3400-4DBF)
        meaningful_chars = len(re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318Fa-zA-Z0-9]', description))
        if len(description) > 0 and meaningful_chars / len(description) < 0.3:
            return False

        return True

    def _extract_description_after_match(
        self, text: str, pos: int, name: str
    ) -> str:
        """매치 이후 텍스트에서 설명 추출"""
        remaining = text[pos:pos + 500]
        lines = remaining.split('\n')

        for line in lines[:3]:
            line = line.strip()
            if line and len(line) > 10:
                # 다른 명령어나 섹션이 시작되면 중단
                if re.match(r'^(?:\d+\.|\w+mgr|\w+ctl)', line):
                    break
                return line[:300]

        return ""

    def _extract_concepts_from_sections(
        self,
        text: str,
        filename: str,
        page_num: int,
        product: str,
        strategy_id: str,
        confidence: float
    ) -> List[LearningDataItem]:
        """섹션 헤더에서 개념 추출"""
        items = []

        # TOC 페이지 감지 (많은 페이지 참조가 있으면 건너뛰기)
        page_ref_count = len(re.findall(r'\.\.\.\s*\d+', text))
        if page_ref_count > 5:
            return items

        # 섹션 헤더 패턴
        section_patterns = [
            r"^((?:\d+\.)+\s*)([^\n\.]{5,80})$",  # 1.2.3. Title (5-80자, 점 제외)
            r"^(第\d+[章節]\s*)([^\n\.]{5,80})$",  # 第1章 Title
        ]

        for pattern in section_patterns:
            for match in re.finditer(pattern, text, re.MULTILINE):
                prefix = match.group(1)
                title = match.group(2).strip()

                # 이름 정제
                title = self._clean_name(title)
                if not title or len(title) < 5:
                    continue

                # TOC 참조 패턴 제외
                if re.search(r'\.\.\.\s*\d+', title):
                    continue

                # 페이지 번호로 끝나는 것 제외 (한국어, 일본어, 영어 문자 뒤 숫자는 허용)
                if re.search(r'\d+\s*$', title) and not re.search(r'[a-zA-Z가-힣あ-んア-ン一-龯]\s*\d+\s*$', title):
                    continue

                # 일반적인 제목 건너뛰기
                if self._is_generic_title(title):
                    continue

                # 제목 이후 첫 단락을 설명으로 사용
                remaining = text[match.end():match.end() + 500]
                description = self._extract_first_paragraph(remaining)

                if description and len(description) > 30:
                    # 설명 품질 검증
                    if not self._is_valid_description(description, "concept"):
                        continue

                    items.append(LearningDataItem(
                        name=title,
                        item_type="concept",
                        description=description[:500],
                        source_file=filename,
                        source_page=page_num,
                        product=product,
                        strategy_id=strategy_id,
                        confidence=confidence
                    ))

        return items

    def _extract_first_paragraph(self, text: str) -> str:
        """첫 번째 의미있는 단락 추출"""
        paragraphs = text.strip().split('\n\n')
        for para in paragraphs:
            para = para.strip()
            if para and len(para) > 20:
                # 숫자/코드 라인이 아닌 경우
                if not re.match(r'^[\d\s\-\.]+$', para):
                    return para
        return ""

    def _is_common_word(self, word: str) -> bool:
        """일반적인 단어인지 확인"""
        # 영어 일반 단어
        common_words = {
            "the", "and", "for", "with", "from", "this", "that",
            "chapter", "section", "guide", "reference", "manual",
            "page", "table", "figure", "example", "note", "warning",
            "appendix", "index", "overview", "introduction", "summary",
            "contents", "copyright", "version", "release", "document",
            "information", "description", "option", "parameter", "value",
            "type", "name", "path", "file", "data", "system", "user",
            "server", "client", "application", "service", "process"
        }
        # 일본어 일반 단어
        jp_common = {
            "はじめに", "概要", "目次", "付録", "索引", "注意", "参照",
            "設定", "環境", "確認", "実行", "処理", "変更", "追加",
            "削除", "作成", "構成", "機能", "使用", "説明"
        }
        # 한국어 일반 단어
        kr_common = {
            "개요", "목차", "부록", "색인", "참조", "주의", "설정",
            "환경", "확인", "실행", "처리", "변경", "추가", "삭제",
            "생성", "구성", "기능", "사용", "설명", "소개", "안내",
            "가이드", "매뉴얼", "문서", "버전", "릴리스"
        }
        # 프로그래밍 일반 키워드
        programming_words = {
            "main", "run", "start", "stop", "get", "set", "init",
            "doget", "dopost", "execute", "process", "handle",
            "create", "update", "delete", "read", "write", "close",
            "open", "load", "save", "print", "return", "throw",
            "void", "int", "string", "boolean", "class", "public",
            "private", "static", "final", "abstract", "interface",
            "import", "package", "extends", "implements", "new",
            "true", "false", "null", "container", "message", "hello"
        }
        # 지역명/회사명
        location_words = {
            "seongnam", "seoul", "korea", "japan", "tokyo", "tmax",
            "gyeonggi", "bundang"
        }

        word_lower = word.lower()
        all_common = common_words | jp_common | kr_common | programming_words | location_words

        return word_lower in all_common

    def _is_generic_title(self, title: str) -> bool:
        """일반적인 제목인지 확인

        Note: 부록(appendix/付録/부록)은 기술 참조 정보를 포함하므로 스킵하지 않음
        """
        generic_titles = {
            # 영어
            "overview", "introduction", "contents", "index",
            "notes", "about this guide", "preface",
            # 일본어
            "概要", "はじめに", "目次", "索引",
            "注意事項", "このガイドについて",
            # 한국어
            "개요", "소개", "목차", "색인",
            "주의사항", "이 가이드에 대하여", "이 문서에 대하여",
            "머리말", "서문"
        }
        return title.lower() in {t.lower() for t in generic_titles}

    def process_all_manuals(self) -> List[LearningDataItem]:
        """모든 매뉴얼 처리"""
        all_items = []
        pdf_files = list(self.manuals_dir.rglob("*.pdf"))

        logger.info(f"Processing {len(pdf_files)} PDF files with strategy-aware parsing...")

        # 전략별 통계
        strategy_stats = {}

        for pdf_path in pdf_files:
            items = self.parse_pdf(pdf_path)
            all_items.extend(items)

            # 통계 업데이트
            strategy_info = self.get_strategy_for_file(pdf_path.name)
            strategy_id = strategy_info["strategy_id"]
            if strategy_id not in strategy_stats:
                strategy_stats[strategy_id] = {"files": 0, "items": 0}
            strategy_stats[strategy_id]["files"] += 1
            strategy_stats[strategy_id]["items"] += len(items)

            logger.info(f"  {pdf_path.name}: {len(items)} items ({strategy_id})")

        # 중복 제거
        unique_items = self._deduplicate_items(all_items)

        # 통계 출력
        logger.info(f"\n=== Strategy Statistics ===")
        for sid, stats in sorted(strategy_stats.items()):
            logger.info(f"  {sid}: {stats['files']} files, {stats['items']} items")

        logger.info(f"\nTotal: {len(unique_items)} unique items extracted")
        return unique_items

    def _deduplicate_items(self, items: List[LearningDataItem]) -> List[LearningDataItem]:
        """중복 항목 제거"""
        seen = {}
        for item in items:
            key = (item.name.lower(), item.item_type, item.product)
            if key not in seen or len(item.description) > len(seen[key].description):
                seen[key] = item
        return list(seen.values())


def generate_learning_dataset(
    manuals_dir: Path,
    output_path: Path,
    strategy_file: Optional[Path] = None
) -> Dict[str, Any]:
    """학습 데이터셋 생성

    Args:
        manuals_dir: 매뉴얼 디렉토리
        output_path: 출력 파일 경로
        strategy_file: 전략 분석 파일 경로

    Returns:
        생성 통계
    """
    parser = StrategyAwareParser(manuals_dir, strategy_file)
    items = parser.process_all_manuals()

    # 타입별 통계
    type_stats = {}
    for item in items:
        if item.item_type not in type_stats:
            type_stats[item.item_type] = 0
        type_stats[item.item_type] += 1

    # 제품별 통계
    product_stats = {}
    for item in items:
        if item.product not in product_stats:
            product_stats[item.product] = 0
        product_stats[item.product] += 1

    # JSON 출력
    output_data = {
        "metadata": {
            "total_items": len(items),
            "type_stats": type_stats,
            "product_stats": product_stats
        },
        "items": [
            {
                "name": item.name,
                "type": item.item_type,
                "description": item.description,
                "syntax": item.syntax,
                "parameters": item.parameters,
                "examples": item.examples,
                "related": item.related,
                "source_file": item.source_file,
                "source_page": item.source_page,
                "product": item.product,
                "category": item.category,
                "strategy_id": item.strategy_id,
                "confidence": item.confidence
            }
            for item in items
        ]
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Learning dataset saved to: {output_path}")

    return {
        "total_items": len(items),
        "type_stats": type_stats,
        "product_stats": product_stats
    }
