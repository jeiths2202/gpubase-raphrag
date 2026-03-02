"""
Semantic Chunker

TOC/헤딩 기반 의미 단위 청킹을 수행합니다.
기존 RecursiveCharacterTextSplitter의 기계적 청킹을 대체합니다.
"""

import re
import logging
import hashlib
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

from .config import ChunkingConfig
from ..models.chunk import (
    EnhancedChunk, ChunkType, TableChunk, TableType
)
from ..models.document_structure import (
    DocumentStructure, HierarchyNode, NodeType
)
from ..parsers.pdf_parser import ParagraphReconstructor, TableToMarkdownConverter

logger = logging.getLogger(__name__)


class SemanticChunker:
    """의미 기반 청커

    섹션/단락 경계를 존중하며 적응형 크기로 청킹합니다.
    기존 RecursiveCharacterTextSplitter를 대체합니다.

    주요 기능:
    1. TOC 기반 섹션 경계 감지
    2. 단락 재구성 (ParagraphReconstructor)
    3. 테이블 분리 및 보존
    4. 적응형 청크 크기 (200-1500자)
    """

    # GFM 테이블 패턴
    TABLE_PATTERN = re.compile(
        r'^\|[^\n]+\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n?)+',
        re.MULTILINE
    )

    def __init__(self, config: ChunkingConfig = None):
        self.config = config or ChunkingConfig()
        self.paragraph_reconstructor = ParagraphReconstructor()
        self.table_converter = TableToMarkdownConverter()

    def chunk_document(
        self,
        structure: DocumentStructure,
        raw_pages: List[str],
        document_id: str = ""
    ) -> List[EnhancedChunk]:
        """문서를 의미 기반으로 청킹

        Args:
            structure: StructureParser에서 추출한 문서 구조
            raw_pages: 페이지별 원본 텍스트
            document_id: 출처 Document ID

        Returns:
            EnhancedChunk 리스트
        """
        all_chunks = []
        chunk_index = 0

        # 계층 구조 순회
        for node in structure.hierarchy:
            node_chunks = self._chunk_node(
                node=node,
                raw_pages=raw_pages,
                document_id=document_id,
                start_index=chunk_index
            )
            all_chunks.extend(node_chunks)
            chunk_index += len(node_chunks)

        # 청크 연결 (이전/다음 청크 ID 설정)
        self._link_chunks(all_chunks)

        logger.info(f"청킹 완료: {len(all_chunks)}개 청크 생성")
        return all_chunks

    def _chunk_node(
        self,
        node: HierarchyNode,
        raw_pages: List[str],
        document_id: str,
        start_index: int
    ) -> List[EnhancedChunk]:
        """계층 노드를 청킹

        Args:
            node: HierarchyNode
            raw_pages: 페이지별 원본 텍스트
            document_id: Document ID
            start_index: 시작 인덱스

        Returns:
            EnhancedChunk 리스트
        """
        chunks = []

        # 노드의 텍스트 추출
        text = self._get_node_text(node, raw_pages)
        if not text.strip():
            # 자식 노드만 처리
            for child in node.children:
                child_chunks = self._chunk_node(
                    child, raw_pages, document_id,
                    start_index + len(chunks)
                )
                chunks.extend(child_chunks)
            return chunks

        # 테이블 추출 및 분리
        text_without_tables, table_chunks = self._extract_and_separate_tables(
            text=text,
            section_title=node.title,
            page_range=(node.page_start, node.page_end),
            document_id=document_id
        )

        # 텍스트 청킹
        text_chunks = self._chunk_text(
            text=text_without_tables,
            section_title=node.title,
            section_level=node.level,
            page_range=(node.page_start, node.page_end),
            document_id=document_id,
            start_index=start_index
        )

        # 테이블 청크와 텍스트 청크 통합
        # 테이블은 관련 텍스트 청크에 첨부하거나 별도 청크로 추가
        if table_chunks and text_chunks:
            # 첫 번째 텍스트 청크에 테이블 첨부
            text_chunks[0].tables.extend(table_chunks)
            if text_chunks[0].chunk_type == ChunkType.TEXT:
                text_chunks[0].chunk_type = ChunkType.MIXED
        elif table_chunks and not text_chunks:
            # 테이블만 있는 경우 별도 청크 생성
            for tbl in table_chunks:
                chunk = EnhancedChunk(
                    chunk_id=EnhancedChunk.generate_id(
                        tbl.markdown, node.title, start_index + len(chunks)
                    ),
                    content=tbl.markdown,
                    chunk_type=ChunkType.TABLE,
                    section_title=node.title,
                    section_level=node.level,
                    page_range=(node.page_start, node.page_end),
                    document_id=document_id,
                    tables=[tbl]
                )
                chunks.append(chunk)

        chunks.extend(text_chunks)

        # 자식 노드 처리
        for child in node.children:
            child_chunks = self._chunk_node(
                child, raw_pages, document_id,
                start_index + len(chunks)
            )
            chunks.extend(child_chunks)

        return chunks

    def _get_node_text(
        self,
        node: HierarchyNode,
        raw_pages: List[str]
    ) -> str:
        """노드의 페이지 범위에서 텍스트 추출"""
        if node.raw_text:
            return node.raw_text

        texts = []
        start = node.page_start - 1  # 0-indexed
        end = min(node.page_end, len(raw_pages))

        for page_idx in range(start, end):
            if 0 <= page_idx < len(raw_pages):
                texts.append(raw_pages[page_idx])

        return "\n".join(texts)

    def _extract_and_separate_tables(
        self,
        text: str,
        section_title: str,
        page_range: Tuple[int, int],
        document_id: str
    ) -> Tuple[str, List[TableChunk]]:
        """텍스트에서 테이블 추출 및 분리

        Args:
            text: 원본 텍스트
            section_title: 섹션 제목
            page_range: 페이지 범위
            document_id: Document ID

        Returns:
            (테이블 제거된 텍스트, TableChunk 리스트)
        """
        table_chunks = []
        text_without_tables = text

        # GFM 테이블 패턴 검색
        for i, match in enumerate(self.TABLE_PATTERN.finditer(text)):
            table_md = match.group(0)

            # 테이블 유형 분류
            table_type = self._classify_table(table_md)

            # 행/열 수 계산
            lines = table_md.strip().split('\n')
            row_count = len(lines) - 1  # 헤더 구분선 제외
            col_count = len(lines[0].split('|')) - 2  # 양쪽 빈 문자열 제외

            # TableChunk 생성
            table_chunk = TableChunk(
                table_id=hashlib.md5(table_md[:100].encode()).hexdigest()[:12],
                table_type=table_type,
                markdown=table_md,
                title=self._extract_table_title(text, match.start()),
                row_count=row_count,
                col_count=col_count,
                page_number=page_range[0]
            )
            table_chunks.append(table_chunk)

            # 텍스트에서 테이블 제거
            text_without_tables = text_without_tables.replace(table_md, "\n[TABLE]\n")

        return text_without_tables, table_chunks

    def _classify_table(self, table_md: str) -> TableType:
        """테이블 유형 분류

        헤더와 내용 분석:
        - "에러", "코드", "Error" → ERROR_TABLE
        - "파라미터", "설정", "값" → PARAMETER_TABLE
        - "명령", "옵션", "인자" → COMMAND_TABLE
        - 기타 → DATA_TABLE
        """
        table_lower = table_md.lower()

        # 에러 테이블
        if any(kw in table_lower for kw in [
            'error', 'エラー', '에러', 'code', 'コード', '코드',
            'abend', 'return', 'rc=', 'cause', '原因', '원인'
        ]):
            return TableType.ERROR_TABLE

        # 파라미터 테이블
        if any(kw in table_lower for kw in [
            'parameter', 'パラメータ', '파라미터', 'config', '設定', '설정',
            'value', '値', '값', 'default', 'デフォルト', '기본값'
        ]):
            return TableType.PARAMETER_TABLE

        # 명령어 테이블
        if any(kw in table_lower for kw in [
            'command', 'コマンド', '명령', 'option', 'オプション', '옵션',
            'argument', '引数', '인자', 'syntax', '構文', '구문'
        ]):
            return TableType.COMMAND_TABLE

        return TableType.DATA_TABLE

    def _extract_table_title(self, text: str, table_start: int) -> str:
        """테이블 제목 추출

        테이블 바로 위의 줄에서 제목 추출 시도
        """
        # 테이블 앞의 텍스트
        before_table = text[:table_start].strip()
        if not before_table:
            return ""

        # 마지막 줄 추출
        lines = before_table.split('\n')
        last_line = lines[-1].strip()

        # 제목 패턴 확인 (표 1.1, Table 1, 테이블 등)
        title_patterns = [
            r'^(表|Table|테이블|図|Figure)\s*[\d.]+[:\s]*(.*)$',
            r'^[\d.]+\s+(.+)$',  # 1.1 제목
        ]

        for pattern in title_patterns:
            match = re.match(pattern, last_line, re.IGNORECASE)
            if match:
                return match.group(0)[:100]

        # 짧은 줄이면 제목으로 간주
        if len(last_line) < 100 and not last_line.startswith('|'):
            return last_line

        return ""

    def _chunk_text(
        self,
        text: str,
        section_title: str,
        section_level: int,
        page_range: Tuple[int, int],
        document_id: str,
        start_index: int
    ) -> List[EnhancedChunk]:
        """텍스트를 적응형 크기로 청킹

        1. 단락 재구성
        2. 적응형 크기에 맞게 그룹핑
        3. EnhancedChunk 생성
        """
        if not text.strip():
            return []

        # 단락 재구성
        lines = text.split('\n')
        paragraphs = self.paragraph_reconstructor.reconstruct(lines)

        if not paragraphs:
            return []

        # 단락을 청크로 그룹핑
        chunks = []
        current_content = []
        current_size = 0

        for para in paragraphs:
            para = para.strip()
            if not para or para == "[TABLE]":
                continue

            para_size = len(para)

            # 현재 청크에 추가할지 새 청크 시작할지 결정
            if current_size + para_size > self.config.target_chunk_size:
                # 현재 청크가 최소 크기 이상이면 저장
                if current_size >= self.config.min_chunk_size:
                    chunk_content = "\n\n".join(current_content)
                    chunk = self._create_chunk(
                        content=chunk_content,
                        section_title=section_title,
                        section_level=section_level,
                        page_range=page_range,
                        document_id=document_id,
                        index=start_index + len(chunks)
                    )
                    chunks.append(chunk)
                    current_content = []
                    current_size = 0

            current_content.append(para)
            current_size += para_size

        # 마지막 청크 처리
        if current_content:
            # 마지막 청크가 너무 작으면 이전 청크와 병합 시도
            if current_size < self.config.min_chunk_size and chunks:
                last_chunk = chunks[-1]
                merged_content = last_chunk.content + "\n\n" + "\n\n".join(current_content)
                if len(merged_content) <= self.config.max_chunk_size:
                    last_chunk.content = merged_content
                    last_chunk.char_count = len(merged_content)
                    current_content = []

            if current_content:
                chunk_content = "\n\n".join(current_content)
                chunk = self._create_chunk(
                    content=chunk_content,
                    section_title=section_title,
                    section_level=section_level,
                    page_range=page_range,
                    document_id=document_id,
                    index=start_index + len(chunks)
                )
                chunks.append(chunk)

        return chunks

    def _create_chunk(
        self,
        content: str,
        section_title: str,
        section_level: int,
        page_range: Tuple[int, int],
        document_id: str,
        index: int
    ) -> EnhancedChunk:
        """EnhancedChunk 생성"""
        # 섹션 컨텍스트 포함
        if self.config.include_section_context and section_title:
            content_with_context = f"[{section_title}]\n\n{content}"
        else:
            content_with_context = content

        return EnhancedChunk(
            chunk_id=EnhancedChunk.generate_id(content, section_title, index),
            content=content_with_context,
            chunk_type=ChunkType.TEXT,
            section_title=section_title,
            section_level=section_level,
            page_range=page_range,
            char_count=len(content_with_context),
            document_id=document_id,
            keywords=self._extract_keywords(content),
        )

    def _extract_keywords(self, text: str, max_keywords: int = 7) -> List[str]:
        """텍스트에서 키워드 추출"""
        keywords = set()

        # 대문자 약어 (TJES, VSAM 등)
        abbr_pattern = r'\b[A-Z]{2,}[A-Z0-9]*\b'
        for match in re.findall(abbr_pattern, text):
            if len(match) >= 2 and len(match) <= 20:
                keywords.add(match)

        # 명령어 패턴 (tjesmgr, oscboot 등)
        cmd_pattern = r'\b[a-z]+(?:mgr|boot|init|down|start|stop|ctl|cmd)\b'
        for match in re.findall(cmd_pattern, text, re.IGNORECASE):
            keywords.add(match.lower())

        # 에러 코드 패턴
        error_pattern = r'-\d{4,5}|S[0-9A-F]{3}|U\d{4}'
        for match in re.findall(error_pattern, text):
            keywords.add(match)

        # 일반적인 단어 제외
        common_words = {
            'THE', 'AND', 'FOR', 'NOT', 'ARE', 'ALL', 'WITH', 'THIS', 'THAT',
            'FROM', 'HAVE', 'HAS', 'HAD', 'BUT', 'WILL', 'CAN', 'MAY'
        }
        keywords = keywords - common_words

        return sorted(list(keywords))[:max_keywords]

    def _link_chunks(self, chunks: List[EnhancedChunk]) -> None:
        """청크 간 연결 설정"""
        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk.previous_chunk_id = chunks[i - 1].chunk_id
            if i < len(chunks) - 1:
                chunk.next_chunk_id = chunks[i + 1].chunk_id

    def chunk_text_simple(
        self,
        text: str,
        document_id: str = "",
        section_title: str = ""
    ) -> List[EnhancedChunk]:
        """간단한 텍스트 청킹 (구조 없이)

        DocumentStructure 없이 텍스트만으로 청킹할 때 사용
        """
        return self._chunk_text(
            text=text,
            section_title=section_title,
            section_level=0,
            page_range=(1, 1),
            document_id=document_id,
            start_index=0
        )
