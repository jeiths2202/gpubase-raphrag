"""
Table Processor

PDF에서 테이블을 추출하고 GFM Markdown으로 변환합니다.
기존 TableToMarkdownConverter를 활용합니다.
"""

import re
import logging
from typing import List, Optional, Tuple, Dict, Any

import fitz  # PyMuPDF

from ..models.chunk import ExtractedTable, TableChunk, TableType
from ..parsers.pdf_parser import TableToMarkdownConverter

logger = logging.getLogger(__name__)


class TableProcessor:
    """PDF 테이블 추출 및 Markdown 변환

    주요 기능:
    1. PDF에서 테이블 추출 (PyMuPDF)
    2. 테이블 유형 분류 (에러, 파라미터, 명령어, 데이터)
    3. GFM Markdown 변환
    4. 테이블 제목 추출

    환경 변수:
    - MIN_TABLE_ROWS: 최소 테이블 행 수 (기본값: 2)
    - MIN_TABLE_COLS: 최소 테이블 열 수 (기본값: 2)
    - MAX_TABLE_ROWS: 최대 테이블 행 수 (기본값: 100)
    """

    MIN_TABLE_ROWS = 2
    MIN_TABLE_COLS = 2
    MAX_TABLE_ROWS = 100

    # 테이블 제목 패턴
    TITLE_PATTERNS = [
        r'^(表|Table|테이블)\s*[\d.]+[:\s]*(.*)$',
        r'^[\d.]+\s+(.+)$',
    ]

    # 테이블 유형별 키워드
    TYPE_KEYWORDS = {
        TableType.ERROR_TABLE: [
            'error', 'エラー', '에러', 'code', 'コード', '코드',
            'abend', 'return', 'rc=', 'cause', '原因', '원인',
            'reason', '理由', '이유', 'message', 'メッセージ', '메시지'
        ],
        TableType.PARAMETER_TABLE: [
            'parameter', 'パラメータ', '파라미터', 'config', '設定', '설정',
            'value', '値', '값', 'default', 'デフォルト', '기본값',
            'option', 'オプション', '옵션', 'property', 'プロパティ', '속성'
        ],
        TableType.COMMAND_TABLE: [
            'command', 'コマンド', '명령', 'syntax', '構文', '구문',
            'argument', '引数', '인자', 'usage', '使用法', '사용법',
            'subcommand', 'サブコマンド', '하위명령'
        ]
    }

    def __init__(self):
        self.markdown_converter = TableToMarkdownConverter()

    def extract_tables_from_pdf(
        self,
        pdf_path: str,
        page_range: Tuple[int, int] = None
    ) -> List[ExtractedTable]:
        """PDF에서 테이블 추출

        Args:
            pdf_path: PDF 파일 경로
            page_range: 추출할 페이지 범위 (1-indexed, 포함)

        Returns:
            ExtractedTable 리스트
        """
        extracted = []

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            logger.error(f"PDF 열기 실패: {pdf_path} - {e}")
            return []

        try:
            start_page = (page_range[0] - 1) if page_range else 0
            end_page = page_range[1] if page_range else len(doc)

            for page_num in range(start_page, min(end_page, len(doc))):
                page = doc[page_num]
                page_tables = self._extract_page_tables(page, page_num + 1)
                extracted.extend(page_tables)

        finally:
            doc.close()

        logger.info(f"테이블 추출 완료: {len(extracted)}개 ({pdf_path})")
        return extracted

    def _extract_page_tables(
        self,
        page: fitz.Page,
        page_number: int
    ) -> List[ExtractedTable]:
        """페이지에서 테이블 추출

        Args:
            page: fitz.Page 객체
            page_number: 페이지 번호 (1-indexed)

        Returns:
            ExtractedTable 리스트
        """
        tables = []
        page_text = page.get_text()

        # PyMuPDF 테이블 찾기
        try:
            found_tables = page.find_tables()
        except Exception as e:
            logger.debug(f"테이블 찾기 실패 (page {page_number}): {e}")
            return []

        for table in found_tables:
            try:
                # 테이블 데이터 추출
                data = table.extract()

                if not data or len(data) < self.MIN_TABLE_ROWS:
                    continue

                # 열 수 확인
                col_count = max(len(row) for row in data) if data else 0
                if col_count < self.MIN_TABLE_COLS:
                    continue

                # 행 수 제한
                if len(data) > self.MAX_TABLE_ROWS:
                    data = data[:self.MAX_TABLE_ROWS]
                    logger.debug(f"테이블 행 제한: {len(data)} → {self.MAX_TABLE_ROWS}")

                # 헤더와 데이터 분리
                headers = [str(cell) if cell else "" for cell in data[0]]

                # None을 빈 문자열로 변환
                clean_data = []
                for row in data:
                    clean_row = [str(cell) if cell else "" for cell in row]
                    # 행 길이 맞추기
                    while len(clean_row) < col_count:
                        clean_row.append("")
                    clean_data.append(clean_row[:col_count])

                # 테이블 위치 (bbox)
                bbox = table.bbox if hasattr(table, 'bbox') else (0, 0, 0, 0)

                # 테이블 제목 추출
                title = self._find_table_title(page_text, bbox, page)

                tables.append(ExtractedTable(
                    page_number=page_number,
                    bbox=tuple(bbox),
                    data=clean_data,
                    headers=headers,
                    row_count=len(clean_data),
                    col_count=col_count,
                    title=title
                ))

            except Exception as e:
                logger.warning(f"테이블 추출 실패 (page {page_number}): {e}")
                continue

        return tables

    def _find_table_title(
        self,
        page_text: str,
        bbox: Tuple[float, float, float, float],
        page: fitz.Page
    ) -> str:
        """테이블 제목 찾기

        테이블 위쪽 영역에서 제목 패턴 검색

        Args:
            page_text: 페이지 전체 텍스트
            bbox: 테이블 위치
            page: fitz.Page 객체

        Returns:
            테이블 제목 (없으면 빈 문자열)
        """
        x0, y0, x1, y1 = bbox

        # 테이블 위쪽 영역 텍스트 추출
        title_rect = fitz.Rect(x0 - 10, max(0, y0 - 50), x1 + 10, y0)

        try:
            title_text = page.get_text("text", clip=title_rect).strip()
        except Exception:
            title_text = ""

        if not title_text:
            return ""

        # 제목 패턴 매칭
        lines = title_text.split('\n')
        for line in reversed(lines):
            line = line.strip()
            for pattern in self.TITLE_PATTERNS:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(0)[:100]

        # 짧은 마지막 줄이면 제목으로 간주
        last_line = lines[-1].strip() if lines else ""
        if last_line and len(last_line) < 80:
            return last_line

        return ""

    def classify_table(self, table: ExtractedTable) -> TableType:
        """테이블 유형 분류

        헤더와 데이터 내용을 분석하여 유형 결정

        Args:
            table: ExtractedTable

        Returns:
            TableType
        """
        # 검색할 텍스트 구성
        search_text = " ".join(table.headers).lower()
        if table.data:
            # 첫 몇 행의 데이터도 포함
            for row in table.data[:5]:
                search_text += " " + " ".join(row).lower()

        # 제목도 포함
        search_text += " " + table.title.lower()

        # 유형별 키워드 매칭
        type_scores = {}
        for table_type, keywords in self.TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in search_text)
            if score > 0:
                type_scores[table_type] = score

        if type_scores:
            return max(type_scores, key=type_scores.get)

        return TableType.DATA_TABLE

    def convert_to_markdown(self, table: ExtractedTable) -> str:
        """테이블을 GFM Markdown으로 변환

        Args:
            table: ExtractedTable

        Returns:
            GFM Markdown 문자열
        """
        if not table.data:
            return ""

        return self.markdown_converter.convert(table.data)

    def process_tables(
        self,
        tables: List[ExtractedTable]
    ) -> List[TableChunk]:
        """테이블 목록을 처리하여 TableChunk 생성

        Args:
            tables: ExtractedTable 리스트

        Returns:
            TableChunk 리스트
        """
        chunks = []

        for table in tables:
            # 유형 분류
            table_type = self.classify_table(table)

            # Markdown 변환
            markdown = self.convert_to_markdown(table)

            if not markdown.strip():
                continue

            # ID 생성 (내용 해시)
            import hashlib
            table_id = hashlib.md5(markdown[:100].encode()).hexdigest()[:12]

            chunks.append(TableChunk(
                table_id=table_id,
                table_type=table_type,
                markdown=markdown,
                title=table.title,
                row_count=table.row_count,
                col_count=table.col_count,
                page_number=table.page_number
            ))

        logger.info(f"테이블 처리 완료: {len(chunks)}개 TableChunk 생성")
        return chunks

    def process_pdf_tables(
        self,
        pdf_path: str,
        page_range: Tuple[int, int] = None
    ) -> List[TableChunk]:
        """PDF의 테이블을 추출하고 처리

        편의 메서드: extract + process 결합

        Args:
            pdf_path: PDF 파일 경로
            page_range: 페이지 범위 (선택)

        Returns:
            TableChunk 리스트
        """
        extracted = self.extract_tables_from_pdf(pdf_path, page_range)

        if not extracted:
            return []

        return self.process_tables(extracted)


