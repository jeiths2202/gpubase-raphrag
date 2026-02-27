"""PDF 파싱 모듈

ChatGPT-Quality Pipeline 개선 (PDCA: chatgpt-quality-pipeline):
- ParagraphReconstructor: PDF 줄바꿈을 의미있는 단락으로 재구성
- TableToMarkdownConverter: 테이블을 GFM Markdown으로 변환
"""

import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

import pymupdf

from ..models.manual import ManualMetadata, ManualContent, TOCItem
from ..config import config

logger = logging.getLogger(__name__)


# =============================================================================
# ChatGPT-Quality Pipeline Components
# =============================================================================

class ParagraphReconstructor:
    """
    PDF 줄바꿈을 의미있는 단락으로 재구성

    단락 재구성 규칙:
    1. 줄이 문장 종결자(.!?。？！)로 끝나면 단락 종료
    2. 줄이 콜론(:)으로 끝나면 다음 줄은 목록/설명일 가능성
    3. 40자 이하 짧은 줄은 다음 줄과 병합 (제목 제외)
    4. 빈 줄은 단락 구분자
    5. 번호/불릿으로 시작하면 리스트 항목
    """

    SENTENCE_ENDERS = frozenset('.!?。？！')
    LIST_MARKERS = re.compile(r'^[\s]*([-•*·]|\d+[.)]\s|\([0-9]+\))')
    HEADING_PATTERN = re.compile(r'^[\s]*(\d+\.)+\s*\S')  # 1.1, 1.1.1 등
    SHORT_LINE_THRESHOLD = 40

    def reconstruct(self, lines: List[str]) -> List[str]:
        """
        PDF 줄 목록을 의미있는 단락으로 재구성

        Args:
            lines: PDF에서 추출한 줄 목록

        Returns:
            재구성된 단락 목록
        """
        paragraphs = []
        current = []

        for line in lines:
            line = line.strip()
            if not line:
                # 빈 줄 = 단락 종료
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
                continue

            # 제목 패턴 (1.1, 1.1.1 등)은 별도 단락
            if self.HEADING_PATTERN.match(line):
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
                paragraphs.append(line)
                continue

            # 리스트 항목은 별도 처리
            if self.LIST_MARKERS.match(line):
                if current:
                    paragraphs.append(' '.join(current))
                    current = []
                paragraphs.append(line)
                continue

            current.append(line)

            # 문장 종결자로 끝나면 단락 완료
            if line and line[-1] in self.SENTENCE_ENDERS:
                paragraphs.append(' '.join(current))
                current = []

        if current:
            paragraphs.append(' '.join(current))

        return paragraphs


class TableToMarkdownConverter:
    """
    PyMuPDF 테이블을 GFM Markdown으로 변환

    Input (PyMuPDF table.extract()):
        [
            ["Header1", "Header2", "Header3"],
            ["Row1Col1", "Row1Col2", "Row1Col3"],
            ["Row2Col1", "Row2Col2", "Row2Col3"]
        ]

    Output (GFM Markdown):
        | Header1 | Header2 | Header3 |
        |---------|---------|---------|
        | Row1Col1 | Row1Col2 | Row1Col3 |
        | Row2Col1 | Row2Col2 | Row2Col3 |
    """

    def convert(self, table_data: List[List[str]]) -> str:
        """
        2D 테이블 데이터를 GFM Markdown 테이블로 변환

        Args:
            table_data: 2D 리스트 (첫 행은 헤더)

        Returns:
            GFM Markdown 테이블 문자열
        """
        if not table_data or len(table_data) < 2:
            return ""

        # None 값을 빈 문자열로 치환
        table_data = [
            [str(cell) if cell is not None else "" for cell in row]
            for row in table_data
        ]

        # 열 수 정규화 (가장 긴 행 기준)
        max_cols = max(len(row) for row in table_data)
        table_data = [
            row + [""] * (max_cols - len(row))
            for row in table_data
        ]

        # 열 너비 계산 (최소 3자, 최대 50자)
        col_widths = []
        for i in range(max_cols):
            max_width = max(len(str(row[i])) for row in table_data)
            col_widths.append(min(max(max_width, 3), 50))

        lines = []

        # 헤더 행
        header = table_data[0]
        header_line = "| " + " | ".join(
            str(cell)[:col_widths[i]].ljust(col_widths[i])
            for i, cell in enumerate(header)
        ) + " |"
        lines.append(header_line)

        # 구분선
        separator = "|" + "|".join(
            "-" * (w + 2) for w in col_widths
        ) + "|"
        lines.append(separator)

        # 데이터 행
        for row in table_data[1:]:
            data_line = "| " + " | ".join(
                str(cell)[:col_widths[i]].ljust(col_widths[i])
                for i, cell in enumerate(row)
            ) + " |"
            lines.append(data_line)

        return "\n".join(lines)


