"""SFT ChatML 학습 데이터 생성기 (PDF 직접 추출)

기존 요약본을 사용하지 않고, uploads/manuals/ 의 245 PDF를
PyMuPDF로 직접 추출하여 Q-A 쌍을 생성합니다.

추출 흐름:
  uploads/manuals/{product_dir}/*.pdf
    → PyMuPDF 텍스트 추출
    → ComprehensiveParser 패턴 매칭 (command/config/api/concept)
    → Error Reference Guide: fix_error_descriptions.py Format A/B 로직
    → Q-A 템플릿 적용 (ja/ko/en)
    → SFT ChatML JSONL 출력
"""

import json
import re
import random
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from ..models.training import SFTRecord, DataLanguage, TrainingStats
from ..config import (
    config, PRODUCT_SYSTEM_PROMPTS, DEFAULT_SYSTEM_PROMPT,
    ERROR_PREFIX_TO_PRODUCT, DIRECTORY_TO_PRODUCT, DIRECTORY_LANGUAGE,
    PDF_COMPONENT_TO_PRODUCT, COMPONENT_SPLIT_DIRS,
)

logger = logging.getLogger(__name__)

# PyMuPDF
try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None
        logger.warning("PyMuPDF not available")

# ─── Q-A 템플릿 (5유형 × 3언어) ─────────────────────────

QA_TEMPLATES = {
    "error": {
        "ja": [
            "エラーコード {code} ({name}) の原因と対処方法を教えてください。",
            "エラー {code} が発生しました。原因は何ですか？",
            "{name} エラーの解決方法は？",
            "OpenFrameで {code} エラーが出る場合の対処法は？",
        ],
        "ko": [
            "에러코드 {code} ({name})의 원인과 해결방법을 알려주세요.",
            "에러 {code}가 발생했습니다. 원인이 무엇인가요?",
            "{name} 에러 해결방법은?",
            "OpenFrame에서 {code} 에러가 발생할 때 대처법은?",
        ],
        "en": [
            "What causes error code {code} ({name}) and how to resolve it?",
            "Error {code} occurred. What is the cause?",
            "How to fix {name} error?",
            "How to handle error {code} in OpenFrame?",
        ],
    },
    "command": {
        "ja": [
            "{name} コマンドの使い方と主なオプションを教えてください。",
            "{name} の構文と使用例は？",
            "{name} コマンドについて説明してください。",
        ],
        "ko": [
            "{name} 명령어의 사용법과 주요 옵션을 알려주세요.",
            "{name}의 구문과 사용 예시는?",
            "{name} 명령어에 대해 설명해주세요.",
        ],
        "en": [
            "How to use the {name} command and its main options?",
            "What is the syntax and usage examples of {name}?",
            "Explain the {name} command.",
        ],
    },
    "config": {
        "ja": [
            "{name} 設定パラメータの説明と設定方法を教えてください。",
            "{name} の設定値とデフォルト値は？",
            "{name} パラメータの意味は？",
        ],
        "ko": [
            "{name} 설정 파라미터의 설명과 설정 방법을 알려주세요.",
            "{name}의 설정값과 기본값은?",
            "{name} 파라미터의 의미는?",
        ],
        "en": [
            "What does the {name} configuration parameter do?",
            "What are the values and defaults for {name}?",
            "What does the {name} parameter mean?",
        ],
    },
    "api": {
        "ja": [
            "{name} 関数の使い方とパラメータを教えてください。",
            "{name}() の使用方法は？",
        ],
        "ko": [
            "{name} 함수의 사용법과 파라미터를 알려주세요.",
            "{name}()의 사용 방법은?",
        ],
        "en": [
            "How to use the {name} function and its parameters?",
            "How to use {name}()?",
        ],
    },
    "concept": {
        "ja": [
            "{name} とは何ですか？詳しく説明してください。",
            "{name} の概要と主な機能は？",
        ],
        "ko": [
            "{name}이란 무엇인가요? 자세히 설명해주세요.",
            "{name}의 개요와 주요 기능은?",
        ],
        "en": [
            "What is {name}? Please explain in detail.",
            "What is the overview and main features of {name}?",
        ],
    },
}

# ─── I-02: 한국어 응답 헤더 번역 매핑 ──────────────────
RESPONSE_HEADER_MAP = {
    "説明": "설명",
    "対処方法": "해결방법",
    "参考": "참고",
    "構文": "구문",
    "使用法": "사용법",
    "パラメータ": "파라미터",
    "戻り値": "반환값",
    "例": "예시",
    "注意": "주의",
    "デフォルト値": "기본값",
    "設定値": "설정값",
    "概要": "개요",
}

# 한국어 번역 시 보존할 기술 용어
PRESERVE_TERMS = frozenset({
    "OpenFrame", "Tibero", "Tmax", "JEUS", "WebtoB", "TACF", "TJES",
    "OSC", "OSI", "HiDB", "NDB", "AIM", "VSAM", "KSDS", "ESDS",
    "JCL", "COBOL", "PL/I", "tjesmgr", "tacfmgr", "hidbmgr",
    "oscmgr", "osimgr", "ndbmgr", "catmgr", "volmgr",
    "idcams", "iebgener", "iebcopy", "dfsort", "dsmigin", "dsmigout",
    "tmboot", "tmdown", "ofboot", "ofdown",
    "ProSort", "ProSync", "ProTrieve", "OFMiner", "OFStudio", "OFAsm",
    "OFCOBOL", "OFManager", "OFGW",
})

# 에러코드 응답 번역 테이블
RESPONSE_PHRASES = {
    "場合に発生します": {"ko": "경우에 발생합니다", "en": "This error occurs when"},
    "お問い合わせください": {"ko": "문의하시기 바랍니다", "en": "please contact technical support"},
    "再実行します": {"ko": "다시 실행합니다", "en": "retry the operation"},
    "確認してください": {"ko": "확인하시기 바랍니다", "en": "please verify"},
    "参照してください": {"ko": "참조하시기 바랍니다", "en": "please refer to"},
    "システム管理者に": {"ko": "시스템 관리자에게", "en": "the system administrator"},
}

# ─── 에러 추출 패턴 (fix_error_descriptions.py 로직) ─────

ERROR_NAME_PATTERN = re.compile(
    r"(?P<name>[A-Z][A-Z0-9_]+_ERR_[A-Z0-9_]+)\s*\((?P<code>-?\d+)\)"
)
ERROR_SECTION_PATTERN = re.compile(
    r"^\d+\.\d+\.?\s*(?P<module>[A-Za-z][A-Za-z0-9_-]+)\s*\((?P<code>-?\d+)\)\s*$",
    re.MULTILINE,
)
TOC_LINE_PATTERN = re.compile(
    r"^\d+\.\d+\.?\s*[A-Za-z][A-Za-z0-9_-]+\s*\(-?\d+\)\s*\.{2,}", re.MULTILINE
)
LABEL_PATTERN = re.compile(r"^(説明|対処方法|参考)\s*$", re.MULTILINE)
FOOTER_PATTERN = re.compile(
    r"^(第\d+章\s+.+\d+\s*$|\d+\s+OpenFrame\s+.+$|\d+\s+Tibero\s+.+$)",
    re.MULTILINE,
)

