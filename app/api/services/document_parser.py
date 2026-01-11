"""
Document Parser Service
Handles parsing of various document formats: PDF, Word, Excel, PowerPoint, Text, Images
"""
import asyncio
import io
import os
import re
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple, BinaryIO

from ..models.document import (
    DocumentType,
    ProcessingMode,
    SUPPORTED_MIME_TYPES,
    EXTENSION_TO_MIME,
    VLMExtractionResult,
    ImageInfo,
    TableInfo,
)


class ParsedDocument:
    """Represents a parsed document with extracted content."""

    def __init__(
        self,
        document_type: DocumentType,
        filename: str,
        mime_type: str
    ):
        self.document_type = document_type
        self.filename = filename
        self.mime_type = mime_type
        self.text_content: str = ""
        self.pages: List[Dict[str, Any]] = []
        self.tables: List[TableInfo] = []
        self.images: List[ImageInfo] = []
        self.metadata: Dict[str, Any] = {}
        self.chunks: List[Dict[str, Any]] = []
        self.processing_info: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "document_type": self.document_type.value,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "text_content": self.text_content,
            "pages": self.pages,
            "tables": [t.model_dump() for t in self.tables],
            "images": [i.model_dump() for i in self.images],
            "metadata": self.metadata,
            "chunks": self.chunks,
            "processing_info": self.processing_info
        }


class BaseDocumentParser(ABC):
    """Abstract base class for document parsers."""

    @abstractmethod
    async def parse(
        self,
        file_content: bytes,
        filename: str,
        options: Dict[str, Any] = None
    ) -> ParsedDocument:
        """Parse document and extract content."""
        pass

    @abstractmethod
    def supports(self, mime_type: str) -> bool:
        """Check if parser supports the given MIME type."""
        pass


class TextParser(BaseDocumentParser):
    """Parser for plain text files."""

    SUPPORTED_TYPES = [
        "text/plain",
        "text/markdown",
        "text/html",
        "text/csv",
        "application/json"
    ]

    def supports(self, mime_type: str) -> bool:
        return mime_type in self.SUPPORTED_TYPES

    async def parse(
        self,
        file_content: bytes,
        filename: str,
        options: Dict[str, Any] = None
    ) -> ParsedDocument:
        options = options or {}
        encoding = options.get("encoding", "utf-8")

        # Determine document type
        ext = os.path.splitext(filename)[1].lower()
        mime_type = EXTENSION_TO_MIME.get(ext, "text/plain")
        doc_type = SUPPORTED_MIME_TYPES.get(mime_type, DocumentType.TEXT)

        doc = ParsedDocument(doc_type, filename, mime_type)

        try:
            # Try to decode with specified encoding
            text = file_content.decode(encoding)
        except UnicodeDecodeError:
            # Fallback to different encodings
            for enc in ["utf-8", "cp949", "euc-kr", "latin-1"]:
                try:
                    text = file_content.decode(enc)
                    encoding = enc
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = file_content.decode("utf-8", errors="replace")

        doc.text_content = text
        doc.metadata = {
            "encoding": encoding,
            "line_count": len(text.splitlines()),
            "char_count": len(text),
            "word_count": len(text.split())
        }

        # Parse specific formats
        if mime_type == "text/csv":
            doc.tables = await self._parse_csv(text)
        elif mime_type == "application/json":
            doc.metadata["json_parsed"] = True
        elif mime_type == "text/markdown":
            doc.metadata["has_code_blocks"] = "```" in text
            doc.metadata["has_headers"] = bool(re.search(r"^#+\s", text, re.MULTILINE))

        doc.pages = [{"page_number": 1, "content": text}]
        doc.processing_info = {
            "parser": "TextParser",
            "parsed_at": datetime.now(timezone.utc).isoformat()
        }

        return doc

    async def _parse_csv(self, text: str) -> List[TableInfo]:
        """Parse CSV content into table."""
        lines = text.strip().split("\n")
        if not lines:
            return []

        # Simple CSV parsing (in production, use csv module)
        delimiter = "," if "," in lines[0] else "\t"
        rows = [line.split(delimiter) for line in lines]

        if len(rows) < 2:
            return []

        table = TableInfo(
            id=f"table_{uuid.uuid4().hex[:8]}",
            headers=rows[0],
            rows=rows[1:],
            caption="CSV Data",
            markdown=self._rows_to_markdown(rows[0], rows[1:])
        )
        return [table]

    def _rows_to_markdown(self, headers: List[str], rows: List[List[str]]) -> str:
        """Convert table rows to markdown."""
        md = "| " + " | ".join(headers) + " |\n"
        md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
        for row in rows:
            md += "| " + " | ".join(row) + " |\n"
        return md


