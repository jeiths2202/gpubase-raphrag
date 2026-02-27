"""통합 LoRA용 CPT 코퍼스 생성기

4가지 소스에서 제품 간 관계 텍스트를 추출:
1. 아키텍처 문서: 각 제품 Base-Guide의 "システム構成" 장
2. 설치 가이드: "Prerequisites" / "前提条件" 섹션
3. 마이그레이션 가이드: HOST→OpenFrame 매핑 테이블
4. 운영 가이드: 起動/停止 순서 설명

기존 CPTChunk 모델을 product="unified"로 재사용합니다.
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Set

from ..config import (
    DIRECTORY_TO_PRODUCT,
    DIRECTORY_LANGUAGE,
    COMPONENT_SPLIT_DIRS,
    PDF_COMPONENT_TO_PRODUCT,
    OTHER_PRODUCT_KEYWORDS,
    PRODUCT_DISPLAY_NAMES,
)
from ..models.training import CPTChunk, DataLanguage

logger = logging.getLogger(__name__)

# PyMuPDF import
try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None
        logger.warning("PyMuPDF not available - unified CPT generation will fail")

# 관계 관련 섹션 감지 키워드
RELATION_SECTION_KEYWORDS = [
    # 일본어
    "システム構成", "前提条件", "連携", "起動順序", "停止順序",
    "マイグレーション", "依存", "互換性", "アーキテクチャ",
    "インストール", "前提ソフトウェア", "関連製品", "構成例",
    # 한국어
    "시스템 구성", "전제조건", "연동", "기동순서", "정지순서",
    "마이그레이션", "의존", "호환성", "아키텍처",
    "설치", "전제 소프트웨어", "관련 제품", "구성 예",
    # 영어
    "System Configuration", "Prerequisites", "Integration",
    "Boot Sequence", "Shutdown", "Migration", "Dependency",
    "Compatibility", "Architecture", "Installation",
    "Related Products", "Configuration Example",
]

# TOC/헤더/푸터 제거 패턴 (기존 CPT와 동일)
TOC_LINE_RE = re.compile(r'^.*?\.{4,}\s*\d+\s*$', re.MULTILINE)
FOOTER_RE = re.compile(
    r'^(?:Copyright|©|Tmax|TmaxSoft|OpenFrame).*$',
    re.MULTILINE | re.IGNORECASE,
)
PAGE_NUM_RE = re.compile(r'^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$', re.MULTILINE)

# 섹션 분할 패턴
SECTION_HEADING_RE = re.compile(
    r'\n(?=第?\d+[章節]|[A-Z]\.\d+|\d+\.\d+\.)'
)

# v2: 핵심 가이드 targeted extraction (완화된 필터링으로 전문 추출)
# 비교/마이그레이션/화면정의 등 통합 LoRA에 특히 중요한 PDF 리스트
TARGETED_GUIDES = [
    # BMS / MFS 화면정의 가이드
    "MVS_Openframe 7.1*/OF_OSC_Mapping-Support*.pdf",
    "MVS_Openframe 7.1*/OF_OSI_MFS-Reference*.pdf",
    # 마이그레이션 가이드 (3 플랫폼)
    "MVS_Openframe 7.1*/OF_*Migration*.pdf",
    "MSP_Openframe 7.3*/OF_*Migration*.pdf",
    "XSP_Openframe 7.3*/OF_*Migration*.pdf",
    # RDBII / AIM DB 가이드
    "XSP_Openframe 7.3*/OF_*RDBII*.pdf",
    "MSP_Openframe 7.3*/OF_AIM_Developer*.pdf",
    "XSP_Openframe 7.3*/OF_AIM_Developer*.pdf",
    "MSP_Openframe 7.3*/OF_AIM_Administrator*.pdf",
    "XSP_Openframe 7.3*/OF_AIM_Administrator*.pdf",
    # CTG 가이드
    "MVS_Openframe 7.1*/OF_OSC_CTG*.pdf",
    # VOS3 가이드 (전체)
    "VOS3_Openframe 2.0*/*.pdf",
    # OFMiner / OFStudio 가이드
    "OFMiner*/*.pdf",
    "OFStudio*/*.pdf",
    # OFPli 가이드
    "OFPli*/*.pdf",
    # ProSync / ProTrieve 가이드
    "ProSync*/*.pdf",
    "ProTrieve*/*.pdf",
    # JCL Reference / DB 가이드 (플랫폼별 차이 비교)
    "MVS_Openframe 7.1*/OF_*JCL*.pdf",
    "MSP_Openframe 7.3*/OF_*JCL*.pdf",
    "XSP_Openframe 7.3*/OF_*JCL*.pdf",
    "MVS_Openframe 7.1*/OF_*HiDB*.pdf",
    "MSP_Openframe 7.3*/OF_*NDB*.pdf",
]


class UnifiedCPTGenerator:
    """통합 LoRA용 CPT 코퍼스 생성기

    PDF 매뉴얼에서 제품 간 관계가 기술된 섹션만 선택적으로 추출하여
    통합 LoRA의 도메인 지식 주입에 사용합니다.
    기존 CPTGenerator와 달리 전체 텍스트가 아닌 관계 섹션만 추출합니다.
    """

    MAX_CHUNK_TOKENS = 4096
    SEPARATOR = "<|endoftext|>"
    CHARS_PER_TOKEN_JA = 1.5
    CHARS_PER_TOKEN_EN = 4.0
    MIN_CHUNK_TOKENS = 50
    # 다른 제품 키워드가 최소 이 수만큼 있어야 관계 섹션으로 인정
    MIN_OTHER_PRODUCT_MENTIONS = 2

    def __init__(self, manuals_dir: Path, output_dir: Path):
        self.manuals_dir = manuals_dir
        self.output_dir = output_dir
        # 제품명 → product_id 역매핑 (대소문자 무시)
        self._product_name_lower = {
            name.lower(): pid for name, pid in OTHER_PRODUCT_KEYWORDS.items()
        }
        self._display_name_lower = {
            name.lower(): pid for pid, name in PRODUCT_DISPLAY_NAMES.items()
        }

    def generate_all(self, languages: List[str] = None) -> List[CPTChunk]:
        """통합 CPT 코퍼스 생성

        Args:
            languages: 대상 언어 목록 (기본: ["ja", "ko", "en"])

        Returns:
            CPTChunk 리스트 (product="unified")
        """
        if languages is None:
            languages = ["ja", "ko", "en"]

        logger.info("=== 통합 CPT 코퍼스 생성 시작 ===")

        all_chunks: List[CPTChunk] = []

        for lang in languages:
            chunks = self._collect_relation_chunks(lang)
            if not chunks:
                logger.info(f"[UnifiedCPT] {lang}: 관계 섹션 없음, 건너뜀")
                continue

            # 중복 제거
            before = len(chunks)
            chunks = self._deduplicate(chunks)
            if before != len(chunks):
                logger.info(
                    f"[UnifiedCPT] {lang}: 중복 제거 {before - len(chunks)}건 "
                    f"({before} → {len(chunks)})"
                )

            all_chunks.extend(chunks)
            logger.info(
                f"[UnifiedCPT] {lang}: {len(chunks)}개 관계 섹션 청크 추출"
            )

        # v2: Targeted Guides 추출 (완화된 필터링)
        targeted_chunks = self._collect_targeted_chunks()
        if targeted_chunks:
            before = len(targeted_chunks)
            targeted_chunks = self._deduplicate(targeted_chunks)
            logger.info(
                f"[UnifiedCPT] Targeted guides: {len(targeted_chunks)}개 청크 "
                f"(중복제거: {before} → {len(targeted_chunks)})"
            )
            # 기존 청크와 통합 후 최종 중복 제거
            all_chunks.extend(targeted_chunks)
            all_chunks = self._deduplicate(all_chunks)

        # 코퍼스 파일 작성
        if all_chunks:
            self._write_corpus(all_chunks)

        logger.info(f"통합 CPT 총: {len(all_chunks)}개 청크")
        return all_chunks

    def _collect_relation_chunks(self, lang: str) -> List[CPTChunk]:
        """특정 언어의 모든 PDF에서 관계 섹션 추출"""
        chunks: List[CPTChunk] = []

        for product_dir in sorted(self.manuals_dir.iterdir()):
            if not product_dir.is_dir():
                continue

            dir_lang = DIRECTORY_LANGUAGE.get(product_dir.name, "ja")
            if dir_lang != lang:
                continue

            dir_product_id = DIRECTORY_TO_PRODUCT.get(
                product_dir.name, "unknown_product"
            )
            use_component_split = product_dir.name in COMPONENT_SPLIT_DIRS

            pdf_files = sorted(product_dir.glob("*.pdf"))
            if not pdf_files:
                continue

            for pdf_path in pdf_files:
                try:
                    source_product = self._resolve_product_id(
                        pdf_path.name, dir_product_id, use_component_split
                    )
                    relation_chunks = self._extract_relation_sections(
                        pdf_path, source_product, DataLanguage(lang)
                    )
                    chunks.extend(relation_chunks)
                except Exception as e:
                    logger.warning(f"  Error processing {pdf_path.name}: {e}")

        return chunks

    def _extract_relation_sections(
        self,
        pdf_path: Path,
        source_product: str,
        language: DataLanguage,
    ) -> List[CPTChunk]:
        """PDF에서 관계 관련 섹션만 선택적으로 추출

        1. TOC(목차)에서 관계 키워드가 포함된 섹션 페이지 범위 파악
        2. 해당 페이지 범위의 텍스트 추출
        3. 다른 제품 언급이 2회 이상인 섹션만 유지
        """
        if pymupdf is None:
            raise RuntimeError("PyMuPDF is required for unified CPT generation")

        doc = pymupdf.open(str(pdf_path))
        chunks: List[CPTChunk] = []

        try:
            # TOC 기반 섹션 추출 시도
            toc = doc.get_toc()
            if toc and len(toc) >= 3:
                chunks = self._extract_via_toc(
                    doc, toc, pdf_path.name, source_product, language
                )

            # TOC가 없거나 결과가 없으면 전체 텍스트에서 키워드 기반 추출
            if not chunks:
                chunks = self._extract_via_keyword_scan(
                    doc, pdf_path.name, source_product, language
                )
        finally:
            doc.close()

        return chunks

    def _extract_via_toc(
        self,
        doc,
        toc: list,
        source_file: str,
        source_product: str,
        language: DataLanguage,
    ) -> List[CPTChunk]:
        """TOC에서 관계 키워드 섹션의 페이지 범위를 구하고 텍스트 추출"""
        chunks: List[CPTChunk] = []
        total_pages = len(doc)

        for i, entry in enumerate(toc):
            level, title, page = entry[0], entry[1], entry[2]

            # 관계 키워드가 제목에 포함되어 있는지 확인
            if not self._is_relation_title(title):
                continue

            # 다음 동일 레벨 섹션까지의 페이지 범위 결정
            end_page = total_pages
            for j in range(i + 1, len(toc)):
                if toc[j][0] <= level:
                    end_page = toc[j][2]
                    break

            # 페이지 범위에서 텍스트 추출 (0-indexed)
            start_idx = max(0, page - 1)
            end_idx = min(total_pages, end_page)

            section_text = ""
            for p in range(start_idx, end_idx):
                page_text = doc[p].get_text()
                if page_text:
                    section_text += page_text + "\n"

            section_text = self._clean_text(section_text)

            if not section_text or len(section_text.strip()) < 100:
                continue

            # 다른 제품 언급 확인
            mentioned = self._count_other_product_mentions(
                section_text, source_product
            )
            if mentioned < self.MIN_OTHER_PRODUCT_MENTIONS:
                continue

            # 청크 분할
            section_chunks = self._chunk_text(
                section_text, source_file, language
            )
            chunks.extend(section_chunks)

        return chunks

    def _extract_via_keyword_scan(
        self,
        doc,
        source_file: str,
        source_product: str,
        language: DataLanguage,
    ) -> List[CPTChunk]:
        """TOC 없을 때: 전체 텍스트에서 관계 키워드 주변 단락을 추출"""
        chunks: List[CPTChunk] = []

        # 전체 텍스트 추출
        full_text = ""
        for page_num in range(len(doc)):
            page_text = doc[page_num].get_text()
            if page_text:
                full_text += page_text + "\n"

        full_text = self._clean_text(full_text)
        if not full_text or len(full_text) < 200:
            return chunks

        # 섹션 경계로 분할
        sections = SECTION_HEADING_RE.split(full_text)

        for section in sections:
            section = section.strip()
            if not section or len(section) < 100:
                continue

            # 관계 키워드가 포함된 섹션만
            if not self._contains_relation_keywords(section):
                continue

            # 다른 제품 언급 확인
            mentioned = self._count_other_product_mentions(
                section, source_product
            )
            if mentioned < self.MIN_OTHER_PRODUCT_MENTIONS:
                continue

            section_chunks = self._chunk_text(section, source_file, language)
            chunks.extend(section_chunks)

        return chunks

    def _is_relation_title(self, title: str) -> bool:
        """TOC 제목이 관계 관련 키워드를 포함하는지 확인"""
        title_lower = title.lower()
        for keyword in RELATION_SECTION_KEYWORDS:
            if keyword.lower() in title_lower:
                return True
        return False

    def _contains_relation_keywords(self, text: str) -> bool:
        """텍스트에 관계 키워드가 포함되어 있는지 확인"""
        text_lower = text.lower()
        count = 0
        for keyword in RELATION_SECTION_KEYWORDS:
            if keyword.lower() in text_lower:
                count += 1
                if count >= 2:
                    return True
        return False

    def _count_other_product_mentions(
        self, text: str, source_product: str
    ) -> int:
        """텍스트에서 다른 제품 언급 횟수 계산"""
        mentioned_products: Set[str] = set()
        text_lower = text.lower()

        # OTHER_PRODUCT_KEYWORDS로 확인
        for keyword, product_id in OTHER_PRODUCT_KEYWORDS.items():
            if product_id == source_product:
                continue
            if keyword.lower() in text_lower:
                mentioned_products.add(product_id)

        # PRODUCT_DISPLAY_NAMES로 확인
        for product_id, display_name in PRODUCT_DISPLAY_NAMES.items():
            if product_id == source_product:
                continue
            if display_name.lower() in text_lower:
                mentioned_products.add(product_id)

        return len(mentioned_products)

    def _clean_text(self, text: str) -> str:
        """텍스트 클리닝 (TOC, 헤더/푸터, 페이지번호 제거)"""
        text = TOC_LINE_RE.sub("", text)
        text = FOOTER_RE.sub("", text)
        text = PAGE_NUM_RE.sub("", text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _chunk_text(
        self,
        text: str,
        source_file: str,
        language: DataLanguage,
    ) -> List[CPTChunk]:
        """텍스트를 MAX_CHUNK_TOKENS 이하의 청크로 분할"""
        if not text:
            return []

        paragraphs = re.split(r'\n\n+', text)
        chunks: List[CPTChunk] = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            combined = current + "\n\n" + para if current else para
            combined_tokens = self._count_tokens(combined, language)

            if combined_tokens > self.MAX_CHUNK_TOKENS:
                if current.strip():
                    token_count = self._count_tokens(current, language)
                    if token_count >= self.MIN_CHUNK_TOKENS:
                        chunks.append(CPTChunk(
                            text=current.strip(),
                            product="unified",
                            language=language,
                            source_file=source_file,
                            token_count=token_count,
                        ))
                current = para
            else:
                current = combined

        # 마지막 잔여분
        if current.strip():
            token_count = self._count_tokens(current, language)
            if token_count >= self.MIN_CHUNK_TOKENS:
                chunks.append(CPTChunk(
                    text=current.strip(),
                    product="unified",
                    language=language,
                    source_file=source_file,
                    token_count=token_count,
                ))

        return chunks

    def _count_tokens(self, text: str, language: DataLanguage = None) -> int:
        """토큰 수 근사 추정"""
        if not text:
            return 0
        if language and language.value == "ja":
            return int(len(text) / self.CHARS_PER_TOKEN_JA)
        elif language and language.value == "en":
            return int(len(text) / self.CHARS_PER_TOKEN_EN)
        return int(len(text) / 2.5)

    @staticmethod
    def _deduplicate(chunks: List[CPTChunk]) -> List[CPTChunk]:
        """동일 텍스트 청크 제거 (첫 200자 기준)"""
        seen = set()
        unique = []
        for chunk in chunks:
            norm = re.sub(r"\s+", " ", chunk.text[:200]).strip().lower()
            key = norm
            if key in seen:
                continue
            seen.add(key)
            unique.append(chunk)
        return unique

    def _collect_targeted_chunks(self) -> List[CPTChunk]:
        """TARGETED_GUIDES의 PDF에서 완화된 필터링으로 전문 추출

        일반 추출과 달리 MIN_OTHER_PRODUCT_MENTIONS 조건을 완화하여
        BMS/MFS, Migration, CTG 등 핵심 가이드의 내용을 더 많이 포함.
        """
        chunks: List[CPTChunk] = []

        if pymupdf is None:
            logger.warning("PyMuPDF not available - targeted guide extraction skipped")
            return chunks

        for pattern in TARGETED_GUIDES:
            matched_files = list(self.manuals_dir.glob(pattern))
            if not matched_files:
                logger.debug(f"  Targeted guide not found: {pattern}")
                continue

            for pdf_path in sorted(matched_files):
                try:
                    # 디렉토리에서 언어/제품 결정
                    dir_name = pdf_path.parent.name
                    dir_lang = DIRECTORY_LANGUAGE.get(dir_name, "ja")
                    dir_product_id = DIRECTORY_TO_PRODUCT.get(dir_name, "unknown_product")
                    use_component_split = dir_name in COMPONENT_SPLIT_DIRS

                    source_product = self._resolve_product_id(
                        pdf_path.name, dir_product_id, use_component_split
                    )
                    language = DataLanguage(dir_lang)

                    # 완화된 추출: 관계 키워드 없어도 전체 섹션 추출
                    doc = pymupdf.open(str(pdf_path))
                    try:
                        full_text = ""
                        for page_num in range(len(doc)):
                            page_text = doc[page_num].get_text()
                            if page_text:
                                full_text += page_text + "\n"

                        full_text = self._clean_text(full_text)
                        if full_text and len(full_text) >= 200:
                            # 섹션 분할 후 최소 길이만 확인 (관계 키워드 필터 완화)
                            sections = SECTION_HEADING_RE.split(full_text)
                            for section in sections:
                                section = section.strip()
                                if len(section) < 100:
                                    continue
                                section_chunks = self._chunk_text(
                                    section, pdf_path.name, language
                                )
                                chunks.extend(section_chunks)
                    finally:
                        doc.close()

                except Exception as e:
                    logger.warning(f"  Targeted guide error: {pdf_path.name}: {e}")

        logger.info(f"[UnifiedCPT] Targeted guides: {len(TARGETED_GUIDES)} patterns → {len(chunks)} chunks")
        return chunks

    def _write_corpus(self, chunks: List[CPTChunk]) -> None:
        """통합 CPT 코퍼스 파일 작성"""
        cpt_dir = Path(self.output_dir) / "cpt_unified"
        cpt_dir.mkdir(parents=True, exist_ok=True)

        # 언어별로 파일 분리
        by_lang: dict[str, List[CPTChunk]] = {}
        for chunk in chunks:
            lang = chunk.language.value
            by_lang.setdefault(lang, []).append(chunk)

        for lang, lang_chunks in by_lang.items():
            corpus_path = cpt_dir / f"corpus_unified_{lang}.txt"
            total_tokens = 0

            with open(corpus_path, "w", encoding="utf-8") as f:
                for i, chunk in enumerate(lang_chunks):
                    if i > 0:
                        f.write(f"\n{self.SEPARATOR}\n")
                    f.write(chunk.text)
                    total_tokens += chunk.token_count

            size_mb = corpus_path.stat().st_size / 1024 / 1024
            logger.info(
                f"[UnifiedCPT] {lang}: {len(lang_chunks)}개 청크, "
                f"~{total_tokens:,} tokens → {corpus_path.name} "
                f"({size_mb:.1f} MB)"
            )

    @staticmethod
    def _resolve_product_id(
        pdf_filename: str, dir_product_id: str, use_component_split: bool
    ) -> str:
        """PDF 파일명에서 product_id 결정 (기존 CPTGenerator와 동일 로직)"""
        if not use_component_split:
            return dir_product_id

        stem = pdf_filename.replace(".pdf", "")

        if stem.startswith("OF_"):
            parts = stem.split("_")
            if len(parts) >= 2:
                component = parts[1]
                mapped = PDF_COMPONENT_TO_PRODUCT.get(component)
                if mapped:
                    return mapped

        if stem.startswith("OFManager"):
            return "ofmanager_v2"

        return dir_product_id