# ─── 매뉴얼 유형 판별 ───────────────────────────────────

MANUAL_TYPE_MAP = {
    "Error-Reference": "error",
    "Command-Reference": "command",
    "Tool-Reference": "command",
    "Utility-Reference": "command",
    "Configuration-Guide": "config",
    "Developer-Guide": "api",
    "Administrator-Guide": "concept",
    "User-Guide": "concept",
    "Installation-Guide": "concept",
    "Migration-Guide": "concept",
    "Base-Guide": "concept",
    "Batch-Guide": "concept",
    "TJES-Guide": "concept",
    "Dataset-Guide": "concept",
    "Reference-Guide": "command",
    "Language-Reference": "concept",
    "SQL-Reference": "concept",
    "Sort-Utility": "command",
    "IPF-Reference": "command",
}

# 구조 항목 추출용 패턴
COMMAND_RE = re.compile(
    r"^(?:第?\d+[章節]?\.?\d*\.?\s*)?([a-z][a-z0-9_-]{2,})\s*(?:コマンド|command|ユーティリティ|utility)",
    re.MULTILINE | re.IGNORECASE,
)
CONFIG_RE = re.compile(
    r"^([A-Z][A-Z0-9_]{2,})\s*[=:]\s*(.+?)(?:\s*#|$)", re.MULTILINE
)
API_RE = re.compile(
    r"([a-z]{2,6}_[a-z_]+)\s*\(\)", re.MULTILINE
)

# 필터링: 일반적 단어
SKIP_WORDS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "chapter",
    "section", "guide", "reference", "manual", "page", "table",
    "figure", "example", "note", "warning", "appendix", "index",
    "overview", "introduction", "summary", "contents", "copyright",
    "openframe", "tibero", "tmax", "tmaxsoft",
})

# Installation Guide 저품질 콘텐츠 필터 패턴
INSTALL_JUNK_PATTERNS = [
    re.compile(r"={5,}"),                          # ======= 구분선
    re.compile(r"-{5,}"),                          # ------- 구분선
    re.compile(r"\[={10,}\|"),                     # [========|========] 진행바
    re.compile(r"Preparing .+ Installation"),       # Preparing CONSOLE Mode Installation
    re.compile(r"Choose Install (?:Folder|Set)"),   # Choose Install Folder/Set
    re.compile(r"ENTER AN ABSOLUTE PATH"),          # 설치 경로 입력 프롬프트
    re.compile(r"InstallAnywhere"),                 # InstallAnywhere installer
    re.compile(r"License Agreement"),               # 라이센스 동의
    re.compile(r"End-User License"),                # EULA
    re.compile(r"Installing\.\.\.", re.IGNORECASE), # Installing...
    re.compile(r"Extracting the installation"),     # Extracting resources
    re.compile(r"Launching installer"),             # Launching installer
    re.compile(r"->?\d+- "),                        # ->1- Install option 선택지
    re.compile(r"Directory Check"),                 # 디렉토리 확인 프롬프트
    re.compile(r"User Specified Directory"),        # 설치 디렉토리 메시지
    re.compile(r"To overwrite Open"),               # 덮어쓰기 확인
    re.compile(r"索引\.{3,}"),                      # 索引.............. 45 (인덱스 페이지)
    re.compile(r"#.+InstallAnywhere"),              # InstallAnywhere 설정 코멘트
    re.compile(r"#\s*New environment setting added"),# 환경변수 자동 추가 코멘트
    re.compile(r"#\s*The unmodified version"),       # 자동 백업 코멘트
    re.compile(r"#\s*End comments by"),              # 자동 끝 코멘트
    re.compile(r"#\s*Do NOT modify these lines"),    # 수정 금지 코멘트
]

# Installation Guide에서 허용되는 유의미 제목 패턴
INSTALL_USEFUL_TITLES = re.compile(
    r"(?:システム要件|環境設定|環境変数|properties\.conf|"
    r"コンパイル|ofasm|ofasmif|ofcbpp|マクロ|エラーコード|"
    r"アンインストール|バージョン確認|ライブラリ|"
    r"system.+requirements?|configuration|environment|compile|"
    r"uninstall|version.+check|library)",
    re.IGNORECASE,
)


