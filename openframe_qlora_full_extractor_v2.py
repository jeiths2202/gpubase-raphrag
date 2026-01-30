#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenFrame 매뉴얼 QLoRA 학습 데이터 추출기 v2.0
==============================================
TmaxSoft 기술 문서에서 instruction-response 쌍을 생성합니다.
표(Table)와 이미지 추출 기능이 개선되었습니다.

사용법:
  1. PDF 파싱 모드: python openframe_qlora_full_extractor_v2.py --input manual.pdf --output data.jsonl
  2. 샘플 생성 모드: python openframe_qlora_full_extractor_v2.py --sample
  3. 이미지 추출: python openframe_qlora_full_extractor_v2.py --input manual.pdf --extract-images

요구사항:
  - Python 3.8+
  - PyMuPDF (pip install PyMuPDF)

출력 형식:
  - Alpaca: {"instruction": "...", "input": "", "output": "..."}
  - ShareGPT: {"conversations": [{"from": "human", "value": "..."}, {"from": "gpt", "value": "..."}]}

v2.0 개선사항:
  - 표(Table) 추출 및 마크다운 변환
  - 이미지 추출 및 메타데이터 저장
  - 표/이미지 기반 Q&A 생성
  - 더 정교한 섹션 파싱
"""

import json
import re
import argparse
import base64
import io
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from datetime import datetime

# PDF 처리를 위한 라이브러리
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
    PYMUPDF_VERSION = tuple(map(int, fitz.version[0].split('.')[:2]))
except ImportError:
    HAS_PYMUPDF = False
    PYMUPDF_VERSION = (0, 0)


class ContentType(Enum):
    """콘텐츠 유형 분류"""
    CHAPTER = "chapter"
    SECTION = "section"
    SUBSECTION = "subsection"
    DEFINITION = "definition"
    PROCEDURE = "procedure"
    CODE_EXAMPLE = "code_example"
    TABLE = "table"
    CONFIGURATION = "configuration"
    COMMAND = "command"
    ERROR_MESSAGE = "error_message"
    LOG = "log"
    API = "api"
    IMAGE = "image"


@dataclass
class TableData:
    """표 데이터 구조"""
    headers: List[str]
    rows: List[List[str]]
    caption: str = ""
    page_number: int = 0

    def to_markdown(self) -> str:
        """마크다운 표로 변환"""
        if not self.headers and not self.rows:
            return ""

        lines = []

        # 캡션
        if self.caption:
            lines.append(f"**{self.caption}**\n")

        # 헤더가 없으면 첫 번째 행을 헤더로 사용
        if self.headers:
            headers = self.headers
            data_rows = self.rows
        elif self.rows:
            headers = self.rows[0]
            data_rows = self.rows[1:]
        else:
            return ""

        # 헤더 행
        lines.append("| " + " | ".join(str(h).strip() for h in headers) + " |")
        # 구분선
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        # 데이터 행
        for row in data_rows:
            # 행의 길이를 헤더에 맞춤
            padded_row = list(row) + [""] * (len(headers) - len(row))
            lines.append("| " + " | ".join(str(c).strip() for c in padded_row[:len(headers)]) + " |")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "headers": self.headers,
            "rows": self.rows,
            "caption": self.caption,
            "page_number": self.page_number,
            "markdown": self.to_markdown()
        }


@dataclass
class ImageData:
    """이미지 데이터 구조"""
    image_index: int
    page_number: int
    width: int
    height: int
    image_type: str  # png, jpeg, etc.
    caption: str = ""
    surrounding_text: str = ""
    base64_data: Optional[str] = None  # 선택적 base64 인코딩 데이터

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "image_index": self.image_index,
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
            "image_type": self.image_type,
            "caption": self.caption,
            "surrounding_text": self.surrounding_text,
            "has_base64": self.base64_data is not None
        }


@dataclass
class TrainingExample:
    """QLoRA 학습용 데이터 구조"""
    instruction: str
    input: str
    output: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """전체 데이터 딕셔너리 변환"""
        return {
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output,
            "metadata": self.metadata
        }

    def to_alpaca_format(self) -> Dict[str, str]:
        """Alpaca 형식으로 변환 (LLaMA Fine-tuning용)"""
        return {
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output
        }

    def to_sharegpt_format(self) -> Dict[str, Any]:
        """ShareGPT 형식으로 변환 (ChatGPT-like 학습용)"""
        messages = []
        if self.input:
            messages.append({
                "from": "human",
                "value": f"{self.instruction}\n\n{self.input}"
            })
        else:
            messages.append({
                "from": "human",
                "value": self.instruction
            })
        messages.append({
            "from": "gpt",
            "value": self.output
        })
        return {"conversations": messages}

    def to_openai_format(self) -> Dict[str, Any]:
        """OpenAI Fine-tuning 형식으로 변환"""
        messages = []
        messages.append({
            "role": "system",
            "content": "あなたはOpenFrame技術サポートのアシスタントです。OpenFrameに関する質問に正確に回答してください。"
        })

        user_content = self.instruction
        if self.input:
            user_content += f"\n\n{self.input}"

        messages.append({"role": "user", "content": user_content})
        messages.append({"role": "assistant", "content": self.output})

        return {"messages": messages}

    def get_id(self) -> str:
        """고유 ID 생성"""
        content = f"{self.instruction}{self.input}{self.output}"
        return hashlib.md5(content.encode()).hexdigest()[:12]


@dataclass
class DocumentSection:
    """문서 섹션 구조"""
    level: int  # 1: 章, 2: 節, 3: 項
    number: str  # "1.1", "A.2" 등
    title: str
    content: str
    content_type: ContentType
    parent_section: Optional[str] = None
    code_blocks: List[str] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)
    images: List[ImageData] = field(default_factory=list)
    page_number: Optional[int] = None


class OpenFrameManualParserV2:
    """OpenFrame 매뉴얼 파서 v2 - 표와 이미지 추출 개선"""

    # 섹션 패턴 (일본어/영어 혼합)
    CHAPTER_PATTERN = re.compile(r'^第(\d+)章\s+(.+)$', re.MULTILINE)
    SECTION_PATTERN = re.compile(r'^(\d+\.\d+\.?)\s+(.+)$', re.MULTILINE)
    SUBSECTION_PATTERN = re.compile(r'^(\d+\.\d+\.\d+\.?)\s+(.+)$', re.MULTILINE)
    APPENDIX_PATTERN = re.compile(r'^付録\s*([A-Z])\.?\s+(.+)$', re.MULTILINE)

    # 코드 블록 패턴
    CODE_BLOCK_PATTERN = re.compile(r'^\$\s+.+$|^[A-Z_]+\s*=.+$', re.MULTILINE)
    CONFIG_PATTERN = re.compile(r'^\[.+\]$', re.MULTILINE)
    SQL_PATTERN = re.compile(r'^SQL>\s*.+$', re.MULTILINE)

    # 표 캡션 패턴
    TABLE_CAPTION_PATTERN = re.compile(r'(?:表|Table)\s*[\d\-\.]+[\.:]?\s*(.+?)(?:\n|$)', re.IGNORECASE)

    # 이미지/그림 캡션 패턴
    FIGURE_CAPTION_PATTERN = re.compile(r'(?:図|Figure|Fig\.?)\s*[\d\-\.]+[\.:]?\s*(.+?)(?:\n|$)', re.IGNORECASE)

    # 키워드 기반 콘텐츠 유형 매핑
    CONTENT_TYPE_KEYWORDS = {
        ContentType.DEFINITION: ['概要', 'overview', '紹介', 'introduction', 'とは'],
        ContentType.CONFIGURATION: ['設定', 'config', '構成', '環境', 'conf'],
        ContentType.COMMAND: ['コマンド', 'command', 'ツール', 'tool', 'mgr'],
        ContentType.PROCEDURE: ['手順', 'procedure', '方法', '作成', '実行'],
        ContentType.ERROR_MESSAGE: ['エラー', 'error', 'メッセージ'],
        ContentType.LOG: ['ログ', 'log', '記録'],
        ContentType.API: ['API', 'サービス', 'service', 'svr']
    }

    def __init__(self, extract_images: bool = False, image_output_dir: Optional[str] = None):
        self.sections: List[DocumentSection] = []
        self.document_metadata: Dict[str, Any] = {}
        self.all_tables: List[TableData] = []
        self.all_images: List[ImageData] = []
        self.extract_images = extract_images
        self.image_output_dir = Path(image_output_dir) if image_output_dir else None

        if self.image_output_dir:
            self.image_output_dir.mkdir(parents=True, exist_ok=True)

    def parse_pdf(self, pdf_path: str) -> List[DocumentSection]:
        """PDF 파일 파싱 (표와 이미지 포함)"""
        if not HAS_PYMUPDF:
            raise ImportError(
                "PDF 파싱을 위해 PyMuPDF가 필요합니다.\n"
                "설치: pip install PyMuPDF"
            )

        doc = fitz.open(pdf_path)

        # 문서 메타데이터 추출
        self._extract_document_metadata(doc)

        # 페이지별 처리
        full_text = ""
        page_tables: Dict[int, List[TableData]] = {}
        page_images: Dict[int, List[ImageData]] = {}

        for page_num, page in enumerate(doc, 1):
            # 텍스트 추출
            page_text = page.get_text()
            full_text += f"\n[PAGE:{page_num}]\n{page_text}"

            # 표 추출
            tables = self._extract_tables_from_page(page, page_num)
            if tables:
                page_tables[page_num] = tables
                self.all_tables.extend(tables)

            # 이미지 추출
            images = self._extract_images_from_page(doc, page, page_num)
            if images:
                page_images[page_num] = images
                self.all_images.extend(images)

        doc.close()

        # 텍스트 파싱하여 섹션 추출
        sections = self._parse_text(full_text)

        # 섹션에 표와 이미지 연결
        self._associate_tables_and_images(sections, page_tables, page_images)

        self.sections = sections
        return sections

    def _extract_tables_from_page(self, page, page_num: int) -> List[TableData]:
        """페이지에서 표 추출"""
        tables = []

        # PyMuPDF 1.23.0+ 에서는 find_tables() 사용
        if PYMUPDF_VERSION >= (1, 23):
            try:
                tab_finder = page.find_tables()
                for idx, tab in enumerate(tab_finder.tables):
                    # 표 데이터 추출
                    table_data = tab.extract()

                    if not table_data or len(table_data) < 2:
                        continue

                    # 헤더와 데이터 분리
                    headers = [str(cell) if cell else "" for cell in table_data[0]]
                    rows = [[str(cell) if cell else "" for cell in row] for row in table_data[1:]]

                    # 캡션 찾기 (표 위의 텍스트에서)
                    caption = self._find_table_caption(page, tab.bbox, idx)

                    table = TableData(
                        headers=headers,
                        rows=rows,
                        caption=caption,
                        page_number=page_num
                    )
                    tables.append(table)
            except Exception as e:
                # find_tables가 실패하면 폴백 방식 사용
                tables = self._extract_tables_fallback(page, page_num)
        else:
            # 구버전 PyMuPDF용 폴백
            tables = self._extract_tables_fallback(page, page_num)

        return tables

    def _extract_tables_fallback(self, page, page_num: int) -> List[TableData]:
        """표 추출 폴백 방식 (텍스트 기반)"""
        tables = []
        text = page.get_text()

        # 간단한 표 패턴 감지 (탭이나 여러 공백으로 구분된 행)
        lines = text.split('\n')
        table_rows = []

        for line in lines:
            # 탭이나 2개 이상의 공백으로 구분된 셀 찾기
            cells = re.split(r'\t|  +', line.strip())
            if len(cells) >= 2:
                table_rows.append(cells)
            elif table_rows and len(table_rows) >= 3:
                # 표 종료, 저장
                table = TableData(
                    headers=table_rows[0],
                    rows=table_rows[1:],
                    caption="",
                    page_number=page_num
                )
                tables.append(table)
                table_rows = []
            else:
                table_rows = []

        # 마지막 표 처리
        if len(table_rows) >= 3:
            table = TableData(
                headers=table_rows[0],
                rows=table_rows[1:],
                caption="",
                page_number=page_num
            )
            tables.append(table)

        return tables

    def _find_table_caption(self, page, bbox, table_index: int) -> str:
        """표 캡션 찾기"""
        # 표 위쪽 영역에서 캡션 텍스트 찾기
        caption_rect = fitz.Rect(bbox[0], max(0, bbox[1] - 50), bbox[2], bbox[1])
        caption_text = page.get_text("text", clip=caption_rect).strip()

        # 캡션 패턴 매칭
        match = self.TABLE_CAPTION_PATTERN.search(caption_text)
        if match:
            return match.group(1).strip()

        # 패턴이 없으면 마지막 줄 사용
        lines = caption_text.split('\n')
        if lines:
            return lines[-1].strip()[:100]  # 최대 100자

        return f"Table {table_index + 1}"

    def _extract_images_from_page(self, doc, page, page_num: int) -> List[ImageData]:
        """페이지에서 이미지 추출"""
        images = []
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            xref = img_info[0]

            try:
                # 이미지 정보 추출
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)

                # 너무 작은 이미지 무시 (아이콘 등)
                if width < 50 or height < 50:
                    continue

                # 캡션 찾기
                caption = self._find_image_caption(page, img_index)

                # 주변 텍스트 추출
                surrounding_text = self._get_surrounding_text(page, xref)

                image_data = ImageData(
                    image_index=img_index,
                    page_number=page_num,
                    width=width,
                    height=height,
                    image_type=image_ext,
                    caption=caption,
                    surrounding_text=surrounding_text
                )

                # 이미지 저장 또는 base64 인코딩
                if self.extract_images:
                    if self.image_output_dir:
                        # 파일로 저장
                        img_filename = f"page{page_num}_img{img_index}.{image_ext}"
                        img_path = self.image_output_dir / img_filename
                        with open(img_path, 'wb') as f:
                            f.write(image_bytes)
                    else:
                        # base64 인코딩
                        image_data.base64_data = base64.b64encode(image_bytes).decode('utf-8')

                images.append(image_data)

            except Exception as e:
                # 이미지 추출 실패 시 무시
                continue

        return images

    def _find_image_caption(self, page, img_index: int) -> str:
        """이미지 캡션 찾기"""
        text = page.get_text()

        # 그림/Figure 캡션 패턴 찾기
        matches = list(self.FIGURE_CAPTION_PATTERN.finditer(text))
        if img_index < len(matches):
            return matches[img_index].group(1).strip()

        return f"Figure {img_index + 1}"

    def _get_surrounding_text(self, page, xref: int) -> str:
        """이미지 주변 텍스트 추출"""
        # 이미지 위치 찾기
        for img_info in page.get_images(full=True):
            if img_info[0] == xref:
                # 이미지 영역 주변 텍스트
                text = page.get_text()
                # 처음 200자 반환
                return text[:200].strip()
        return ""

    def _extract_document_metadata(self, doc) -> Dict[str, Any]:
        """문서 메타데이터 추출"""
        metadata = {
            "product": "OpenFrame",
            "version": "7.1",
            "language": "ja",
            "page_count": doc.page_count,
            "extracted_at": datetime.now().isoformat()
        }

        # PDF 메타데이터
        pdf_metadata = doc.metadata
        if pdf_metadata:
            if pdf_metadata.get("title"):
                metadata["title"] = pdf_metadata["title"]
            if pdf_metadata.get("author"):
                metadata["author"] = pdf_metadata["author"]
            if pdf_metadata.get("creationDate"):
                metadata["creation_date"] = pdf_metadata["creationDate"]

        # 첫 페이지에서 버전 정보 추출
        if doc.page_count > 0:
            first_page_text = doc[0].get_text()

            # 버전 정보 추출
            version_match = re.search(r'OpenFrame[/\s]*(Base|Batch|OSC|OSI|GW|HiDB|TACF)?\s*(\d+\.\d+)', first_page_text)
            if version_match:
                if version_match.group(1):
                    metadata["product"] = f"OpenFrame/{version_match.group(1)}"
                metadata["version"] = version_match.group(2)

            # 가이드 버전 추출
            guide_version_match = re.search(r'v(\d+\.\d+\.\d+)', first_page_text)
            if guide_version_match:
                metadata["guide_version"] = f"v{guide_version_match.group(1)}"

        self.document_metadata = metadata
        return metadata

    def _parse_text(self, text: str) -> List[DocumentSection]:
        """텍스트 파싱하여 섹션 추출"""
        sections = []

        # 챕터 및 부록 매칭
        chapter_matches = [(m, 'chapter') for m in self.CHAPTER_PATTERN.finditer(text)]
        appendix_matches = [(m, 'appendix') for m in self.APPENDIX_PATTERN.finditer(text)]

        all_matches = chapter_matches + appendix_matches
        all_matches.sort(key=lambda x: x[0].start())

        for i, (match, match_type) in enumerate(all_matches):
            start_pos = match.start()
            end_pos = all_matches[i + 1][0].start() if i + 1 < len(all_matches) else len(text)

            chapter_text = text[start_pos:end_pos]

            if match_type == 'chapter':
                chapter_num = match.group(1)
                chapter_title = match.group(2).strip()
                section_number = f"第{chapter_num}章"
            else:
                chapter_num = match.group(1)
                chapter_title = match.group(2).strip()
                section_number = f"付録{chapter_num}"

            # 페이지 번호 추출
            page_match = re.search(r'\[PAGE:(\d+)\]', chapter_text)
            page_num = int(page_match.group(1)) if page_match else None

            # 챕터 섹션 생성
            chapter_section = DocumentSection(
                level=1,
                number=section_number,
                title=chapter_title,
                content=self._clean_content(chapter_text),
                content_type=ContentType.CHAPTER,
                code_blocks=self._extract_code_blocks(chapter_text),
                page_number=page_num
            )
            sections.append(chapter_section)

            # 하위 섹션 파싱
            sub_sections = self._parse_subsections(chapter_text, section_number)
            sections.extend(sub_sections)

        return sections

    def _parse_subsections(self, chapter_text: str, parent_chapter: str) -> List[DocumentSection]:
        """하위 섹션 파싱"""
        sections = []

        # 섹션 매칭 (2레벨)
        section_matches = list(self.SECTION_PATTERN.finditer(chapter_text))

        for i, match in enumerate(section_matches):
            start_pos = match.start()
            end_pos = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(chapter_text)

            section_text = chapter_text[start_pos:end_pos]
            section_num = match.group(1).rstrip('.')
            section_title = match.group(2).strip()

            # 콘텐츠 유형 결정
            content_type = self._determine_content_type(section_title, section_text)

            # 페이지 번호 추출
            page_match = re.search(r'\[PAGE:(\d+)\]', section_text)
            page_num = int(page_match.group(1)) if page_match else None

            section = DocumentSection(
                level=2,
                number=section_num,
                title=section_title,
                content=self._clean_content(section_text),
                content_type=content_type,
                parent_section=parent_chapter,
                code_blocks=self._extract_code_blocks(section_text),
                page_number=page_num
            )
            sections.append(section)

            # 서브섹션 파싱 (3레벨)
            subsection_matches = list(self.SUBSECTION_PATTERN.finditer(section_text))
            for j, sub_match in enumerate(subsection_matches):
                sub_start = sub_match.start()
                sub_end = subsection_matches[j + 1].start() if j + 1 < len(subsection_matches) else len(section_text)

                subsection_text = section_text[sub_start:sub_end]
                subsection_num = sub_match.group(1).rstrip('.')
                subsection_title = sub_match.group(2).strip()

                subsection = DocumentSection(
                    level=3,
                    number=subsection_num,
                    title=subsection_title,
                    content=self._clean_content(subsection_text),
                    content_type=self._determine_content_type(subsection_title, subsection_text),
                    parent_section=section_num,
                    code_blocks=self._extract_code_blocks(subsection_text)
                )
                sections.append(subsection)

        return sections

    def _associate_tables_and_images(self, sections: List[DocumentSection],
                                      page_tables: Dict[int, List[TableData]],
                                      page_images: Dict[int, List[ImageData]]):
        """섹션에 표와 이미지 연결"""
        for section in sections:
            if section.page_number:
                # 해당 페이지의 표 연결
                if section.page_number in page_tables:
                    section.tables = page_tables[section.page_number]

                # 해당 페이지의 이미지 연결
                if section.page_number in page_images:
                    section.images = page_images[section.page_number]

    def _determine_content_type(self, title: str, content: str) -> ContentType:
        """콘텐츠 유형 결정"""
        title_content = (title + " " + content[:500]).lower()

        for content_type, keywords in self.CONTENT_TYPE_KEYWORDS.items():
            if any(kw.lower() in title_content for kw in keywords):
                return content_type

        # 코드 패턴 기반 판단
        if self.CODE_BLOCK_PATTERN.search(content):
            return ContentType.CODE_EXAMPLE
        if self.CONFIG_PATTERN.search(content):
            return ContentType.CONFIGURATION
        if self.SQL_PATTERN.search(content):
            return ContentType.PROCEDURE

        return ContentType.SECTION

    def _extract_code_blocks(self, text: str) -> List[str]:
        """코드 블록 추출"""
        code_blocks = []

        # $ 로 시작하는 커맨드라인
        cmd_matches = re.findall(r'^\$\s+.+$', text, re.MULTILINE)
        code_blocks.extend(cmd_matches)

        # 설정 블록 (KEY=VALUE 형식)
        config_matches = re.findall(r'^[A-Z_]+\s*=\s*.+$', text, re.MULTILINE)
        code_blocks.extend(config_matches)

        # SQL 구문
        sql_matches = re.findall(r'SQL>\s*.+$', text, re.MULTILINE)
        code_blocks.extend(sql_matches)

        # 섹션 설정 블록 [SECTION_NAME]
        section_config = re.findall(r'^\[[\w_]+\][\s\S]*?(?=\n\[|\Z)', text, re.MULTILINE)
        for config in section_config[:3]:
            if len(config) < 500:
                code_blocks.append(config.strip())

        return list(set(code_blocks))

    def _clean_content(self, text: str) -> str:
        """콘텐츠 정제"""
        # 페이지 번호 및 헤더/푸터 제거
        text = re.sub(r'\d+\s+OpenFrame\s+Base.*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^OpenFrame\s+\d+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[PAGE:\d+\]', '', text)

        # 연속 공백/개행 정리
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)

        return text.strip()

    def get_statistics(self) -> Dict[str, Any]:
        """파싱 통계 반환"""
        return {
            "total_sections": len(self.sections),
            "total_tables": len(self.all_tables),
            "total_images": len(self.all_images),
            "sections_with_tables": sum(1 for s in self.sections if s.tables),
            "sections_with_images": sum(1 for s in self.sections if s.images),
            "sections_with_code": sum(1 for s in self.sections if s.code_blocks),
            "document_metadata": self.document_metadata
        }


class QLoRADataGeneratorV2:
    """QLoRA 학습 데이터 생성기 v2 - 표와 이미지 지원"""

    # 질문 템플릿 (일본어)
    QUESTION_TEMPLATES_JA = {
        ContentType.DEFINITION: [
            "{title}とは何ですか？",
            "{title}について説明してください。",
            "{title}の概要を教えてください。",
            "{title}の目的と役割は何ですか？"
        ],
        ContentType.CONFIGURATION: [
            "{title}の設定方法を教えてください。",
            "{title}はどのように設定しますか？",
            "{title}の設定例を示してください。",
            "{title}の設定パラメータについて説明してください。"
        ],
        ContentType.COMMAND: [
            "{title}コマンドの使い方を教えてください。",
            "{title}の実行方法を説明してください。",
            "{title}のオプションについて教えてください。",
            "{title}の使用例を示してください。"
        ],
        ContentType.PROCEDURE: [
            "{title}の手順を教えてください。",
            "{title}を実行する方法は？",
            "{title}のステップを詳しく説明してください。",
            "{title}はどのように行いますか？"
        ],
        ContentType.CODE_EXAMPLE: [
            "{title}のコード例を示してください。",
            "{title}の実装例を教えてください。",
            "{title}のサンプルを見せてください。"
        ],
        ContentType.TABLE: [
            "{title}の一覧を表形式で示してください。",
            "{title}の詳細を表にまとめてください。",
            "{title}のパラメータ一覧を教えてください。"
        ],
        ContentType.LOG: [
            "{title}について説明してください。",
            "{title}の形式を教えてください。",
            "{title}はどこに保存されますか？"
        ],
        ContentType.API: [
            "{title}の機能について説明してください。",
            "{title}サーバーの役割は何ですか？",
            "{title}の設定方法を教えてください。"
        ],
        ContentType.IMAGE: [
            "{title}の構成図について説明してください。",
            "{title}のアーキテクチャを図で示してください。"
        ],
        ContentType.CHAPTER: [
            "{title}について説明してください。",
            "{title}の内容を要約してください。",
            "{title}で扱うトピックは何ですか？"
        ],
        ContentType.SECTION: [
            "{title}について詳しく教えてください。",
            "{title}とは何ですか？"
        ]
    }

    # 표 관련 질문 템플릿
    TABLE_QUESTION_TEMPLATES_JA = [
        "{caption}の各項目について説明してください。",
        "{caption}の内容を教えてください。",
        "{caption}に含まれるパラメータは何ですか？"
    ]

    # 이미지 관련 질문 템플릿
    IMAGE_QUESTION_TEMPLATES_JA = [
        "{caption}について説明してください。",
        "{caption}の構成要素を教えてください。",
        "{caption}が示している内容は何ですか？"
    ]

    def __init__(self, parser: OpenFrameManualParserV2):
        self.parser = parser
        self.training_data: List[TrainingExample] = []

    def generate_training_data(self,
                               include_metadata: bool = True,
                               language: str = "ja",
                               min_content_length: int = 50,
                               max_templates_per_section: int = 3,
                               include_tables: bool = True,
                               include_images: bool = True) -> List[TrainingExample]:
        """학습 데이터 생성"""
        training_data = []

        templates = self.QUESTION_TEMPLATES_JA

        for section in self.parser.sections:
            # 콘텐츠 길이 체크
            if len(section.content) < min_content_length:
                continue

            # 기본 섹션 Q&A 생성
            section_examples = self._generate_section_examples(
                section, templates, language, include_metadata, max_templates_per_section
            )
            training_data.extend(section_examples)

            # 코드 블록 Q&A 생성
            if section.code_blocks:
                code_examples = self._generate_code_examples(section, language, include_metadata)
                training_data.extend(code_examples)

            # 표 Q&A 생성
            if include_tables and section.tables:
                table_examples = self._generate_table_examples(section, language, include_metadata)
                training_data.extend(table_examples)

            # 이미지 Q&A 생성
            if include_images and section.images:
                image_examples = self._generate_image_examples(section, language, include_metadata)
                training_data.extend(image_examples)

        self.training_data = training_data
        return training_data

    def _generate_section_examples(self, section: DocumentSection, templates: Dict,
                                   language: str, include_metadata: bool,
                                   max_templates: int) -> List[TrainingExample]:
        """섹션 기본 Q&A 생성"""
        examples = []

        section_templates = templates.get(
            section.content_type,
            templates.get(ContentType.SECTION, ["{title}について説明してください。"])
        )

        selected_templates = section_templates[:max_templates]

        for template in selected_templates:
            instruction = template.format(title=section.title)

            metadata = {}
            if include_metadata:
                metadata = {
                    "source": "OpenFrame Manual",
                    "version": self.parser.document_metadata.get("version", "7.1"),
                    "section_number": section.number,
                    "section_level": section.level,
                    "content_type": section.content_type.value,
                    "parent_section": section.parent_section,
                    "has_code_examples": len(section.code_blocks) > 0,
                    "has_tables": len(section.tables) > 0,
                    "has_images": len(section.images) > 0,
                    "language": language
                }

            output = self._generate_response(section, language)

            example = TrainingExample(
                instruction=instruction,
                input="",
                output=output,
                metadata=metadata
            )
            examples.append(example)

        return examples

    def _generate_response(self, section: DocumentSection, language: str = "ja") -> str:
        """응답 텍스트 생성"""
        response_parts = []

        # 기본 설명
        response_parts.append(section.content)

        # 코드 블록 포함
        if section.code_blocks:
            label = "使用例:" if language == "ja" else "Examples:"
            response_parts.append(f"\n\n{label}")
            for code in section.code_blocks[:3]:
                response_parts.append(f"```\n{code}\n```")

        # 표 포함
        if section.tables:
            for table in section.tables[:2]:
                md_table = table.to_markdown()
                if md_table:
                    response_parts.append(f"\n\n{md_table}")

        return "\n".join(response_parts)

    def _generate_code_examples(self, section: DocumentSection,
                                language: str,
                                include_metadata: bool) -> List[TrainingExample]:
        """코드 예제 Q&A 생성"""
        examples = []

        if not section.code_blocks:
            return examples

        if language == "ja":
            instruction = f"{section.title}のコマンド例・設定例を教えてください。"
        else:
            instruction = f"Show me command and configuration examples for {section.title}."

        code_output = "\n".join([f"```\n{code}\n```" for code in section.code_blocks])

        metadata = {}
        if include_metadata:
            metadata = {
                "source": "OpenFrame Manual",
                "section_number": section.number,
                "content_type": "code_example",
                "language": language
            }

        example = TrainingExample(
            instruction=instruction,
            input="",
            output=code_output,
            metadata=metadata
        )
        examples.append(example)

        return examples

    def _generate_table_examples(self, section: DocumentSection,
                                 language: str,
                                 include_metadata: bool) -> List[TrainingExample]:
        """표 기반 Q&A 생성"""
        examples = []

        for table in section.tables:
            md_table = table.to_markdown()
            if not md_table:
                continue

            caption = table.caption or section.title

            # 표 내용 설명 질문
            if language == "ja":
                instruction = f"{caption}の内容を表形式で教えてください。"
            else:
                instruction = f"Show me the {caption} in table format."

            metadata = {}
            if include_metadata:
                metadata = {
                    "source": "OpenFrame Manual",
                    "section_number": section.number,
                    "content_type": "table",
                    "table_caption": caption,
                    "table_rows": len(table.rows),
                    "page_number": table.page_number,
                    "language": language
                }

            example = TrainingExample(
                instruction=instruction,
                input="",
                output=md_table,
                metadata=metadata
            )
            examples.append(example)

            # 표의 각 행에 대한 Q&A (헤더가 있는 경우)
            if table.headers and len(table.headers) >= 2 and len(table.rows) <= 20:
                for row in table.rows[:10]:  # 최대 10행
                    if len(row) >= 2 and row[0].strip():
                        key = row[0].strip()
                        value = " | ".join(str(c).strip() for c in row[1:] if c)

                        if language == "ja":
                            row_instruction = f"{caption}における{key}について説明してください。"
                        else:
                            row_instruction = f"Explain {key} in {caption}."

                        row_example = TrainingExample(
                            instruction=row_instruction,
                            input="",
                            output=value,
                            metadata={
                                "source": "OpenFrame Manual",
                                "content_type": "table_row",
                                "table_caption": caption,
                                "row_key": key
                            } if include_metadata else {}
                        )
                        examples.append(row_example)

        return examples

    def _generate_image_examples(self, section: DocumentSection,
                                 language: str,
                                 include_metadata: bool) -> List[TrainingExample]:
        """이미지 기반 Q&A 생성"""
        examples = []

        for image in section.images:
            caption = image.caption or f"Figure in {section.title}"

            # 이미지 설명 질문
            if language == "ja":
                instruction = f"{caption}について説明してください。"
            else:
                instruction = f"Describe {caption}."

            # 이미지 설명 (주변 텍스트 + 섹션 내용)
            output_parts = []
            if image.surrounding_text:
                output_parts.append(image.surrounding_text)
            output_parts.append(f"\nこの図は{section.title}に関連しています。")
            output_parts.append(section.content[:500])  # 섹션 내용 일부

            metadata = {}
            if include_metadata:
                metadata = {
                    "source": "OpenFrame Manual",
                    "section_number": section.number,
                    "content_type": "image",
                    "image_caption": caption,
                    "image_size": f"{image.width}x{image.height}",
                    "page_number": image.page_number,
                    "language": language
                }

            example = TrainingExample(
                instruction=instruction,
                input="",
                output="\n".join(output_parts),
                metadata=metadata
            )
            examples.append(example)

        return examples

    def generate_qa_pairs(self, language: str = "ja") -> List[TrainingExample]:
        """고급 Q&A 쌍 생성"""
        qa_pairs = []

        # 챕터별 요약 질문
        for section in self.parser.sections:
            if section.level == 1:
                child_sections = [s for s in self.parser.sections
                                 if s.parent_section == section.number]

                if child_sections:
                    topics = [s.title for s in child_sections[:5]]

                    if language == "ja":
                        instruction = f"{section.title}で扱うトピックは何ですか？"
                        output_prefix = f"{section.title}では以下のトピックを扱います："
                    else:
                        instruction = f"What topics are covered in {section.title}?"
                        output_prefix = f"{section.title} covers the following topics:"

                    qa = TrainingExample(
                        instruction=instruction,
                        input="",
                        output=output_prefix + "\n" + "\n".join([f"- {t}" for t in topics]),
                        metadata={
                            "source": "OpenFrame Manual",
                            "question_type": "summary",
                            "section_number": section.number
                        }
                    )
                    qa_pairs.append(qa)

        # 전체 표 목록 Q&A
        if self.parser.all_tables:
            if language == "ja":
                instruction = "このマニュアルに含まれる表の一覧を教えてください。"
                output = "このマニュアルには以下の表が含まれています：\n"
            else:
                instruction = "List all tables in this manual."
                output = "This manual contains the following tables:\n"

            for i, table in enumerate(self.parser.all_tables[:20], 1):
                output += f"{i}. {table.caption} (ページ {table.page_number})\n"

            qa = TrainingExample(
                instruction=instruction,
                input="",
                output=output,
                metadata={"question_type": "table_list", "total_tables": len(self.parser.all_tables)}
            )
            qa_pairs.append(qa)

        return qa_pairs

    def export_jsonl(self, output_path: str, format_type: str = "alpaca"):
        """JSONL 형식으로 내보내기"""
        with open(output_path, 'w', encoding='utf-8') as f:
            for example in self.training_data:
                if format_type == "alpaca":
                    data = example.to_alpaca_format()
                elif format_type == "sharegpt":
                    data = example.to_sharegpt_format()
                elif format_type == "openai":
                    data = example.to_openai_format()
                else:
                    data = example.to_dict()

                f.write(json.dumps(data, ensure_ascii=False) + '\n')

        print(f"Exported {len(self.training_data)} examples to {output_path}")

    def export_json(self, output_path: str, format_type: str = "alpaca"):
        """JSON 배열 형식으로 내보내기"""
        data_list = []

        for example in self.training_data:
            if format_type == "alpaca":
                data_list.append(example.to_alpaca_format())
            elif format_type == "sharegpt":
                data_list.append(example.to_sharegpt_format())
            elif format_type == "openai":
                data_list.append(example.to_openai_format())
            else:
                data_list.append(example.to_dict())

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)

        print(f"Exported {len(self.training_data)} examples to {output_path}")

    def export_tables_json(self, output_path: str):
        """표 데이터만 JSON으로 내보내기"""
        tables_data = [table.to_dict() for table in self.parser.all_tables]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(tables_data, f, ensure_ascii=False, indent=2)

        print(f"Exported {len(tables_data)} tables to {output_path}")

    def export_images_json(self, output_path: str):
        """이미지 메타데이터 JSON으로 내보내기"""
        images_data = [image.to_dict() for image in self.parser.all_images]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(images_data, f, ensure_ascii=False, indent=2)

        print(f"Exported {len(images_data)} image metadata to {output_path}")

    def get_statistics(self) -> Dict[str, Any]:
        """통계 정보 반환"""
        stats = {
            "total_examples": len(self.training_data),
            "by_content_type": {},
            "avg_instruction_length": 0,
            "avg_output_length": 0,
            "total_sections": len(self.parser.sections),
            "total_tables": len(self.parser.all_tables),
            "total_images": len(self.parser.all_images),
            "table_examples": sum(1 for e in self.training_data
                                 if e.metadata.get("content_type") in ["table", "table_row"]),
            "image_examples": sum(1 for e in self.training_data
                                 if e.metadata.get("content_type") == "image"),
            "document_metadata": self.parser.document_metadata
        }

        # 콘텐츠 유형별 통계
        for example in self.training_data:
            content_type = example.metadata.get("content_type", "unknown")
            stats["by_content_type"][content_type] = \
                stats["by_content_type"].get(content_type, 0) + 1

        # 평균 길이 계산
        if self.training_data:
            stats["avg_instruction_length"] = round(sum(
                len(e.instruction) for e in self.training_data
            ) / len(self.training_data), 1)
            stats["avg_output_length"] = round(sum(
                len(e.output) for e in self.training_data
            ) / len(self.training_data), 1)

        return stats


def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(
        description='OpenFrame 매뉴얼에서 QLoRA 학습 데이터 추출 (v2.0 - 표/이미지 지원)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 샘플 데이터 생성
  python %(prog)s --sample --output training_data.jsonl

  # PDF에서 추출 (표/이미지 포함)
  python %(prog)s --input manual.pdf --output data.jsonl --format alpaca

  # 이미지 추출 및 저장
  python %(prog)s --input manual.pdf --extract-images --image-dir ./images

  # 표 데이터만 추출
  python %(prog)s --input manual.pdf --export-tables tables.json
        """
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        help='입력 PDF 파일 경로'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='openframe_training_data_v2.jsonl',
        help='출력 파일 경로 (기본: openframe_training_data_v2.jsonl)'
    )
    parser.add_argument(
        '--format', '-f',
        choices=['alpaca', 'sharegpt', 'openai', 'full'],
        default='alpaca',
        help='출력 형식 (기본: alpaca)'
    )
    parser.add_argument(
        '--language', '-l',
        choices=['ja', 'en'],
        default='ja',
        help='질문 언어 (기본: ja)'
    )
    parser.add_argument(
        '--sample',
        action='store_true',
        help='샘플 데이터 생성 모드'
    )
    parser.add_argument(
        '--extract-images',
        action='store_true',
        help='이미지 추출 활성화'
    )
    parser.add_argument(
        '--image-dir',
        type=str,
        help='이미지 저장 디렉토리'
    )
    parser.add_argument(
        '--export-tables',
        type=str,
        help='표 데이터 JSON 내보내기 경로'
    )
    parser.add_argument(
        '--export-images',
        type=str,
        help='이미지 메타데이터 JSON 내보내기 경로'
    )
    parser.add_argument(
        '--no-tables',
        action='store_true',
        help='표 기반 Q&A 비활성화'
    )
    parser.add_argument(
        '--no-images',
        action='store_true',
        help='이미지 기반 Q&A 비활성화'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='통계 정보만 출력'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("OpenFrame Manual QLoRA Training Data Extractor v2.0")
    print("(표 및 이미지 추출 지원)")
    print("=" * 60)

    if args.sample or not args.input:
        print("\n[모드] 샘플 데이터 생성 (v1 호환)")
        print("PDF 파일을 지정하여 v2 기능을 사용하세요.")
        print("예: python openframe_qlora_full_extractor_v2.py --input manual.pdf")
        return

    # PDF 파싱 모드
    print(f"\n[모드] PDF 파싱 (v2)")
    print(f"  입력 파일: {args.input}")
    print(f"  이미지 추출: {'활성화' if args.extract_images else '비활성화'}")

    if not Path(args.input).exists():
        print(f"Error: 파일을 찾을 수 없습니다: {args.input}")
        return

    # 파서 초기화
    manual_parser = OpenFrameManualParserV2(
        extract_images=args.extract_images,
        image_output_dir=args.image_dir
    )

    try:
        print("\n[1/4] PDF 파싱 중...")
        sections = manual_parser.parse_pdf(args.input)
        parser_stats = manual_parser.get_statistics()
        print(f"      → 섹션: {parser_stats['total_sections']}개")
        print(f"      → 표: {parser_stats['total_tables']}개")
        print(f"      → 이미지: {parser_stats['total_images']}개")

    except ImportError as e:
        print(f"Error: {e}")
        return

    # 학습 데이터 생성
    print("\n[2/4] 학습 데이터 생성 중...")
    generator = QLoRADataGeneratorV2(manual_parser)
    training_data = generator.generate_training_data(
        language=args.language,
        include_tables=not args.no_tables,
        include_images=not args.no_images
    )
    print(f"      → 기본 학습 데이터: {len(training_data)}개")

    # Q&A 쌍 추가
    print("\n[3/4] Q&A 쌍 생성 중...")
    qa_pairs = generator.generate_qa_pairs(language=args.language)
    generator.training_data.extend(qa_pairs)
    print(f"      → Q&A 쌍: {len(qa_pairs)}개")
    print(f"      → 총 학습 데이터: {len(generator.training_data)}개")

    # 출력
    print("\n[4/4] 파일 저장 중...")
    if args.output.endswith('.json'):
        generator.export_json(args.output, args.format)
    else:
        generator.export_jsonl(args.output, args.format)

    # 표 데이터 내보내기
    if args.export_tables:
        generator.export_tables_json(args.export_tables)

    # 이미지 메타데이터 내보내기
    if args.export_images:
        generator.export_images_json(args.export_images)

    # 통계 출력
    stats = generator.get_statistics()
    print("\n" + "=" * 60)
    print("[통계]")
    print("=" * 60)
    print(f"  총 학습 예제: {stats['total_examples']}개")
    print(f"  총 섹션: {stats['total_sections']}개")
    print(f"  총 표: {stats['total_tables']}개")
    print(f"  총 이미지: {stats['total_images']}개")
    print(f"  표 기반 예제: {stats['table_examples']}개")
    print(f"  이미지 기반 예제: {stats['image_examples']}개")
    print(f"  평균 질문 길이: {stats['avg_instruction_length']}자")
    print(f"  평균 응답 길이: {stats['avg_output_length']}자")

    print("\n[콘텐츠 유형별]")
    for ct, count in sorted(stats['by_content_type'].items()):
        print(f"  • {ct}: {count}개")

    print("\n" + "=" * 60)
    print("완료!")


if __name__ == "__main__":
    main()