class PDFParser:
    """PDF 문서 파서

    ChatGPT-Quality Pipeline 통합:
    - 단락 재구성으로 불필요한 줄바꿈 제거
    - 테이블을 GFM Markdown으로 자동 변환
    """

    def __init__(self):
        self.filename_pattern = re.compile(config.filename_pattern)
        # ChatGPT-Quality Pipeline 컴포넌트
        self.paragraph_reconstructor = ParagraphReconstructor()
        self.table_converter = TableToMarkdownConverter()

    def parse(self, pdf_path: Path) -> Optional[ManualContent]:
        """PDF 파일 파싱"""
        if not pdf_path.exists():
            logger.error(f"파일을 찾을 수 없습니다: {pdf_path}")
            return None

        try:
            doc = pymupdf.open(str(pdf_path))

            # 메타데이터 추출
            metadata = self._extract_metadata(pdf_path, doc)

            # 페이지별 텍스트 추출
            pages = self._extract_pages(doc)

            # 목차 추출
            toc = self._extract_toc(doc)
            metadata.toc = toc

            doc.close()

            content = ManualContent(
                metadata=metadata,
                pages=pages,
                full_text="\n\n".join(pages)
            )

            logger.info(f"파싱 완료: {pdf_path.name} ({len(pages)} 페이지)")
            return content

        except Exception as e:
            logger.error(f"PDF 파싱 실패: {pdf_path} - {e}")
            return None

    def _extract_metadata(self, pdf_path: Path, doc: pymupdf.Document) -> ManualMetadata:
        """메타데이터 추출"""
        file_name = pdf_path.name
        file_size = pdf_path.stat().st_size

        metadata = ManualMetadata(
            file_path=pdf_path,
            file_name=file_name,
            file_size=file_size,
            page_count=len(doc)
        )

        # PDF 내장 메타데이터
        pdf_meta = doc.metadata
        if pdf_meta:
            metadata.title = pdf_meta.get("title", "")
            metadata.author = pdf_meta.get("author", "")
            if pdf_meta.get("creationDate"):
                try:
                    # PDF 날짜 형식: D:20250101120000
                    date_str = pdf_meta["creationDate"]
                    if date_str.startswith("D:"):
                        date_str = date_str[2:16]
                        metadata.creation_date = datetime.strptime(date_str, "%Y%m%d%H%M%S")
                except (ValueError, IndexError):
                    pass

        # 파일명에서 정보 추출
        self._parse_filename(file_name, metadata)

        return metadata

    def _parse_filename(self, filename: str, metadata: ManualMetadata) -> None:
        """파일명에서 메타데이터 추출"""
        # 표준 패턴 시도
        match = self.filename_pattern.match(filename)
        if match:
            metadata.prefix = match.group("prefix")
            metadata.component = match.group("component")
            metadata.platform = match.group("platform")
            metadata.version = match.group("version")
            metadata.guide_type = match.group("guide_type")
            metadata.doc_version = match.group("doc_version")
            metadata.language = match.group("language")
            return

        # 대체 패턴들 시도
        # Tibero_7_SQL_Reference_Guide_v2.1.1_jp.pdf
        alt_pattern = r"(?P<prefix>Tibero|Tmax)_(?P<version>[\d.]+)_(?P<guide_type>[A-Za-z_-]+)_v(?P<doc_version>[\d.]+)_(?P<language>ja|jp|en)\.pdf"
        match = re.match(alt_pattern, filename)
        if match:
            metadata.prefix = match.group("prefix")
            metadata.component = match.group("prefix")
            metadata.version = match.group("version")
            metadata.guide_type = match.group("guide_type").replace("_", "-")
            metadata.doc_version = match.group("doc_version")
            metadata.language = match.group("language")
            return

        # 기본값으로 파일명 분석
        logger.warning(f"표준 패턴 불일치: {filename}")
        # 언어 추출
        if "_ja." in filename or "_jp." in filename:
            metadata.language = "ja"
        elif "_en." in filename:
            metadata.language = "en"

        # 가이드 타입 추출
        for guide_type in config.guide_types.keys():
            if guide_type.replace("-", "_") in filename or guide_type in filename:
                metadata.guide_type = guide_type
                break

    def _extract_pages(self, doc: pymupdf.Document) -> List[str]:
        """페이지별 텍스트 추출 (ChatGPT-Quality Pipeline 적용)

        개선 사항:
        1. 테이블 먼저 추출하여 GFM Markdown으로 변환
        2. 일반 텍스트는 단락 재구성 적용
        3. 테이블과 텍스트를 적절히 병합
        """
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]

            # 1. 테이블 추출 및 GFM 변환
            tables_md = self._extract_and_convert_tables(page)

            # 2. 일반 텍스트 추출
            text = page.get_text()

            # 3. 기본 정제
            text = self._clean_text(text)

            # 4. 단락 재구성 적용
            lines = text.split('\n')
            paragraphs = self.paragraph_reconstructor.reconstruct(lines)

            # 5. 단락들을 연결
            reconstructed_text = '\n\n'.join(paragraphs)

            # 6. 테이블이 있으면 텍스트 끝에 추가 (위치 기반 삽입은 복잡하므로)
            if tables_md:
                table_section = '\n\n'.join(tables_md)
                reconstructed_text = f"{reconstructed_text}\n\n{table_section}"

            pages.append(reconstructed_text)

        return pages

    def _extract_and_convert_tables(self, page) -> List[str]:
        """페이지에서 테이블 추출 및 GFM Markdown 변환

        Args:
            page: PyMuPDF 페이지 객체

        Returns:
            GFM Markdown 테이블 문자열 리스트
        """
        result = []
        try:
            tables = page.find_tables()
            for table in tables:
                data = table.extract()
                if data and len(data) >= 2:  # 헤더 + 최소 1개 데이터 행
                    md = self.table_converter.convert(data)
                    if md:
                        result.append(md)
        except Exception as e:
            logger.debug(f"테이블 추출 실패: {e}")
        return result

    def _clean_text(self, text: str) -> str:
        """텍스트 정제"""
        # 여러 공백을 하나로
        text = re.sub(r"[ \t]+", " ", text)
        # 여러 줄바꿈을 두 개로
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 페이지 번호 패턴 제거 (예: "| 51", "52 |")
        text = re.sub(r"\|\s*\d+\s*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\d+\s*\|", "", text, flags=re.MULTILINE)
        return text.strip()

    def _extract_toc(self, doc: pymupdf.Document) -> List[TOCItem]:
        """목차 추출"""
        toc = doc.get_toc()
        items = []
        for item in toc:
            level, title, page = item
            items.append(TOCItem(level=level, title=title, page=page))
        return items

    def get_section_text(
        self,
        content: ManualContent,
        section_title: str,
        exact_match: bool = False
    ) -> Optional[str]:
        """특정 섹션의 텍스트 추출"""
        toc = content.metadata.toc
        target_item = None

        for item in toc:
            if exact_match:
                if item.title == section_title:
                    target_item = item
                    break
            else:
                if section_title.lower() in item.title.lower():
                    target_item = item
                    break

        if target_item:
            return content.get_section_by_toc(target_item)
        return None

    def extract_tables(self, doc: pymupdf.Document, page_num: int) -> List[List[List[str]]]:
        """페이지에서 테이블 추출"""
        page = doc[page_num]
        tables = page.find_tables()
        result = []
        for table in tables:
            extracted = table.extract()
            if extracted:
                result.append(extracted)
        return result
