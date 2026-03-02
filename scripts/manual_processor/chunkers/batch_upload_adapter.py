"""
Batch Upload Adapter

기존 batch_upload.py와 SemanticChunker를 통합하는 어댑터입니다.
RecursiveCharacterTextSplitter를 SemanticChunker로 대체합니다.
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import fitz  # PyMuPDF

from .config import ChunkingConfig
from .semantic_chunker import SemanticChunker
from ..models.chunk import EnhancedChunk, ChunkType
from ..models.document_structure import DocumentStructure, HierarchyNode, NodeType
from ..parsers.structure_parser import StructureParser
from ..processors.image_processor import ImageProcessor
from ..processors.table_processor import TableProcessor, TableMerger
from ..cache.image_cache import ImageCache

logger = logging.getLogger(__name__)


class SemanticBatchChunker:
    """Batch Upload용 Semantic Chunker

    기존 RecursiveCharacterTextSplitter(CHUNK_SIZE=800, CHUNK_OVERLAP=150)를
    의미 기반 청킹으로 대체합니다.

    주요 차이점:
    1. 고정 크기 → 적응형 크기 (200-1500자)
    2. 기계적 분할 → 섹션/단락 경계 존중
    3. 텍스트만 → 멀티모달 (이미지, 테이블 포함)

    사용법:
    ```python
    from scripts.manual_processor.chunkers.batch_upload_adapter import SemanticBatchChunker

    chunker = SemanticBatchChunker()
    chunks = chunker.chunk_pdf("/path/to/file.pdf", document_id="doc123")

    # 기존 형식과 호환되는 텍스트 리스트
    text_chunks = [chunk.content for chunk in chunks]
    ```
    """

    def __init__(
        self,
        config: ChunkingConfig = None,
        process_images: bool = True,
        process_tables: bool = True,
        use_cache: bool = True
    ):
        """
        Args:
            config: 청킹 설정 (기본값 사용 시 None)
            process_images: Vision LLM으로 이미지 처리 여부
            process_tables: 테이블 추출 및 변환 여부
            use_cache: 이미지 캐시 사용 여부
        """
        self.config = config or ChunkingConfig()
        self.process_images = process_images
        self.process_tables = process_tables

        # 핵심 컴포넌트
        self.semantic_chunker = SemanticChunker(self.config)
        self.structure_parser = StructureParser()

        # 멀티모달 프로세서
        if process_images:
            cache = ImageCache() if use_cache else None
            self.image_processor = ImageProcessor(cache=cache, use_cache=use_cache)
        else:
            self.image_processor = None

        if process_tables:
            self.table_processor = TableProcessor()
        else:
            self.table_processor = None

        logger.info(
            f"SemanticBatchChunker 초기화 완료 "
            f"(images={process_images}, tables={process_tables}, cache={use_cache})"
        )

    def chunk_pdf(
        self,
        pdf_path: str,
        document_id: str = "",
        language: str = "ja"
    ) -> List[EnhancedChunk]:
        """PDF를 의미 기반으로 청킹

        Args:
            pdf_path: PDF 파일 경로
            document_id: 문서 ID (없으면 파일명 해시)
            language: 문서 언어 (ja/kr/en)

        Returns:
            EnhancedChunk 리스트
        """
        path = Path(pdf_path)
        if not path.exists():
            logger.error(f"파일을 찾을 수 없음: {pdf_path}")
            return []

        if not document_id:
            document_id = hashlib.md5(path.name.encode()).hexdigest()[:12]

        logger.info(f"PDF 청킹 시작: {path.name} (id={document_id})")

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"PDF 열기 실패: {e}")
            return []

        try:
            # 1. 페이지별 텍스트 추출
            raw_pages = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                raw_pages.append(text)

            # 2. 문서 구조 분석
            structure = self._analyze_structure(doc, raw_pages)

            # 3. 의미 기반 청킹
            chunks = self.semantic_chunker.chunk_document(
                structure=structure,
                raw_pages=raw_pages,
                document_id=document_id
            )

            # 4. 이미지 처리 (선택)
            if self.process_images and self.image_processor:
                chunks = self._add_image_descriptions(
                    chunks, pdf_path, structure
                )

            # 5. 테이블 처리 (선택)
            if self.process_tables and self.table_processor:
                chunks = self._enhance_table_chunks(
                    chunks, pdf_path
                )

            logger.info(f"청킹 완료: {len(chunks)}개 청크 생성")
            return chunks

        finally:
            doc.close()

    def _analyze_structure(
        self,
        doc: fitz.Document,
        raw_pages: List[str]
    ) -> DocumentStructure:
        """문서 구조 분석

        TOC가 있으면 활용, 없으면 헤딩 패턴으로 추론
        """
        # PyMuPDF TOC 추출 시도
        toc = doc.get_toc()

        if toc and len(toc) > 3:
            # TOC 기반 구조 생성
            return self._structure_from_toc(toc, len(raw_pages))
        else:
            # 헤딩 패턴 기반 추론
            return self._structure_from_headings(raw_pages)

    def _structure_from_toc(
        self,
        toc: List[Tuple[int, str, int]],
        total_pages: int
    ) -> DocumentStructure:
        """TOC에서 문서 구조 생성

        Args:
            toc: PyMuPDF TOC [(level, title, page), ...]
            total_pages: 전체 페이지 수

        Returns:
            DocumentStructure
        """
        hierarchy = []
        stack = []  # (level, node) 스택

        for i, (level, title, page) in enumerate(toc):
            # 다음 항목의 페이지로 page_end 결정
            if i + 1 < len(toc):
                page_end = toc[i + 1][2]
            else:
                page_end = total_pages

            node = HierarchyNode(
                node_type=NodeType.SECTION,
                title=title.strip(),
                level=level,
                page_start=page,
                page_end=page_end,
                children=[]
            )

            # 스택 조정 및 부모-자식 관계 설정
            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                stack[-1][1].children.append(node)
            else:
                hierarchy.append(node)

            stack.append((level, node))

        return DocumentStructure(
            title="",
            total_pages=total_pages,
            hierarchy=hierarchy
        )

    def _structure_from_headings(
        self,
        raw_pages: List[str]
    ) -> DocumentStructure:
        """헤딩 패턴에서 문서 구조 추론"""
        import re

        # 일반적인 헤딩 패턴
        heading_patterns = [
            (1, r'^第\s*\d+\s*章'),           # 일본어 장
            (1, r'^Chapter\s+\d+'),            # 영어 장
            (2, r'^\d+\.\d+\s+[^\d]'),         # 2.1 제목
            (3, r'^\d+\.\d+\.\d+\s+[^\d]'),    # 2.1.1 제목
        ]

        hierarchy = []
        current_section = None

        for page_num, page_text in enumerate(raw_pages, 1):
            lines = page_text.split('\n')

            for line in lines[:20]:  # 페이지 상단만 확인
                line = line.strip()
                if len(line) < 3 or len(line) > 100:
                    continue

                for level, pattern in heading_patterns:
                    if re.match(pattern, line):
                        node = HierarchyNode(
                            node_type=NodeType.SECTION,
                            title=line[:80],
                            level=level,
                            page_start=page_num,
                            page_end=page_num,
                            children=[]
                        )

                        # 이전 섹션의 page_end 업데이트
                        if current_section:
                            current_section.page_end = page_num - 1

                        hierarchy.append(node)
                        current_section = node
                        break

        # 마지막 섹션 page_end
        if current_section:
            current_section.page_end = len(raw_pages)

        # 구조가 없으면 전체를 하나의 섹션으로
        if not hierarchy:
            hierarchy.append(HierarchyNode(
                node_type=NodeType.SECTION,
                title="Document",
                level=1,
                page_start=1,
                page_end=len(raw_pages),
                children=[]
            ))

        return DocumentStructure(
            title="",
            total_pages=len(raw_pages),
            hierarchy=hierarchy
        )

    def _add_image_descriptions(
        self,
        chunks: List[EnhancedChunk],
        pdf_path: str,
        structure: DocumentStructure
    ) -> List[EnhancedChunk]:
        """청크에 이미지 설명 추가"""
        if not self.image_processor:
            return chunks

        try:
            # 이미지 추출 및 처리
            image_chunks = self.image_processor.process_images_sync(
                self.image_processor.extract_images_from_pdf(pdf_path)
            )

            if not image_chunks:
                return chunks

            # 페이지별 이미지 그룹화
            page_images = {}
            for img_chunk in image_chunks:
                page = img_chunk.page_number
                if page not in page_images:
                    page_images[page] = []
                page_images[page].append(img_chunk)

            # 해당 페이지의 청크에 이미지 첨부
            for chunk in chunks:
                chunk_pages = range(chunk.page_range[0], chunk.page_range[1] + 1)
                for page in chunk_pages:
                    if page in page_images:
                        chunk.images.extend(page_images[page])
                        if chunk.chunk_type == ChunkType.TEXT:
                            chunk.chunk_type = ChunkType.MIXED

            logger.info(f"이미지 {len(image_chunks)}개 청크에 첨부")

        except Exception as e:
            logger.warning(f"이미지 처리 실패: {e}")

        return chunks

    def _enhance_table_chunks(
        self,
        chunks: List[EnhancedChunk],
        pdf_path: str
    ) -> List[EnhancedChunk]:
        """테이블 청크 개선"""
        if not self.table_processor:
            return chunks

        try:
            # 테이블 추출
            extracted = self.table_processor.extract_tables_from_pdf(pdf_path)

            if not extracted:
                return chunks

            # 연속 테이블 병합
            merged = TableMerger.merge_consecutive(extracted)

            # TableChunk 생성
            table_chunks = self.table_processor.process_tables(merged)

            if not table_chunks:
                return chunks

            # 페이지별 테이블 그룹화
            page_tables = {}
            for tbl_chunk in table_chunks:
                page = tbl_chunk.page_number
                if page not in page_tables:
                    page_tables[page] = []
                page_tables[page].append(tbl_chunk)

            # 해당 페이지의 청크에 테이블 첨부
            for chunk in chunks:
                chunk_pages = range(chunk.page_range[0], chunk.page_range[1] + 1)
                for page in chunk_pages:
                    if page in page_tables:
                        chunk.tables.extend(page_tables[page])
                        if chunk.chunk_type == ChunkType.TEXT:
                            chunk.chunk_type = ChunkType.MIXED

            logger.info(f"테이블 {len(table_chunks)}개 청크에 첨부")

        except Exception as e:
            logger.warning(f"테이블 처리 실패: {e}")

        return chunks

    def chunk_text(
        self,
        text: str,
        document_id: str = ""
    ) -> List[EnhancedChunk]:
        """텍스트 직접 청킹 (PDF 없이)

        기존 batch_upload.py 호환용

        Args:
            text: 청킹할 텍스트
            document_id: 문서 ID

        Returns:
            EnhancedChunk 리스트
        """
        return self.semantic_chunker.chunk_text_simple(
            text=text,
            document_id=document_id
        )

    def get_text_chunks(
        self,
        chunks: List[EnhancedChunk]
    ) -> List[str]:
        """EnhancedChunk에서 텍스트만 추출

        기존 batch_upload.py 호환용 - List[str] 반환

        Args:
            chunks: EnhancedChunk 리스트

        Returns:
            텍스트 리스트
        """
        texts = []
        for chunk in chunks:
            content = chunk.content

            # 테이블 마크다운 추가
            for tbl in chunk.tables:
                content += f"\n\n{tbl.markdown}"

            # 이미지 설명 추가
            for img in chunk.images:
                if img.description:
                    content += f"\n\n[Image: {img.description}]"

            texts.append(content)

        return texts


def create_semantic_text_splitter(
    min_chunk_size: int = 200,
    target_chunk_size: int = 800,
    max_chunk_size: int = 1500
) -> SemanticBatchChunker:
    """RecursiveCharacterTextSplitter 대체 팩토리

    기존 코드와의 호환성을 위한 팩토리 함수

    Args:
        min_chunk_size: 최소 청크 크기 (기본값: 200)
        target_chunk_size: 목표 청크 크기 (기본값: 800)
        max_chunk_size: 최대 청크 크기 (기본값: 1500)

    Returns:
        SemanticBatchChunker 인스턴스

    사용 예:
    ```python
    # 기존 코드
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    chunks = splitter.split_text(text)

    # 새 코드
    from scripts.manual_processor.chunkers.batch_upload_adapter import create_semantic_text_splitter
    chunker = create_semantic_text_splitter(target_chunk_size=800)
    enhanced_chunks = chunker.chunk_text(text)
    chunks = chunker.get_text_chunks(enhanced_chunks)
    ```
    """
    config = ChunkingConfig(
        min_chunk_size=min_chunk_size,
        target_chunk_size=target_chunk_size,
        max_chunk_size=max_chunk_size
    )

    return SemanticBatchChunker(
        config=config,
        process_images=False,  # 텍스트 전용
        process_tables=False,
        use_cache=False
    )