class TableMerger:
    """분리된 테이블 병합

    페이지 경계에서 분리된 테이블을 감지하고 병합합니다.
    """

    # 연속 테이블 판단 기준
    HEADER_SIMILARITY_THRESHOLD = 0.8

    @staticmethod
    def should_merge(
        table1: ExtractedTable,
        table2: ExtractedTable
    ) -> bool:
        """두 테이블이 병합되어야 하는지 판단

        기준:
        - 연속된 페이지
        - 동일한 열 수
        - 유사한 헤더

        Args:
            table1: 첫 번째 테이블
            table2: 두 번째 테이블 (다음 페이지)

        Returns:
            병합 필요 여부
        """
        # 연속 페이지 확인
        if table2.page_number != table1.page_number + 1:
            return False

        # 열 수 일치
        if table1.col_count != table2.col_count:
            return False

        # 헤더 유사성 확인
        if table1.headers and table2.headers:
            matching = sum(
                1 for h1, h2 in zip(table1.headers, table2.headers)
                if h1.lower() == h2.lower()
            )
            similarity = matching / len(table1.headers)
            return similarity >= TableMerger.HEADER_SIMILARITY_THRESHOLD

        return False

    @staticmethod
    def merge(
        table1: ExtractedTable,
        table2: ExtractedTable
    ) -> ExtractedTable:
        """두 테이블 병합

        Args:
            table1: 첫 번째 테이블
            table2: 두 번째 테이블

        Returns:
            병합된 테이블
        """
        # 두 번째 테이블의 헤더 행 제거 (중복)
        data2 = table2.data[1:] if table2.data else []

        merged_data = table1.data + data2

        return ExtractedTable(
            page_number=table1.page_number,
            bbox=table1.bbox,
            data=merged_data,
            headers=table1.headers,
            row_count=len(merged_data),
            col_count=table1.col_count,
            title=table1.title or table2.title
        )

    @classmethod
    def merge_consecutive(
        cls,
        tables: List[ExtractedTable]
    ) -> List[ExtractedTable]:
        """연속 테이블 병합

        Args:
            tables: 테이블 리스트 (페이지 순)

        Returns:
            병합된 테이블 리스트
        """
        if not tables:
            return []

        result = [tables[0]]

        for table in tables[1:]:
            if cls.should_merge(result[-1], table):
                result[-1] = cls.merge(result[-1], table)
                logger.debug(
                    f"테이블 병합: page {result[-1].page_number} + {table.page_number}"
                )
            else:
                result.append(table)

        return result