class PDFParser(BaseDocumentParser):
    """Parser for PDF documents."""

    SUPPORTED_TYPES = ["application/pdf"]

    def supports(self, mime_type: str) -> bool:
        return mime_type in self.SUPPORTED_TYPES

    async def parse(
        self,
        file_content: bytes,
        filename: str,
        options: Dict[str, Any] = None
    ) -> ParsedDocument:
        """
        Parse PDF document.

        In production, this would use libraries like:
        - PyMuPDF (fitz)
        - pdfplumber
        - PyPDF2
        - pdf2image for page rendering
        """
        options = options or {}
        doc = ParsedDocument(DocumentType.PDF, filename, "application/pdf")

        # Mock PDF parsing (in production, use actual PDF library)
        doc.text_content = await self._mock_pdf_extraction(file_content)

        # Extract metadata
        doc.metadata = {
            "pages": 10,  # Mock page count
            "title": filename.replace(".pdf", ""),
            "author": "Unknown",
            "created_date": datetime.now(timezone.utc).isoformat(),
            "pdf_version": "1.7"
        }

        # Mock pages
        doc.pages = [
            {"page_number": i + 1, "content": f"Page {i + 1} content..."}
            for i in range(doc.metadata["pages"])
        ]

        # Mock table extraction
        if options.get("extract_tables", True):
            doc.tables = await self._mock_table_extraction()

        # Mock image extraction
        if options.get("extract_images", True):
            doc.images = await self._mock_image_extraction()

        doc.processing_info = {
            "parser": "PDFParser",
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "options": options
        }

        return doc

    async def _mock_pdf_extraction(self, content: bytes) -> str:
        """Mock PDF text extraction."""
        await asyncio.sleep(0.5)
        return """PDF 문서 내용

1. 개요
본 문서는 시스템 설계 및 구현에 대한 내용을 담고 있습니다.

2. 시스템 아키텍처
- 프론트엔드: React + TypeScript
- 백엔드: FastAPI + Python
- 데이터베이스: Neo4j, PostgreSQL

3. 주요 기능
3.1 문서 관리
문서 업로드, 분석, 검색 기능을 제공합니다.

3.2 AI 기반 질의응답
RAG 기술을 활용한 지능형 Q&A 시스템입니다.

4. 결론
본 시스템은 효율적인 지식 관리를 위한 종합 솔루션입니다."""

    async def _mock_table_extraction(self) -> List[TableInfo]:
        """Mock table extraction from PDF."""
        return [
            TableInfo(
                id=f"table_{uuid.uuid4().hex[:8]}",
                page_number=3,
                headers=["구성요소", "기술", "버전"],
                rows=[
                    ["프론트엔드", "React", "18.2"],
                    ["백엔드", "FastAPI", "0.100"],
                    ["데이터베이스", "Neo4j", "5.0"]
                ],
                caption="시스템 기술 스택",
                markdown=""
            )
        ]

    async def _mock_image_extraction(self) -> List[ImageInfo]:
        """Mock image extraction from PDF."""
        return [
            ImageInfo(
                id=f"img_{uuid.uuid4().hex[:8]}",
                page_number=2,
                position={"x": 100, "y": 200, "width": 400, "height": 300},
                description="시스템 아키텍처 다이어그램",
                alt_text="System Architecture Diagram"
            )
        ]