class SFTGenerator:
    """SFT ChatML 학습 데이터 생성 (PDF 직접 추출)"""

    def __init__(self, manuals_dir: Path, output_dir: Path):
        self.manuals_dir = manuals_dir
        self.output_dir = output_dir
        self.records: List[SFTRecord] = []

    def generate_all(self, languages: List[str] = None) -> TrainingStats:
        """전체 PDF에서 SFT 데이터 생성

        각 PDF의 원본 언어(dir_lang)와 일치하는 언어로만 Q-A를 생성합니다.
        일본어 PDF → ja Q-A만, 한국어 PDF → ko Q-A만 생성하여
        응답 언어 불일치(일본어 응답 + 한국어 질문) 문제를 방지합니다.
        """
        if languages is None:
            languages = ["ja", "ko", "en"]

        if pymupdf is None:
            raise RuntimeError("PyMuPDF is required for SFT generation")

        stats = TrainingStats()
        self.records = []

        logger.info(f"[SFT] PDF 직접 추출 시작 - 허용 언어: {languages}")

        # I-01: COMPONENT_SPLIT_DIRS 간 중복 PDF 제거
        dedup_skip = self._deduplicate_component_pdfs()
        if dedup_skip:
            logger.info(f"  [Dedup] {len(dedup_skip)}개 중복 PDF 건너뜀 (가장 큰 버전만 사용)")

        # 모든 제품 디렉토리 순회
        total_pdfs = 0
        skipped_lang = 0
        skipped_dedup = 0
        for product_dir in sorted(self.manuals_dir.iterdir()):
            if not product_dir.is_dir():
                continue

            dir_product_id = DIRECTORY_TO_PRODUCT.get(product_dir.name, "unknown_product")
            dir_lang = DIRECTORY_LANGUAGE.get(product_dir.name, "ja")
            use_component_split = product_dir.name in COMPONENT_SPLIT_DIRS

            # PDF 원본 언어가 요청 언어에 없으면 skip
            if dir_lang not in languages:
                skipped_lang += 1
                continue

            pdf_files = sorted(product_dir.glob("*.pdf"))
            if not pdf_files:
                continue

            logger.info(
                f"  [{product_dir.name}] {len(pdf_files)} PDFs "
                f"→ dir_product={dir_product_id}, lang={dir_lang}"
                f"{', component_split=ON' if use_component_split else ''}"
            )

            for pdf_path in pdf_files:
                # I-01: 중복 제거 대상이면 건너뜀
                if str(pdf_path) in dedup_skip:
                    logger.debug(f"    [Dedup] Skip: {pdf_path.name}")
                    skipped_dedup += 1
                    continue
                try:
                    # PDF 파일명에서 컴포넌트별 product_id 결정
                    product_id = self._resolve_product_id(
                        pdf_path.name, dir_product_id, use_component_split
                    )

                    manual_type = self._detect_manual_type(pdf_path.name)
                    count_before = len(self.records)

                    if manual_type == "error":
                        self._extract_errors_from_pdf(
                            pdf_path, product_id, dir_lang
                        )
                    else:
                        self._extract_items_from_pdf(
                            pdf_path, product_id, dir_lang, manual_type
                        )

                    added = len(self.records) - count_before
                    if added > 0:
                        logger.debug(f"    {pdf_path.name}: +{added} → {product_id}")
                    total_pdfs += 1

                except Exception as e:
                    logger.warning(f"    Error: {pdf_path.name}: {e}")

        if skipped_lang:
            logger.info(f"  언어 필터로 {skipped_lang}개 디렉토리 건너뜀")
        if skipped_dedup:
            logger.info(f"  [Dedup] 중복 PDF 건너뜀: {skipped_dedup}개")

        # I-01: 레코드 레벨 중복 제거 (동일 제품+질문 제거)
        dedup_before = len(self.records)
        self.records = self._deduplicate_records(self.records)
        dedup_removed = dedup_before - len(self.records)
        if dedup_removed:
            logger.info(f"  [Dedup] 레코드 중복 제거: {dedup_removed}건 (남은: {len(self.records)}건)")

        # I-02: 일본어 레코드에서 한국어 Q-A 자동 생성
        if "ko" in languages:
            ko_generated = self._generate_korean_from_japanese()
            if ko_generated:
                logger.info(f"  [I-02] 한국어 Q-A 생성: {ko_generated}건 추가")

        # I-04: 소량 제품 데이터 증강 (100건 미만 → 패러프레이즈 증강)
        aug_generated = self._augment_small_products(min_records=100)
        if aug_generated:
            logger.info(f"  [I-04] 소량 제품 증강: {aug_generated}건 추가")

        # 통계
        stats.total_records = len(self.records)
        for r in self.records:
            stats.by_language[r.language.value] = stats.by_language.get(r.language.value, 0) + 1
            stats.by_product[r.product] = stats.by_product.get(r.product, 0) + 1
            stats.by_type[r.item_type] = stats.by_type.get(r.item_type, 0) + 1
        stats.by_format["sft"] = stats.total_records

        # Train/Eval 분할
        train, eval_ = self._stratified_split(self.records, ratio=0.8)
        stats.train_count = len(train)
        stats.eval_count = len(eval_)

        # 출력
        sft_dir = Path(self.output_dir) / "sft"
        sft_dir.mkdir(parents=True, exist_ok=True)
        self._write_jsonl(train, sft_dir / "train_all.jsonl")
        self._write_jsonl(eval_, sft_dir / "eval_all.jsonl")
        self._write_by_product(train, eval_, sft_dir)

        logger.info(
            f"[SFT] 완료: {total_pdfs} PDFs → {stats.total_records} records "
            f"(train={stats.train_count}, eval={stats.eval_count})"
        )
        return stats

    # ─── PDF 파일명 → product_id 해석 ──────────────────────

    @staticmethod
    def _resolve_product_id(
        pdf_filename: str, dir_product_id: str, use_component_split: bool
    ) -> str:
        """PDF 파일명에서 컴포넌트를 추출하여 product_id를 결정

        MVS/MSP/XSP 디렉토리의 PDF는 "OF_{Component}_..." 패턴이므로
        Component로 제품을 분리합니다.
          OF_Base_7.1_Base-Guide_v3.1.2_jp.pdf   → "Base" → openframe_base_v2
          OF_HiDB_7.2_HiDB-Guide_v3.1.2_jp.pdf  → "HiDB" → openframe_hidb_v2
          OF_AIM_7.3_Administrator-Guide_...pdf   → "AIM"  → openframe_aim_v2
          OFManager_MSP_7.2_User-Guide_...pdf     → "Manager" (OFManager prefix)
        """
        if not use_component_split:
            return dir_product_id

        stem = pdf_filename.replace(".pdf", "")

        # Pattern 1: "OF_{Component}_..." (대부분의 OpenFrame PDF)
        if stem.startswith("OF_"):
            parts = stem.split("_")
            if len(parts) >= 2:
                component = parts[1]
                mapped = PDF_COMPONENT_TO_PRODUCT.get(component)
                if mapped:
                    return mapped

        # Pattern 2: "OFManager_..." (OFManager PDF in MSP)
        if stem.startswith("OFManager"):
            return "ofmanager_v2"

        # 매핑 없으면 디렉토리 기본값 사용
        return dir_product_id

    @staticmethod
    def _deduplicate_records(records: List[SFTRecord]) -> List[SFTRecord]:
        """레코드 레벨 중복 제거 (I-01)

        같은 제품에서 동일한 질문(instruction)이 있으면 첫 번째만 유지합니다.
        또한 응답이 80% 이상 겹치는 레코드도 중복으로 처리합니다.
        """
        seen_keys = set()
        unique = []
        for r in records:
            # 제품 + 질문 정규화 키
            norm_instruction = re.sub(r"\s+", " ", r.instruction).strip().lower()
            key = (r.product, norm_instruction)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # 제품 + 응답 첫 100자로 유사 응답 필터
            norm_response = re.sub(r"\s+", " ", r.response).strip()[:100].lower()
            resp_key = (r.product, r.item_type, norm_response)
            if resp_key in seen_keys:
                continue
            seen_keys.add(resp_key)

            unique.append(r)
        return unique

    def _deduplicate_component_pdfs(self) -> set:
        """COMPONENT_SPLIT_DIRS 간 중복 PDF 제거 (I-01)

        MVS/MSP/XSP 디렉토리에 같은 컴포넌트(Base, Batch, OSC 등)의
        같은 가이드 유형 PDF가 존재할 때, 가장 큰 파일만 사용합니다.

        예: OF_Base_7.1_Base-Guide_v3.1.2_jp.pdf (MVS, 2.5MB)
            OF_Base_7.3_Base-Guide_v2.1.1_jp.pdf (MSP, 2.1MB)
            → MVS 버전만 유지 (더 큰 파일 = 더 상세한 내용)

        Returns:
            건너뛸 PDF 파일 경로들의 set
        """
        # (component, guide_type) → [(path, size)] 수집
        component_pdfs: Dict[Tuple[str, str], List[Tuple[Path, int]]] = defaultdict(list)

        for dir_name in COMPONENT_SPLIT_DIRS:
            product_dir = self.manuals_dir / dir_name
            if not product_dir.is_dir():
                continue

            for pdf_path in product_dir.glob("*.pdf"):
                stem = pdf_path.stem
                # OF_{Component}_{Version}_{GuideType}_... 파싱
                if stem.startswith("OF_"):
                    parts = stem.split("_")
                    if len(parts) >= 4:
                        component = parts[1]
                        # 가이드 유형 추출 (4번째~, "-" 결합)
                        guide_parts = []
                        for p in parts[3:]:
                            if p.startswith("v") and re.match(r"v\d", p):
                                break
                            guide_parts.append(p)
                        guide_type = "-".join(guide_parts) if guide_parts else "unknown"

                        key = (component, guide_type)
                        component_pdfs[key].append((pdf_path, pdf_path.stat().st_size))
                elif stem.startswith("OFManager"):
                    # OFManager_MSP_7.2_User-Guide_... 패턴
                    parts = stem.split("_")
                    guide_parts = []
                    for p in parts[3:]:
                        if p.startswith("v") and re.match(r"v\d", p):
                            break
                        guide_parts.append(p)
                    guide_type = "-".join(guide_parts) if guide_parts else "unknown"
                    key = ("Manager", guide_type)
                    component_pdfs[key].append((pdf_path, pdf_path.stat().st_size))

        # 각 그룹에서 가장 큰 파일만 남기고 나머지를 skip set에 추가
        skip_set = set()
        for key, pdf_list in component_pdfs.items():
            if len(pdf_list) <= 1:
                continue
            # 크기 내림차순 정렬 → 첫 번째(가장 큰)만 유지
            pdf_list.sort(key=lambda x: x[1], reverse=True)
            keeper = pdf_list[0]
            for pdf_path, size in pdf_list[1:]:
                skip_set.add(str(pdf_path))
                logger.debug(
                    f"  [Dedup] {key}: skip {pdf_path.name} ({size//1024}KB) "
                    f"← keep {keeper[0].name} ({keeper[1]//1024}KB)"
                )

        return skip_set

    # ─── Error Reference Guide 추출 ──────────────────────

    def _extract_errors_from_pdf(
        self, pdf_path: Path, product_id: str, src_lang: str,
    ):
        """Error Reference Guide PDF에서 에러코드 Q-A 직접 추출

        fix_error_descriptions.py 의 Format A/B 자동감지 로직을 사용합니다.
        src_lang: PDF 원본 언어 (응답도 이 언어로 생성)
        """
        doc = pymupdf.open(str(pdf_path))
        full_text = ""
        for page in doc:
            full_text += page.get_text("text") + "\n"
        doc.close()

        # TOC 라인 제거
        full_text = TOC_LINE_PATTERN.sub("", full_text)

        # 모듈 섹션 분리
        section_matches = list(ERROR_SECTION_PATTERN.finditer(full_text))
        if not section_matches:
            return

        for i, match in enumerate(section_matches):
            module_name = match.group("module")
            start = match.start()
            end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(full_text)
            section_text = full_text[start:end]

            # 에러 코드 추출
            error_matches = list(ERROR_NAME_PATTERN.finditer(section_text))
            for j, ematch in enumerate(error_matches):
                error_name = ematch.group("name")
                error_code = ematch.group("code")

                e_start = ematch.end()
                e_end = error_matches[j + 1].start() if j + 1 < len(error_matches) else len(section_text)
                error_text = section_text[e_start:e_end]

                desc, solution, reference = self._extract_error_fields(error_text)
                if not desc and not solution:
                    continue

                # PDF 원본 언어로만 Q-A 생성 (언어 불일치 방지)
                lang = src_lang
                template = random.choice(QA_TEMPLATES["error"][lang])
                instruction = template.format(code=error_code, name=error_name)
                response = self._build_error_response(
                    error_code, error_name, desc, solution, reference, lang
                )
                if not response or len(response) < 20:
                    continue

                # 에러 모듈에서 제품 결정
                err_product = self._error_module_to_product(module_name, product_id)
                sys_prompt = self._get_system_prompt(err_product, lang)

                self.records.append(SFTRecord(
                    instruction=instruction,
                    response=response,
                    system_prompt=sys_prompt,
                    product=err_product,
                    language=DataLanguage(lang),
                    source_file=pdf_path.name,
                    item_type="error",
                ))

    def _extract_error_fields(self, error_text: str) -> Tuple[str, str, str]:
        """에러 텍스트에서 설명/대처방법/참고 추출 (Format A/B 자동감지)"""
        lines = error_text.split("\n")

        label_positions = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped in ("説明", "対処方法", "参考"):
                label_positions.append((i, stripped))

        if not label_positions:
            cleaned = self._clean_text(error_text)
            return cleaned, "", ""

        first_label_idx = label_positions[0][0]
        text_before = "\n".join(lines[:first_label_idx])
        content_before = self._clean_text(text_before)

        if content_before:
            return self._extract_format_a(lines, label_positions, content_before)
        else:
            return self._extract_format_b(lines, label_positions)

    def _extract_format_a(
        self, lines, label_positions, content_before
    ) -> Tuple[str, str, str]:
        """Format A: labels AFTER content (Base modules)"""
        description = content_before
        solution = ""
        reference = ""

        for i, (pos, label) in enumerate(label_positions):
            next_pos = label_positions[i + 1][0] if i + 1 < len(label_positions) else len(lines)
            content = self._clean_text("\n".join(lines[pos + 1:next_pos]))
            if label == "説明":
                solution = content
            elif label == "対処方法":
                reference = content

        return description, solution, reference

    def _extract_format_b(self, lines, label_positions) -> Tuple[str, str, str]:
        """Format B: labels BEFORE content (AIM/NDB/PSAM)"""
        description = ""
        solution = ""
        reference = ""

        for i, (pos, label) in enumerate(label_positions):
            next_pos = label_positions[i + 1][0] if i + 1 < len(label_positions) else len(lines)
            content = self._clean_text("\n".join(lines[pos + 1:next_pos]))
            if label == "説明":
                description = content
            elif label == "対処方法":
                solution = content
            elif label == "参考":
                reference = content

        return description, solution, reference

    def _error_module_to_product(self, module_name: str, default_product: str) -> str:
        """에러 모듈명 → 제품 ID"""
        m = module_name.upper()
        if m in ("TJES", "SPOOL", "MVSSYS", "TSO"):
            return "openframe_batch_v2"
        if m in ("TACF", "SAF", "SAFB", "SAFX", "SAFO"):
            return "openframe_common_v2"
        if m in ("PSAM", "AIMCOM", "AIMACP", "AIMCTL", "AIMAIS", "AIMSMR",
                  "AIMCMD", "AIM", "ADL", "AIMTOOL", "DDMS"):
            return "openframe_common_v2"
        if m in ("NDB", "NDBMETA", "NDBRSTD"):
            return "openframe_common_v2"
        return default_product

    # ─── 일반 매뉴얼 추출 (command/config/api/concept) ───

    def _extract_items_from_pdf(
        self, pdf_path: Path, product_id: str, src_lang: str,
        manual_type: str,
    ):
        """일반 매뉴얼 PDF에서 구조화 항목 추출 후 Q-A 생성

        src_lang: PDF 원본 언어 (응답도 이 언어로 생성)
        """
        doc = pymupdf.open(str(pdf_path))
        lang = src_lang

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if not text or len(text.strip()) < 50:
                continue

            # 페이지 텍스트를 섹션으로 분리
            sections = self._split_sections(text)

            is_install_pdf = self._is_installation_pdf(pdf_path.name)

            for title, content in sections:
                if not title or len(content) < 30:
                    continue

                # Installation Guide: 저품질 콘텐츠 필터링
                if is_install_pdf and self._is_install_junk(title, content):
                    continue

                # 지정 타입으로 추출 시도 → 실패 시 concept fallback
                item = self._extract_item(
                    title, content, manual_type, pdf_path.name, page_num + 1
                )
                if not item and manual_type in ("api", "command", "config"):
                    item = self._try_extract_concept(title, content)

                if not item:
                    continue

                name = item["name"]
                item_type = item["type"]
                description = self._clean_response(item["description"])
                syntax = item.get("syntax", "")

                if not description or len(description) < 20:
                    continue

                templates = QA_TEMPLATES.get(item_type, QA_TEMPLATES["concept"])
                template = random.choice(templates[lang])
                instruction = template.format(name=name, code="")

                response = self._build_item_response(
                    name, description, syntax, item_type, lang
                )
                if not response or len(response) < 30:
                    continue

                # 저품질 응답 필터 (목차 잔여, 인덱스 페이지 등)
                if self._is_low_quality_response(response):
                    continue

                sys_prompt = self._get_system_prompt(product_id, lang)
                self.records.append(SFTRecord(
                    instruction=instruction,
                    response=response,
                    system_prompt=sys_prompt,
                    product=product_id,
                    language=DataLanguage(lang),
                    source_file=pdf_path.name,
                    source_page=page_num + 1,
                    item_type=item_type,
                ))

        doc.close()

    def _split_sections(self, text: str) -> List[Tuple[str, str]]:
        """텍스트를 섹션 (제목, 본문) 쌍으로 분할"""
        header_re = re.compile(
            r"^((?:\d+\.)+\s*.+?)$"       # 1.2.3. Title
            r"|^(第\d+[章節]\s*.+?)$"       # 第1章 Title
            r"|^([A-Z]\.\d+\.\d+\.\s*.+?)$" # B.4.5. func()
            r"|^(■.+?)$"                    # ■ Title
        , re.MULTILINE)

        sections = []
        lines = text.split("\n")
        current_title = ""
        current_content = []

        for line in lines:
            if header_re.match(line.strip()):
                if current_title or current_content:
                    sections.append((current_title, "\n".join(current_content)))
                current_title = line.strip()
                current_content = []
            else:
                current_content.append(line)

        if current_title or current_content:
            sections.append((current_title, "\n".join(current_content)))

        return sections

    def _extract_item(
        self, title: str, content: str, manual_type: str,
        filename: str, page_num: int,
    ) -> Optional[Dict]:
        """섹션에서 구조화 항목 추출"""
        if manual_type == "command":
            return self._try_extract_command(title, content)
        elif manual_type == "config":
            return self._try_extract_config(title, content)
        elif manual_type == "api":
            return self._try_extract_api(title, content)
        else:
            return self._try_extract_concept(title, content)

    def _try_extract_command(self, title: str, content: str) -> Optional[Dict]:
        """명령어 추출"""
        cmd_match = re.search(r"([a-zA-Z][a-zA-Z0-9_-]{2,})", title)
        if not cmd_match:
            return None

        name = cmd_match.group(1)
        if name.lower() in SKIP_WORDS or len(name) < 3:
            return None

        desc = self._extract_desc(content)
        syntax = self._extract_syntax(content)

        if not desc and not syntax:
            return None

        return {"name": name, "type": "command",
                "description": desc or title, "syntax": syntax}

    def _try_extract_config(self, title: str, content: str) -> Optional[Dict]:
        """설정 파라미터 추출"""
        param_match = re.search(r"([A-Z][A-Z0-9_]{2,})", title)
        if not param_match:
            return None

        name = param_match.group(1)
        if len(name) < 3:
            return None

        desc = self._extract_desc(content)
        if not desc:
            return None

        return {"name": name, "type": "config", "description": desc, "syntax": ""}

    def _try_extract_api(self, title: str, content: str) -> Optional[Dict]:
        """API/함수 추출"""
        func_match = re.search(r"([a-zA-Z_][a-zA-Z0-9_]+)\s*\(", title)
        if not func_match:
            func_match = re.search(
                r"(?:int|void|char|long|BOOL)\s+([a-zA-Z_][a-zA-Z0-9_]+)\s*\(",
                content
            )
        if not func_match:
            return None

        name = func_match.group(1)
        desc = self._extract_desc(content)
        if not desc:
            return None

        return {"name": name, "type": "api", "description": desc, "syntax": ""}

    def _try_extract_concept(self, title: str, content: str) -> Optional[Dict]:
        """개념/정의 추출"""
        # 제목에서 의미있는 이름 추출
        concept_match = re.search(
            r"([A-Za-z][A-Za-z0-9_-]+(?:\s+[A-Za-z][A-Za-z0-9_-]+){0,3})", title
        )
        if not concept_match:
            # CJK 제목도 허용 (日本語/한국어)
            cjk_match = re.search(
                r"([\u3040-\u9FFF\uAC00-\uD7A3]{2,}(?:\s*[\u3040-\u9FFF\uAC00-\uD7A3]+){0,3})",
                title,
            )
            if not cjk_match:
                return None
            name = cjk_match.group(1).strip()
        else:
            name = concept_match.group(1).strip()

        if len(name) < 3 or name.lower() in SKIP_WORDS:
            return None

        # 본문이 충분히 길어야 의미있는 개념
        cleaned_content = content.strip()
        if len(cleaned_content) < 80:
            return None

        desc = cleaned_content[:500]
        return {"name": name, "type": "concept", "description": desc, "syntax": ""}

    def _extract_desc(self, content: str) -> str:
        """본문에서 설명 추출"""
        desc_match = re.search(
            r"(?:説明|Description|설명|概要|Overview)[:：]?\s*(.+?)(?:\n\n|\n(?:使用法|Usage|構文|Syntax|パラメータ|Parameters)|$)",
            content, re.DOTALL | re.IGNORECASE
        )
        if desc_match:
            return desc_match.group(1).strip()[:500]

        # 설명 라벨이 없으면 본문 자체를 사용 (짧게)
        cleaned = content.strip()
        if len(cleaned) > 30:
            return cleaned[:500]
        return ""

    def _extract_syntax(self, content: str) -> str:
        """본문에서 구문 추출"""
        syntax_match = re.search(
            r"(?:使用法|Usage|構文|Syntax)[:：]?\s*\n?\s*(.+?)(?:\n\n|\n(?:パラメータ|Parameters|引数)|$)",
            content, re.DOTALL | re.IGNORECASE
        )
        return syntax_match.group(1).strip()[:300] if syntax_match else ""

    # ─── 응답 생성 ───────────────────────────────────────

    def _build_error_response(
        self, code: str, name: str, desc: str, solution: str,
        reference: str, lang: str,
    ) -> str:
        """에러코드 응답 생성 (3언어)"""
        if lang == "ja":
            parts = [f"エラー {code} ({name})"]
            if desc:
                parts.append(f"\n説明: {desc}")
            if solution:
                parts.append(f"\n対処方法: {solution}")
            if reference:
                parts.append(f"\n参考: {reference}")
            return "".join(parts)
        elif lang == "ko":
            parts = [f"에러 {code} ({name})"]
            if desc:
                parts.append(f"\n설명: {self._translate_phrase(desc, 'ko')}")
            if solution:
                parts.append(f"\n해결방법: {self._translate_phrase(solution, 'ko')}")
            return "".join(parts)
        else:
            parts = [f"Error {code} ({name})"]
            if desc:
                parts.append(f"\nDescription: {self._translate_phrase(desc, 'en')}")
            if solution:
                parts.append(f"\nResolution: {self._translate_phrase(solution, 'en')}")
            return "".join(parts)

    def _build_item_response(
        self, name: str, desc: str, syntax: str,
        item_type: str, lang: str,
    ) -> str:
        """일반 항목 응답 생성"""
        if lang == "ja":
            parts = [name]
            if desc:
                parts.append(f"\n{desc}")
            if syntax:
                parts.append(f"\n構文: {syntax}")
            return "".join(parts)
        elif lang == "ko":
            parts = [name]
            if desc:
                parts.append(f"\n{self._translate_phrase(desc, 'ko')}")
            if syntax:
                parts.append(f"\n구문: {syntax}")
            return "".join(parts)
        else:
            parts = [name]
            if desc:
                parts.append(f"\n{self._translate_phrase(desc, 'en')}")
            if syntax:
                parts.append(f"\nSyntax: {syntax}")
            return "".join(parts)

    # ─── 유틸리티 ─────────────────────────────────────────

    # ─── I-02: 한국어 Q-A 자동 생성 ──────────────────────

    def _generate_korean_from_japanese(self) -> int:
        """일본어 레코드에서 한국어 Q-A를 템플릿 기반으로 생성 (I-02)

        - 일본어 질문 → 한국어 질문 템플릿으로 교체
        - 일본어 응답 → 헤더만 한국어로 번역 (기술 내용은 원문 유지)
        - JEUS 등 이미 한국어 레코드가 있는 제품은 건너뜀
        """
        # 이미 한국어 레코드가 있는 제품 확인
        ko_products = set()
        for r in self.records:
            if r.language == DataLanguage("ko"):
                ko_products.add(r.product)

        # 일본어 레코드 중 한국어가 없는 제품의 레코드 수집
        ja_records_by_product = defaultdict(list)
        for r in self.records:
            if r.language == DataLanguage("ja") and r.product not in ko_products:
                ja_records_by_product[r.product].append(r)

        if not ja_records_by_product:
            return 0

        generated = 0
        for product, ja_records in ja_records_by_product.items():
            # 각 제품에서 최대 60% 레코드를 한국어로 변환
            sample_size = max(1, int(len(ja_records) * 0.6))
            sampled = random.sample(ja_records, min(sample_size, len(ja_records)))

            for r in sampled:
                ko_instruction = self._translate_question_to_korean(
                    r.instruction, r.item_type
                )
                if not ko_instruction:
                    continue

                ko_response = self._translate_response_headers(r.response)
                ko_sys = self._get_system_prompt(product, "ko")

                self.records.append(SFTRecord(
                    instruction=ko_instruction,
                    response=ko_response,
                    system_prompt=ko_sys,
                    product=product,
                    language=DataLanguage("ko"),
                    source_file=r.source_file,
                    source_page=r.source_page,
                    item_type=r.item_type,
                ))
                generated += 1

        return generated

    @staticmethod
    def _translate_question_to_korean(ja_question: str, item_type: str) -> str:
        """일본어 질문을 한국어 템플릿으로 변환

        기술 용어(영문)는 보존하고, 일본어 문장 패턴만 한국어로 교체합니다.
        """
        templates = QA_TEMPLATES.get(item_type, QA_TEMPLATES["concept"])
        ko_templates = templates.get("ko", [])
        if not ko_templates:
            return ""

        # 질문에서 기술 용어(name/code) 추출
        # 에러코드 패턴: "エラーコード -5212 (DSALC_ERR_...)" or "エラー -5212"
        error_match = re.search(r"(-?\d{3,5})\s*\(([A-Z_]+)\)", ja_question)
        if error_match and item_type == "error":
            code = error_match.group(1)
            name = error_match.group(2)
            template = random.choice(ko_templates)
            return template.format(code=code, name=name)

        # 일반 항목: 영문 기술 용어 또는 CJK 용어 추출
        name_match = re.search(
            r"([A-Za-z][A-Za-z0-9_.-]+(?:\s+[A-Za-z][A-Za-z0-9_.-]+){0,3})",
            ja_question,
        )
        if not name_match:
            # CJK 용어 추출
            name_match = re.search(
                r"([\u3040-\u9FFF\uAC00-\uD7A3]{2,}(?:\s*[\u3040-\u9FFF\uAC00-\uD7A3]+){0,3})",
                ja_question,
            )
        if not name_match:
            return ""

        name = name_match.group(1).strip()
        template = random.choice(ko_templates)
        return template.format(name=name, code="")

    @staticmethod
    def _translate_response_headers(ja_response: str) -> str:
        """일본어 응답의 헤더/라벨만 한국어로 변환

        기술적 내용은 원문 유지하고, 구조 헤더만 번역합니다.
        """
        result = ja_response
        for ja_header, ko_header in RESPONSE_HEADER_MAP.items():
            # "ラベル: 内容" → "라벨: 내용"
            result = result.replace(f"{ja_header}: ", f"{ko_header}: ")
            result = result.replace(f"{ja_header}:", f"{ko_header}:")
            # 단독 라벨 줄 "●ラベル" → "●라벨"
            result = result.replace(f"●{ja_header}", f"●{ko_header}")

        # 일반 응답 구문 번역
        for ja_phrase, translations in RESPONSE_PHRASES.items():
            if ja_phrase in result and "ko" in translations:
                result = result.replace(ja_phrase, translations["ko"])

        return result

    # ─── I-04: 소량 제품 데이터 증강 ──────────────────────

    # 교차제품 Q-A 생성 대상 (소량 제품 → 관련 대량 제품)
    CROSS_PRODUCT_MAP = {
        "openframe_hidb_v2": ["openframe_osc_v2", "openframe_batch_v2"],
        "ofasm_v2": ["openframe_common_v2", "ofcobol_v2"],
        "openframe_gateway_v2": ["openframe_osc_v2", "openframe_common_v2"],
        "openframe_ndb_v2": ["openframe_common_v2", "openframe_batch_v2"],
    }

    CROSS_PRODUCT_TEMPLATES = {
        "ja": [
            "{src_name} と {rel_name} の連携方法を教えてください。",
            "{src_name} 環境で {rel_name} を使用する際の注意点は？",
        ],
        "ko": [
            "{src_name}과 {rel_name}의 연동 방법을 알려주세요.",
            "{src_name} 환경에서 {rel_name}을 사용할 때 주의사항은?",
        ],
    }

    # 제품 표시명
    PRODUCT_DISPLAY_NAMES = {
        "openframe_hidb_v2": "HiDB",
        "ofasm_v2": "OFAsm",
        "openframe_gateway_v2": "OpenFrame Gateway",
        "openframe_ndb_v2": "NDB",
        "openframe_osc_v2": "OSC",
        "openframe_batch_v2": "OpenFrame Batch",
        "openframe_common_v2": "OpenFrame",
        "ofcobol_v2": "OFCOBOL",
    }

    # 패러프레이즈 질문 변형 패턴
    AUGMENT_QUESTION_VARIANTS = {
        "ja": [
            "{name} について教えてください。",
            "{name} の詳細を説明してください。",
            "{name} はどのように動作しますか？",
            "{name} を使用する際の注意点は？",
            "{name} の使い方を初心者向けに説明してください。",
            "{name} に関する技術的な説明をお願いします。",
        ],
        "ko": [
            "{name}에 대해 알려주세요.",
            "{name}의 상세 내용을 설명해주세요.",
            "{name}은 어떻게 동작하나요?",
            "{name}을 사용할 때 주의사항은?",
            "{name}의 사용법을 초보자 수준으로 설명해주세요.",
            "{name}에 관한 기술적인 설명을 부탁합니다.",
        ],
    }

    def _augment_small_products(self, min_records: int = 100) -> int:
        """소량 제품 데이터 증강 (I-04)

        min_records 미만의 제품에 대해:
        1. 기존 레코드를 패러프레이즈 변형하여 증강
        2. 교차제품 Q-A 생성 (HiDB+OSC, OFASM+COBOL 등)
        """
        by_product = defaultdict(list)
        for r in self.records:
            by_product[r.product].append(r)

        generated = 0

        # Phase 1: 교차제품 Q-A 생성
        for src_product, rel_products in self.CROSS_PRODUCT_MAP.items():
            src_records = by_product.get(src_product, [])
            if not src_records:
                continue

            src_name = self.PRODUCT_DISPLAY_NAMES.get(src_product, src_product)
            for rel_product in rel_products:
                rel_records = by_product.get(rel_product, [])
                if not rel_records:
                    continue

                rel_name = self.PRODUCT_DISPLAY_NAMES.get(rel_product, rel_product)
                # 교차제품 Q-A 5개씩 생성
                sample_rel = random.sample(rel_records, min(5, len(rel_records)))
                for rel_r in sample_rel:
                    for lang_key in ("ja", "ko"):
                        templates = self.CROSS_PRODUCT_TEMPLATES.get(lang_key, [])
                        if not templates:
                            continue
                        template = random.choice(templates)
                        instruction = template.format(
                            src_name=src_name, rel_name=rel_name
                        )
                        # 응답은 관련 제품의 콘텐츠 기반
                        response = (
                            f"{src_name}と{rel_name}の連携\n{rel_r.response[:400]}"
                            if lang_key == "ja"
                            else f"{src_name}과 {rel_name} 연동\n{self._translate_response_headers(rel_r.response[:400])}"
                        )
                        sys_prompt = self._get_system_prompt(src_product, lang_key)
                        self.records.append(SFTRecord(
                            instruction=instruction,
                            response=response,
                            system_prompt=sys_prompt,
                            product=src_product,
                            language=DataLanguage(lang_key),
                            source_file=rel_r.source_file,
                            item_type="concept",
                        ))
                        generated += 1

        # Refresh product counts after cross-product generation
        by_product = defaultdict(list)
        for r in self.records:
            by_product[r.product].append(r)

        # Phase 2: 패러프레이즈 증강 (min_records 미만 제품)
        for product, records in by_product.items():
            if len(records) >= min_records:
                continue

            needed = min_records - len(records)
            logger.info(
                f"  [I-04] {product}: {len(records)}건 → 목표 {min_records}건 "
                f"(+{needed}건 증강)"
            )

            # 기존 레코드를 순환하며 패러프레이즈 생성
            source_records = list(records)
            aug_count = 0
            attempts = 0
            max_attempts = needed * 3

            while aug_count < needed and attempts < max_attempts:
                src = source_records[attempts % len(source_records)]
                attempts += 1

                # 질문에서 name 추출
                name = self._extract_name_from_instruction(src.instruction)
                if not name:
                    continue

                lang = src.language.value
                variants = self.AUGMENT_QUESTION_VARIANTS.get(lang, [])
                if not variants:
                    continue

                variant_template = variants[aug_count % len(variants)]
                new_instruction = variant_template.format(name=name)

                # 이미 동일한 질문이 있으면 건너뜀
                norm = re.sub(r"\s+", " ", new_instruction).strip().lower()
                existing_key = (product, norm)
                already_exists = any(
                    re.sub(r"\s+", " ", r.instruction).strip().lower() == norm
                    and r.product == product
                    for r in self.records
                )
                if already_exists:
                    continue

                self.records.append(SFTRecord(
                    instruction=new_instruction,
                    response=src.response,
                    system_prompt=src.system_prompt,
                    product=product,
                    language=src.language,
                    source_file=src.source_file,
                    source_page=src.source_page,
                    item_type=src.item_type,
                ))
                aug_count += 1
                generated += 1

        return generated

    @staticmethod
    def _extract_name_from_instruction(instruction: str) -> str:
        """질문에서 기술 용어(name) 추출"""
        # 에러코드 패턴
        err = re.search(r"(-?\d{3,5})\s*\(([A-Z_]+)\)", instruction)
        if err:
            return f"{err.group(1)} ({err.group(2)})"

        # 영문 기술 용어
        eng = re.search(
            r"([A-Za-z][A-Za-z0-9_.-]+(?:\s+[A-Za-z][A-Za-z0-9_.-]+){0,2})",
            instruction,
        )
        if eng:
            name = eng.group(1).strip()
            if len(name) >= 3 and name.lower() not in SKIP_WORDS:
                return name

        # CJK 용어
        cjk = re.search(
            r"([\u3040-\u9FFF\uAC00-\uD7A3]{2,}(?:\s*[\u3040-\u9FFF\uAC00-\uD7A3]+){0,3})",
            instruction,
        )
        if cjk:
            return cjk.group(1).strip()

        return ""

    def _detect_manual_type(self, filename: str) -> str:
        """파일명에서 매뉴얼 유형 판별"""
        for pattern, mtype in MANUAL_TYPE_MAP.items():
            if pattern in filename:
                return mtype
        return "concept"

    @staticmethod
    def _is_install_junk(title: str, content: str) -> bool:
        """Installation Guide 저품질 콘텐츠 감지

        설치 로그, 진행바, 라이센스 텍스트, 인스톨러 프롬프트 등
        학습 데이터로 부적합한 콘텐츠를 필터링합니다.
        """
        combined = f"{title}\n{content}"

        # 정크 패턴 매칭 (1개만 매칭이라도 Installation PDF면 제거)
        junk_hits = sum(1 for p in INSTALL_JUNK_PATTERNS if p.search(combined))
        if junk_hits >= 1:
            return True

        # 영어 설치 프롬프트 비율이 높으면 제거 (인스톨러 로그)
        ascii_lines = sum(1 for line in content.split("\n")
                         if line.strip() and re.match(r"^[a-zA-Z0-9_\-=\[\]|./: <>(){}]+$", line.strip()))
        total_lines = max(1, sum(1 for line in content.split("\n") if line.strip()))
        if total_lines >= 3 and ascii_lines / total_lines > 0.7:
            return True

        return False

    @staticmethod
    def _is_installation_pdf(filename: str) -> bool:
        """Installation Guide PDF인지 확인"""
        return "Installation" in filename or "Install" in filename

    @staticmethod
    def _is_low_quality_response(response: str) -> bool:
        """응답 품질이 낮은 레코드 감지

        목차 잔여, 페이지 번호 잔여, 의미 없는 짧은 텍스트,
        PARSE_ONLY 스텁, 설치 로그 잔여 등을 필터링.
        """
        if not response:
            return True

        # 목차/인덱스 페이지 잔여 (索引...N, 目次)
        if re.search(r"索引\.{3,}", response):
            return True
        if re.search(r"目次\.{3,}", response):
            return True

        # PARSE_ONLY: "構文解析のみサポート" 등 실질적 내용이 없는 스텁 응답
        parse_only_markers = [
            "構文解析のみサポート",       # 구문해석만 지원
            "構文解析のみ",               # 구문해석만
            "解析のみサポート",           # 해석만 지원
            "未サポート",                 # 미지원
            "サポートされていません",      # 지원되지 않음
            "サポート対象外",             # 지원 대상 외
        ]
        resp_lower = response.strip()
        for marker in parse_only_markers:
            if marker in resp_lower:
                # 마커가 응답의 대부분을 차지하면 저품질
                marker_ratio = len(marker) / max(len(resp_lower), 1)
                if marker_ratio > 0.2 or len(resp_lower) < 100:
                    return True

        # INSTALL_LOG: 설치 로그/설치 프로세스 잔여 콘텐츠
        install_log_patterns = [
            re.compile(r"PRESS\s+<ENTER>\s+TO\s+CONTINUE", re.IGNORECASE),
            re.compile(r"->?\s*\d+\s*-\s*(?:Install|Next|Accept|Quit)", re.IGNORECASE),
            re.compile(r"(?:Default|Current)\s+(?:Install|Target)\s+(?:Folder|Directory)", re.IGNORECASE),
            re.compile(r"(?:DO YOU ACCEPT|ACCEPT THE TERMS)", re.IGNORECASE),
            re.compile(r"\[={5,}\|"),          # [=======|=======] 진행바
            re.compile(r"Configuring the (?:installer|environment)", re.IGNORECASE),
            re.compile(r"InstallAnywhere", re.IGNORECASE),
        ]
        install_hits = sum(1 for p in install_log_patterns if p.search(response))
        if install_hits >= 1:
            return True

        # "iii" "iv" "v" 같은 로마숫자 페이지 번호만 남은 경우
        cleaned = re.sub(r"\s+", " ", response).strip()
        if re.match(r"^.{0,30}\s*[ivxIVX]{1,4}\s*$", cleaned):
            return True

        # 점선이 과도한 콘텐츠 (목차 잔여)
        if response.count("...") >= 3 or response.count("…") >= 3:
            dot_ratio = (response.count(".") + response.count("…")) / max(len(response), 1)
            if dot_ratio > 0.15:
                return True

        return False

    def _clean_text(self, text: str) -> str:
        """텍스트 클리닝"""
        text = FOOTER_PATTERN.sub("", text)
        text = re.sub(r"[ \t]+", " ", text)
        lines = [line.strip() for line in text.strip().split("\n")]
        lines = [line for line in lines if line]
        return " ".join(lines)

    def _clean_response(self, text: str) -> str:
        """응답 텍스트에서 노이즈 제거 (페이지 헤더/푸터/번호)"""
        if not text:
            return ""
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            # 페이지 번호만 있는 줄 제거
            if re.match(r"^\d{1,4}\s*$", stripped):
                continue
            # "第N章 Title  N" 형태의 푸터 제거
            if re.match(r"^第\d+章\s+.+\d+\s*$", stripped):
                continue
            # "N  OpenFrame ..." 형태의 헤더 제거
            if re.match(r"^\d+\s+(OpenFrame|Tibero|Tmax|JEUS|WebtoB)\s+", stripped):
                continue
            # 빈 줄 과다 방지
            if not stripped and cleaned and not cleaned[-1].strip():
                continue
            cleaned.append(line)
        result = "\n".join(cleaned).strip()
        # 최대 길이 제한
        return result[:800] if len(result) > 800 else result

    def _translate_phrase(self, text: str, target: str) -> str:
        """룰 기반 문구 번역 (기술 용어 유지)"""
        if not text:
            return ""
        result = text
        for ja_phrase, translations in RESPONSE_PHRASES.items():
            if ja_phrase in result and target in translations:
                result = result.replace(ja_phrase, translations[target])
        return result

    def _get_system_prompt(self, product: str, lang: str) -> str:
        """제품+언어 시스템 프롬프트"""
        prompts = PRODUCT_SYSTEM_PROMPTS.get(product, DEFAULT_SYSTEM_PROMPT)
        return prompts.get(lang, prompts.get("ja", DEFAULT_SYSTEM_PROMPT["ja"]))

    def _stratified_split(
        self, records: List[SFTRecord], ratio: float = 0.8
    ) -> Tuple[List[SFTRecord], List[SFTRecord]]:
        """제품별 stratified Train/Eval 분할"""
        by_product = defaultdict(list)
        for r in records:
            by_product[r.product].append(r)

        train, eval_ = [], []
        for product, items in by_product.items():
            random.shuffle(items)
            split = int(len(items) * ratio)
            train.extend(items[:split])
            eval_.extend(items[split:])

        random.shuffle(train)
        random.shuffle(eval_)
        return train, eval_

    def _write_jsonl(self, records: List[SFTRecord], path: Path):
        """JSONL 출력"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r.to_jsonl(), ensure_ascii=False) + "\n")
        logger.info(f"  출력: {path} ({len(records)}건)")

    def _write_by_product(
        self, train: List[SFTRecord], eval_: List[SFTRecord], sft_dir: Path
    ):
        """제품별 분할 출력"""
        train_by = defaultdict(list)
        eval_by = defaultdict(list)
        for r in train:
            train_by[r.product].append(r)
        for r in eval_:
            eval_by[r.product].append(r)

        all_products = set(list(train_by.keys()) + list(eval_by.keys()))
        for product in sorted(all_products):
            product_dir = sft_dir / product
            product_dir.mkdir(parents=True, exist_ok=True)
            if train_by[product]:
                self._write_jsonl(train_by[product], product_dir / "train.jsonl")
            if eval_by[product]:
                self._write_jsonl(eval_by[product], product_dir / "eval.jsonl")
