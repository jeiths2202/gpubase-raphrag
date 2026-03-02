"""CPT (Continued Pre-Training) Plain Text 학습 데이터 생성기

전체 PDF 매뉴얼에서 원문 텍스트를 추출하여
4096 토큰 단위의 Plain Text 청크로 분할합니다.

출력: uploads/training/v10/cpt/corpus_{lang}.txt
"""

import re
import logging
from pathlib import Path
from typing import List, Dict

from ..models.training import CPTChunk, TrainingStats, DataLanguage
from ..config import (
    config, DIRECTORY_TO_PRODUCT, DIRECTORY_LANGUAGE,
    PDF_COMPONENT_TO_PRODUCT, COMPONENT_SPLIT_DIRS,
)

logger = logging.getLogger(__name__)

# PyMuPDF import
try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None
        logger.warning("PyMuPDF not available - CPT generation will fail")

# TOC/헤더/푸터 제거 패턴
TOC_LINE_RE = re.compile(
    r'^.*?\.{4,}\s*\d+\s*$', re.MULTILINE
)
FOOTER_RE = re.compile(
    r'^(?:Copyright|©|Tmax|TmaxSoft|OpenFrame).*$', re.MULTILINE | re.IGNORECASE
)
PAGE_NUM_RE = re.compile(
    r'^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$', re.MULTILINE
)
# 日本語セクション見出し
SECTION_SPLIT_RE = re.compile(
    r'\n(?=第?\d+[章節]|[A-Z]\.\d+|\d+\.\d+\.)'
)
# 短い行の連続(目次、索引)
SHORT_LINE_BLOCK_RE = re.compile(
    r'(?:^.{1,20}\n){5,}', re.MULTILINE
)