class WordParser(BaseDocumentParser):
    """Parser for Microsoft Word documents."""

    SUPPORTED_TYPES = [
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]

    def supports(self, mime_type: str) -> bool:
        return mime_type in self.SUPPORTED_TYPES

    async def parse(
        self,
        file_content: bytes,
        filename: str,
        options: Dict[str, Any] = None
    ) -> ParsedDocument:
        """
        Parse Word document.

        In production, this would use libraries like:
        - python-docx
        - mammoth
        - antiword
        """
        options = options or {}
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if filename.endswith(".doc"):
            mime_type = "application/msword"

        doc = ParsedDocument(DocumentType.WORD, filename, mime_type)

        # Mock Word parsing
        doc.text_content = await self._mock_word_extraction(file_content, filename)

        doc.metadata = {
            "title": filename.replace(".docx", "").replace(".doc", ""),
            "author": "Unknown",
            "created_date": datetime.now(timezone.utc).isoformat(),
            "word_count": len(doc.text_content.split()),
            "paragraph_count": doc.text_content.count("\n\n") + 1
        }

        doc.pages = [{"page_number": 1, "content": doc.text_content}]

        # Extract tables if present
        if options.get("extract_tables", True):
            doc.tables = await self._mock_table_extraction()

        # Extract images if present
        if options.get("extract_images", True):
            doc.images = await self._mock_image_extraction()

        doc.processing_info = {
            "parser": "WordParser",
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "is_docx": filename.endswith(".docx")
        }

        return doc

    async def _mock_word_extraction(self, content: bytes, filename: str) -> str:
        """Mock Word document text extraction."""
        await asyncio.sleep(0.3)
        return f"""Microsoft Word 문서: {filename}

1. 서론
이 문서는 Word 형식으로 작성된 문서입니다.

2. 본문
- 다양한 서식을 지원합니다
- 표와 이미지를 포함할 수 있습니다
- 머리글/바닥글 기능을 제공합니다

3. 결론
Word 문서가 성공적으로 파싱되었습니다."""

    async def _mock_table_extraction(self) -> List[TableInfo]:
        """Mock table extraction from Word."""
        return [
            TableInfo(
                id=f"table_{uuid.uuid4().hex[:8]}",
                headers=["항목", "설명"],
                rows=[
                    ["제목", "Word 문서 예시"],
                    ["형식", "DOCX"],
                    ["상태", "정상"]
                ],
                caption="문서 정보",
                markdown=""
            )
        ]

    async def _mock_image_extraction(self) -> List[ImageInfo]:
        """Mock image extraction from Word."""
        return []


class ExcelParser(BaseDocumentParser):
    """Parser for Microsoft Excel documents."""

    SUPPORTED_TYPES = [
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]

    def supports(self, mime_type: str) -> bool:
        return mime_type in self.SUPPORTED_TYPES

    async def parse(
        self,
        file_content: bytes,
        filename: str,
        options: Dict[str, Any] = None
    ) -> ParsedDocument:
        """
        Parse Excel document.

        In production, this would use libraries like:
        - openpyxl
        - pandas
        - xlrd
        """
        options = options or {}
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if filename.endswith(".xls"):
            mime_type = "application/vnd.ms-excel"

        doc = ParsedDocument(DocumentType.EXCEL, filename, mime_type)

        # Mock Excel parsing
        sheets = await self._mock_excel_extraction(file_content, filename)

        # Convert sheets to text and tables
        text_parts = []
        tables = []

        for sheet in sheets:
            sheet_name = sheet["name"]
            headers = sheet["headers"]
            rows = sheet["rows"]

            text_parts.append(f"=== 시트: {sheet_name} ===")

            table = TableInfo(
                id=f"table_{uuid.uuid4().hex[:8]}",
                headers=headers,
                rows=rows,
                caption=f"시트: {sheet_name}",
                markdown=self._rows_to_markdown(headers, rows)
            )
            tables.append(table)

            # Also add as text
            text_parts.append(table.markdown)

        doc.text_content = "\n\n".join(text_parts)
        doc.tables = tables

        doc.metadata = {
            "title": filename.replace(".xlsx", "").replace(".xls", ""),
            "sheet_count": len(sheets),
            "sheet_names": [s["name"] for s in sheets],
            "total_rows": sum(len(s["rows"]) for s in sheets),
            "total_columns": max(len(s["headers"]) for s in sheets) if sheets else 0
        }

        doc.pages = [{"page_number": i + 1, "content": s["name"]} for i, s in enumerate(sheets)]

        doc.processing_info = {
            "parser": "ExcelParser",
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "is_xlsx": filename.endswith(".xlsx")
        }

        return doc

    async def _mock_excel_extraction(self, content: bytes, filename: str) -> List[Dict[str, Any]]:
        """Mock Excel sheet extraction."""
        await asyncio.sleep(0.3)
        return [
            {
                "name": "Sheet1",
                "headers": ["ID", "이름", "부서", "직급"],
                "rows": [
                    ["1", "홍길동", "개발팀", "과장"],
                    ["2", "김철수", "기획팀", "대리"],
                    ["3", "이영희", "디자인팀", "사원"]
                ]
            },
            {
                "name": "Summary",
                "headers": ["항목", "값"],
                "rows": [
                    ["총 직원 수", "3"],
                    ["부서 수", "3"]
                ]
            }
        ]

    def _rows_to_markdown(self, headers: List[str], rows: List[List[str]]) -> str:
        """Convert table rows to markdown."""
        md = "| " + " | ".join(headers) + " |\n"
        md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
        for row in rows:
            md += "| " + " | ".join(str(cell) for cell in row) + " |\n"
        return md


