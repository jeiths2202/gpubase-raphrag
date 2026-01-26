"""PDF 파싱 모듈"""

import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

import pymupdf

from ..models.manual import ManualMetadata, ManualContent, TOCItem
from ..config import config

logger = logging.getLogger(__name__)


class PDFParser:
    """PDF 문서 파서"""

    def __init__(self):
        self.filename_pattern = re.compile(config.filename_pattern)

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
        """페이지별 텍스트 추출"""
        pages = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            # 기본 정제
            text = self._clean_text(text)
            pages.append(text)
        return pages

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