class CPTGenerator:
    """CPT Plain Text 학습 데이터 생成

    PDF 매뉴얼에서 원문 텍스트를 추출하고,
    <|endoftext|> 토큰으로 구분된 4096 토큰 단위의 코퍼스를 생성합니다.
    """

    MAX_CHUNK_TOKENS = 4096
    SEPARATOR = "<|endoftext|>"
    # 대략적 토큰 추정: 일본어 1문자≈1토큰, 영문 1단어≈1토큰
    # 정확한 토큰화 없이 근사치 사용 (학습 시 tokenizer가 정확히 분할)
    CHARS_PER_TOKEN_JA = 1.5   # 일본어: ~1.5 chars/token
    CHARS_PER_TOKEN_EN = 4.0   # 영어/한국어: ~4 chars/token

    def __init__(self, manuals_dir: Path, output_dir: Path):
        self.manuals_dir = manuals_dir
        self.output_dir = output_dir

    def generate_all(self, languages: List[str] = None) -> TrainingStats:
        """전체 CPT 코퍼스 생성

        Args:
            languages: 생성할 언어 목록 (기본: ["ja", "ko", "en"])

        Returns:
            TrainingStats with by_language, by_product counts
        """
        if languages is None:
            languages = ["ja", "ko", "en"]

        stats = TrainingStats()
        stats.by_format["cpt"] = 0

        for lang in languages:
            chunks = self._collect_chunks_for_language(lang)

            if not chunks:
                logger.info(f"[CPT] {lang}: No PDFs found, skipping")
                continue

            # 중복 청크 제거 (MVS/MSP/XSP 간 동일 콘텐츠)
            before_dedup = len(chunks)
            chunks = self._deduplicate_chunks(chunks)
            dedup_removed = before_dedup - len(chunks)
            if dedup_removed:
                logger.info(f"[CPT] {lang}: 중복 청크 제거 {dedup_removed}건 ({before_dedup} → {len(chunks)})")

            # 코퍼스 파일 작성
            cpt_dir = Path(self.output_dir) / "cpt"
            cpt_dir.mkdir(parents=True, exist_ok=True)
            corpus_path = cpt_dir / f"corpus_{lang}.txt"

            total_tokens = self._write_corpus(chunks, corpus_path)

            stats.by_language[lang] = len(chunks)
            stats.by_format["cpt"] += len(chunks)
            stats.total_records += len(chunks)

            # 제품별 집계
            for chunk in chunks:
                product = chunk.product
                stats.by_product[product] = stats.by_product.get(product, 0) + 1

            logger.info(
                f"[CPT] {lang}: {len(chunks)} chunks, "
                f"~{total_tokens:,} tokens → {corpus_path}"
            )

        return stats

    def _deduplicate_component_pdfs(self) -> set:
        """COMPONENT_SPLIT_DIRS 간 중복 PDF 제거 (SFT와 동일 로직)

        MVS/MSP/XSP에서 같은 컴포넌트+가이드타입 PDF가 있으면
        가장 큰 파일만 사용합니다.
        """
        from collections import defaultdict
        component_pdfs = defaultdict(list)

        for dir_name in COMPONENT_SPLIT_DIRS:
            product_dir = self.manuals_dir / dir_name
            if not product_dir.is_dir():
                continue
            for pdf_path in product_dir.glob("*.pdf"):
                stem = pdf_path.stem
                if stem.startswith("OF_"):
                    parts = stem.split("_")
                    if len(parts) >= 4:
                        component = parts[1]
                        guide_parts = []
                        for p in parts[3:]:
                            if p.startswith("v") and re.match(r"v\d", p):
                                break
                            guide_parts.append(p)
                        guide_type = "-".join(guide_parts) if guide_parts else "unknown"
                        key = (component, guide_type)
                        component_pdfs[key].append((pdf_path, pdf_path.stat().st_size))
                elif stem.startswith("OFManager"):
                    parts = stem.split("_")
                    guide_parts = []
                    for p in parts[3:]:
                        if p.startswith("v") and re.match(r"v\d", p):
                            break
                        guide_parts.append(p)
                    guide_type = "-".join(guide_parts) if guide_parts else "unknown"
                    key = ("Manager", guide_type)
                    component_pdfs[key].append((pdf_path, pdf_path.stat().st_size))

        skip_set = set()
        for key, pdf_list in component_pdfs.items():
            if len(pdf_list) <= 1:
                continue
            pdf_list.sort(key=lambda x: x[1], reverse=True)
            for pdf_path, size in pdf_list[1:]:
                skip_set.add(str(pdf_path))
        return skip_set

    def _collect_chunks_for_language(self, lang: str) -> List[CPTChunk]:
        """특정 언어의 모든 PDF에서 청크 수집"""
        chunks = []

        # PDF 레벨 중복 제거 (MVS/MSP/XSP 간)
        dedup_skip = self._deduplicate_component_pdfs()
        if dedup_skip:
            logger.info(f"[CPT] {lang}: PDF 중복 제거 {len(dedup_skip)}개 건너뜀")

        for product_dir in sorted(self.manuals_dir.iterdir()):
            if not product_dir.is_dir():
                continue

            # 디렉토리 언어 판별
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

            logger.debug(
                f"[CPT] Processing {product_dir.name} "
                f"({len(pdf_files)} PDFs, product={dir_product_id})"
                f"{', component_split=ON' if use_component_split else ''}"
            )

            for pdf_path in pdf_files:
                # PDF 레벨 중복 제거
                if str(pdf_path) in dedup_skip:
                    logger.debug(f"  [Dedup] Skip CPT: {pdf_path.name}")
                    continue
                try:
                    # I-03: PDF 파일명에서 컴포넌트별 product_id 결정
                    product_id = self._resolve_product_id(
                        pdf_path.name, dir_product_id, use_component_split
                    )

                    text = self._extract_text(pdf_path)
                    if not text or len(text.strip()) < 100:
                        logger.debug(f"  Skip (too short): {pdf_path.name}")
                        continue

                    pdf_chunks = self._chunk_text(
                        text, pdf_path.name, product_id, DataLanguage(lang)
                    )
                    chunks.extend(pdf_chunks)

                except Exception as e:
                    logger.warning(f"  Error processing {pdf_path.name}: {e}")
                    continue

        return chunks

    @staticmethod
    def _deduplicate_chunks(chunks: List[CPTChunk]) -> List[CPTChunk]:
        """동일/유사 텍스트 청크 제거

        MVS/MSP/XSP 디렉토리에 같은 컴포넌트의 PDF가 중복 존재할 때
        추출된 텍스트가 거의 동일한 경우를 제거합니다.
        첫 200자 + 제품으로 키를 만들어 빠른 dedup 수행.
        """
        seen = set()
        unique = []
        for chunk in chunks:
            # 텍스트 첫 200자를 정규화하여 키 생성
            norm_text = re.sub(r"\s+", " ", chunk.text[:200]).strip().lower()
            key = (chunk.product, norm_text)
            if key in seen:
                continue
            seen.add(key)
            unique.append(chunk)
        return unique

    @staticmethod
    def _resolve_product_id(
        pdf_filename: str, dir_product_id: str, use_component_split: bool
    ) -> str:
        """PDF 파일명에서 컴포넌트를 추출하여 product_id를 결정 (I-03)

        SFTGenerator._resolve_product_id와 동일한 로직.
        MVS/MSP/XSP 디렉토리의 PDF는 "OF_{Component}_..." 패턴으로 제품 분리.
        """
        if not use_component_split:
            return dir_product_id

        stem = pdf_filename.replace(".pdf", "")

        # Pattern 1: "OF_{Component}_..."
        if stem.startswith("OF_"):
            parts = stem.split("_")
            if len(parts) >= 2:
                component = parts[1]
                mapped = PDF_COMPONENT_TO_PRODUCT.get(component)
                if mapped:
                    return mapped

        # Pattern 2: "OFManager_..."
        if stem.startswith("OFManager"):
            return "ofmanager_v2"

        return dir_product_id

    def _extract_text(self, pdf_path: Path) -> str:
        """PyMuPDF로 PDF 전체 텍스트 추출"""
        if pymupdf is None:
            raise RuntimeError("PyMuPDF is required for CPT generation")

        doc = pymupdf.open(str(pdf_path))
        pages_text = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text:
                pages_text.append(text)

        doc.close()
        return "\n".join(pages_text)

    def _clean_text(self, text: str) -> str:
        """텍스트 클리닝 (TOC, 헤더/푸터, 페이지번호 제거)"""
        # TOC 라인 제거 (점선 + 페이지번호)
        text = TOC_LINE_RE.sub("", text)

        # 푸터 (Copyright 등) 제거
        text = FOOTER_RE.sub("", text)

        # 페이지 번호만 있는 줄 제거
        text = PAGE_NUM_RE.sub("", text)

        # 연속 빈 줄 정리
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 선행/후행 공백 제거
        text = text.strip()

        return text

    def _chunk_text(
        self,
        text: str,
        source_file: str,
        product: str,
        language: DataLanguage,
    ) -> List[CPTChunk]:
        """텍스트를 4096 토큰 이하 청크로 분할

        1. TOC/헤더/푸터 제거
        2. 섹션 경계에서 우선 분할
        3. 토큰 수 초과 시 추가 분할
        """
        text = self._clean_text(text)

        if not text:
            return []

        # 섹션 경계에서 분할
        sections = SECTION_SPLIT_RE.split(text)

        chunks = []
        current = ""

        for section in sections:
            section = section.strip()
            if not section:
                continue

            combined_tokens = self._count_tokens(
                current + "\n" + section, language
            )

            if combined_tokens > self.MAX_CHUNK_TOKENS:
                # 현재 누적분 저장
                if current.strip():
                    token_count = self._count_tokens(current, language)
                    if token_count >= 50:  # 너무 짧은 청크 제외
                        chunks.append(CPTChunk(
                            text=current.strip(),
                            product=product,
                            language=language,
                            source_file=source_file,
                            token_count=token_count,
                        ))

                # 섹션이 자체적으로 MAX 초과하면 추가 분할
                if self._count_tokens(section, language) > self.MAX_CHUNK_TOKENS:
                    sub_chunks = self._split_long_section(
                        section, source_file, product, language
                    )
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    current = section
            else:
                if current:
                    current += "\n" + section
                else:
                    current = section

        # 마지막 잔여분
        if current.strip():
            token_count = self._count_tokens(current, language)
            if token_count >= 50:
                chunks.append(CPTChunk(
                    text=current.strip(),
                    product=product,
                    language=language,
                    source_file=source_file,
                    token_count=token_count,
                ))

        return chunks

    def _split_long_section(
        self,
        text: str,
        source_file: str,
        product: str,
        language: DataLanguage,
    ) -> List[CPTChunk]:
        """MAX_CHUNK_TOKENS 초과 섹션을 단락 단위로 추가 분할"""
        paragraphs = re.split(r'\n\n+', text)
        chunks = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            combined_tokens = self._count_tokens(
                current + "\n\n" + para, language
            )

            if combined_tokens > self.MAX_CHUNK_TOKENS:
                if current.strip():
                    token_count = self._count_tokens(current, language)
                    if token_count >= 50:
                        chunks.append(CPTChunk(
                            text=current.strip(),
                            product=product,
                            language=language,
                            source_file=source_file,
                            token_count=token_count,
                        ))
                current = para
            else:
                if current:
                    current += "\n\n" + para
                else:
                    current = para

        if current.strip():
            token_count = self._count_tokens(current, language)
            if token_count >= 50:
                chunks.append(CPTChunk(
                    text=current.strip(),
                    product=product,
                    language=language,
                    source_file=source_file,
                    token_count=token_count,
                ))

        return chunks

    def _count_tokens(self, text: str, language: DataLanguage = None) -> int:
        """토큰 수 근사 추정 (tokenizer 없이)

        일본어: ~1.5 chars/token (CJK 문자가 많음)
        영어/한국어: ~4 chars/token
        """
        if not text:
            return 0

        if language and language.value == "ja":
            ratio = self.CHARS_PER_TOKEN_JA
        elif language and language.value == "en":
            ratio = self.CHARS_PER_TOKEN_EN
        else:
            # 한국어 또는 혼합: 중간값
            ratio = 2.5

        return int(len(text) / ratio)

    def _write_corpus(self, chunks: List[CPTChunk], output_path: Path) -> int:
        """코퍼스 파일 작성

        청크를 <|endoftext|> 토큰으로 구분하여 연결합니다.

        Returns:
            총 토큰 수 (근사)
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        total_tokens = 0

        with open(output_path, "w", encoding="utf-8") as f:
            for i, chunk in enumerate(chunks):
                if i > 0:
                    f.write(f"\n{self.SEPARATOR}\n")
                f.write(chunk.text)
                total_tokens += chunk.token_count

        logger.info(
            f"  Written {len(chunks)} chunks to {output_path.name} "
            f"(~{total_tokens:,} tokens, "
            f"{output_path.stat().st_size / 1024 / 1024:.1f} MB)"
        )

        return total_tokens