class PowerPointParser(BaseDocumentParser):
    """Parser for Microsoft PowerPoint documents."""

    SUPPORTED_TYPES = [
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ]

    def supports(self, mime_type: str) -> bool:
        return mime_type in self.SUPPORTED_TYPES

    async def parse(
        self,
        file_content: bytes,
        filename: str,
        options: Dict[str, Any] = None
    ) -> ParsedDocument:
        """
        Parse PowerPoint document.

        In production, this would use libraries like:
        - python-pptx
        - pdf2image (convert to images first)
        """
        options = options or {}
        mime_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if filename.endswith(".ppt"):
            mime_type = "application/vnd.ms-powerpoint"

        doc = ParsedDocument(DocumentType.POWERPOINT, filename, mime_type)

        # Mock PowerPoint parsing
        slides = await self._mock_ppt_extraction(file_content, filename)

        # Convert slides to text
        text_parts = []
        for slide in slides:
            slide_num = slide["number"]
            title = slide.get("title", f"슬라이드 {slide_num}")
            content = slide.get("content", "")

            text_parts.append(f"--- 슬라이드 {slide_num}: {title} ---")
            text_parts.append(content)

            # Add speaker notes if available
            if slide.get("notes"):
                text_parts.append(f"[발표자 노트] {slide['notes']}")

        doc.text_content = "\n\n".join(text_parts)

        doc.metadata = {
            "title": filename.replace(".pptx", "").replace(".ppt", ""),
            "slide_count": len(slides),
            "has_notes": any(s.get("notes") for s in slides)
        }

        doc.pages = [
            {"page_number": s["number"], "content": s.get("title", "")}
            for s in slides
        ]

        # Extract images from slides
        if options.get("extract_images", True):
            doc.images = await self._mock_image_extraction(slides)

        doc.processing_info = {
            "parser": "PowerPointParser",
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "is_pptx": filename.endswith(".pptx")
        }

        return doc

    async def _mock_ppt_extraction(self, content: bytes, filename: str) -> List[Dict[str, Any]]:
        """Mock PowerPoint slide extraction."""
        await asyncio.sleep(0.4)
        return [
            {
                "number": 1,
                "title": "프로젝트 개요",
                "content": "GPU 기반 지식관리 시스템\n\n- 문서 처리\n- AI 질의응답\n- 마인드맵 생성",
                "notes": "프로젝트 소개로 시작"
            },
            {
                "number": 2,
                "title": "시스템 아키텍처",
                "content": "프론트엔드: React\n백엔드: FastAPI\n데이터베이스: Neo4j",
                "notes": ""
            },
            {
                "number": 3,
                "title": "주요 기능",
                "content": "1. 멀티모달 문서 처리\n2. VLM 기반 분석\n3. 하이브리드 RAG",
                "notes": "각 기능 상세 설명"
            },
            {
                "number": 4,
                "title": "결론",
                "content": "효율적인 지식 관리 플랫폼 구축",
                "notes": ""
            }
        ]

    async def _mock_image_extraction(self, slides: List[Dict[str, Any]]) -> List[ImageInfo]:
        """Mock image extraction from slides."""
        return [
            ImageInfo(
                id=f"img_{uuid.uuid4().hex[:8]}",
                page_number=2,
                position={"x": 100, "y": 150, "width": 600, "height": 400},
                description="시스템 아키텍처 다이어그램",
                alt_text="Architecture Diagram"
            )
        ]


class ImageParser(BaseDocumentParser):
    """Parser for image files with VLM support."""

    SUPPORTED_TYPES = [
        "image/png", "image/jpeg", "image/jpg", "image/gif",
        "image/bmp", "image/tiff", "image/webp"
    ]

    def __init__(self, vlm_service=None):
        self.vlm_service = vlm_service

    def supports(self, mime_type: str) -> bool:
        return mime_type in self.SUPPORTED_TYPES

    async def parse(
        self,
        file_content: bytes,
        filename: str,
        options: Dict[str, Any] = None
    ) -> ParsedDocument:
        """
        Parse image file using VLM for understanding.
        """
        options = options or {}
        ext = os.path.splitext(filename)[1].lower()
        mime_type = EXTENSION_TO_MIME.get(ext, "image/png")

        doc = ParsedDocument(DocumentType.IMAGE, filename, mime_type)

        # If VLM service is available, use it for extraction
        if self.vlm_service and options.get("use_vlm", True):
            vlm_result = await self.vlm_service.process_image(
                file_content,
                task="describe"
            )
            doc.text_content = vlm_result.text_content

            # Extract tables if detected
            if vlm_result.tables:
                for t in vlm_result.tables:
                    doc.tables.append(TableInfo(
                        id=t.get("id", f"table_{uuid.uuid4().hex[:8]}"),
                        headers=t.get("headers", []),
                        rows=t.get("rows", []),
                        caption=t.get("caption", "")
                    ))

            doc.metadata = {
                "vlm_processed": True,
                "confidence": vlm_result.confidence_score,
                "processing_time_ms": vlm_result.processing_time_ms,
                "layout": vlm_result.layout_analysis,
                "detected_objects": vlm_result.detected_objects
            }
        else:
            # Basic image info without VLM
            doc.text_content = f"이미지 파일: {filename}"
            doc.metadata = {
                "vlm_processed": False,
                "format": ext.replace(".", "").upper()
            }

        # Create image info
        doc.images = [
            ImageInfo(
                id=f"img_{uuid.uuid4().hex[:8]}",
                description=doc.text_content[:200] if doc.text_content else filename,
                alt_text=filename
            )
        ]

        doc.pages = [{"page_number": 1, "content": doc.text_content}]

        doc.processing_info = {
            "parser": "ImageParser",
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "vlm_enabled": bool(self.vlm_service) and options.get("use_vlm", True)
        }

        return doc


class DocumentParserFactory:
    """Factory for creating appropriate document parsers."""

    def __init__(self, vlm_service=None):
        self.vlm_service = vlm_service
        self.parsers: List[BaseDocumentParser] = [
            TextParser(),
            PDFParser(),
            WordParser(),
            ExcelParser(),
            PowerPointParser(),
            ImageParser(vlm_service)
        ]

    def get_parser(self, mime_type: str) -> Optional[BaseDocumentParser]:
        """Get appropriate parser for MIME type."""
        for parser in self.parsers:
            if parser.supports(mime_type):
                return parser
        return None

    def get_parser_for_file(self, filename: str) -> Optional[BaseDocumentParser]:
        """Get appropriate parser based on filename extension."""
        ext = os.path.splitext(filename)[1].lower()
        mime_type = EXTENSION_TO_MIME.get(ext)
        if mime_type:
            return self.get_parser(mime_type)
        return None

    async def parse_document(
        self,
        file_content: bytes,
        filename: str,
        mime_type: str = None,
        options: Dict[str, Any] = None
    ) -> Optional[ParsedDocument]:
        """
        Parse a document using the appropriate parser.

        Args:
            file_content: Raw file bytes
            filename: Original filename
            mime_type: MIME type (optional, will be inferred from filename)
            options: Parsing options

        Returns:
            ParsedDocument or None if no parser available
        """
        # Determine MIME type
        if not mime_type:
            ext = os.path.splitext(filename)[1].lower()
            mime_type = EXTENSION_TO_MIME.get(ext)

        if not mime_type:
            return None

        # Get parser
        parser = self.get_parser(mime_type)
        if not parser:
            return None

        # Parse document
        return await parser.parse(file_content, filename, options)

    def get_supported_extensions(self) -> List[str]:
        """Get list of supported file extensions."""
        return list(EXTENSION_TO_MIME.keys())

    def get_supported_mime_types(self) -> List[str]:
        """Get list of supported MIME types."""
        return list(SUPPORTED_MIME_TYPES.keys())


# Factory function
def get_document_parser_factory(vlm_service=None) -> DocumentParserFactory:
    """Get document parser factory instance."""
    return DocumentParserFactory(vlm_service)
