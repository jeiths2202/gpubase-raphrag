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
    """Parser for PDF documents using pypdf for real extraction."""

    SUPPORTED_TYPES = ["application/pdf"]

    def __init__(self, vlm_service=None):
        """
        Initialize PDF parser.

        Args:
            vlm_service: Optional VLM service for OCR and enhanced extraction
        """
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
        Parse PDF document using pypdf library for real statistics.
        """
        options = options or {}
        doc = ParsedDocument(DocumentType.PDF, filename, "application/pdf")

        # Use real PDF parsing with pypdf
        pdf_data = await self._extract_pdf_content(file_content, options)

        doc.text_content = pdf_data["text_content"]
        doc.pages = pdf_data["pages"]
        doc.metadata = pdf_data["metadata"]
        doc.images = pdf_data["images"]
        doc.tables = pdf_data["tables"]

        doc.processing_info = {
            "parser": "PDFParser",
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "options": options,
            "extraction_method": "pypdf"
        }

        return doc

    async def _extract_pdf_content(
        self,
        content: bytes,
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract real content from PDF using pypdf, with optional VLM OCR."""
        processing_mode = options.get("processing_mode", "text_only")
        enable_vlm = options.get("enable_vlm", False)
        language = options.get("language", "auto")

        try:
            from pypdf import PdfReader

            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._sync_extract_pdf,
                content,
                options
            )

            # Check if VLM OCR is needed
            if (processing_mode in ["image_only", "vlm_enhanced"] or enable_vlm) and self.vlm_service:
                # Enhance pages with low text content using VLM OCR
                result = await self._enhance_with_vlm_ocr(
                    content, result, processing_mode, language
                )

            return result

        except ImportError:
            # Fallback to mock if pypdf not available
            return await self._fallback_mock_extraction(content)
        except Exception as e:
            # Fallback on any error
            print(f"PDF extraction error: {e}, using fallback")
            return await self._fallback_mock_extraction(content)

    async def _enhance_with_vlm_ocr(
        self,
        pdf_content: bytes,
        parsed_result: Dict[str, Any],
        processing_mode: str,
        language: str = "auto"
    ) -> Dict[str, Any]:
        """
        Enhance PDF extraction with VLM-based OCR for pages with little/no text.

        Args:
            pdf_content: Original PDF bytes
            parsed_result: Initial parsing result from pypdf
            processing_mode: Processing mode (ocr, vlm_enhanced, multimodal)
            language: Expected document language

        Returns:
            Enhanced parsing result with OCR text
        """
        if not self.vlm_service:
            return parsed_result

        try:
            import fitz  # PyMuPDF for page-to-image conversion

            pdf_doc = fitz.open(stream=pdf_content, filetype="pdf")
            pages = parsed_result.get("pages", [])
            enhanced_pages = []
            full_text_parts = []
            ocr_count = 0

            # Threshold for considering a page as needing OCR
            # If a page has less than 50 characters, it likely needs OCR
            MIN_TEXT_THRESHOLD = 50

            for page_info in pages:
                page_num = page_info.get("page_number", 1)
                page_text = page_info.get("content", "")
                char_count = len(page_text.strip())

                # Check if this page needs OCR
                needs_ocr = (
                    processing_mode == "image_only" or  # Force OCR for all pages
                    (processing_mode == "vlm_enhanced" and char_count < MIN_TEXT_THRESHOLD)
                )

                if needs_ocr and page_num <= len(pdf_doc):
                    try:
                        # Convert page to image
                        fitz_page = pdf_doc[page_num - 1]
                        # Use higher resolution for better OCR (2x zoom)
                        mat = fitz.Matrix(2, 2)
                        pix = fitz_page.get_pixmap(matrix=mat)
                        img_bytes = pix.tobytes("png")

                        # Call VLM OCR
                        ocr_result = await self.vlm_service.extract_text_ocr(
                            img_bytes, language=language
                        )

                        ocr_text = ocr_result.get("text", "")
                        ocr_confidence = ocr_result.get("confidence", 0)

                        if ocr_text and len(ocr_text) > char_count:
                            # Use OCR result if it's better than pypdf extraction
                            enhanced_pages.append({
                                "page_number": page_num,
                                "content": ocr_text,
                                "char_count": len(ocr_text),
                                "ocr_applied": True,
                                "ocr_confidence": ocr_confidence,
                                "original_char_count": char_count
                            })
                            full_text_parts.append(ocr_text)
                            ocr_count += 1
                            print(f"[OCR] Page {page_num}: {char_count} → {len(ocr_text)} chars (VLM OCR)")
                        else:
                            # Keep original if OCR didn't improve
                            enhanced_pages.append(page_info)
                            full_text_parts.append(page_text)

                    except Exception as ocr_error:
                        print(f"[OCR] Page {page_num} OCR failed: {ocr_error}")
                        enhanced_pages.append(page_info)
                        full_text_parts.append(page_text)
                else:
                    # Keep original page
                    enhanced_pages.append(page_info)
                    full_text_parts.append(page_text)

            pdf_doc.close()

            # Update result with enhanced pages
            parsed_result["pages"] = enhanced_pages
            parsed_result["text_content"] = "\n\n".join(full_text_parts)
            parsed_result["metadata"]["ocr_pages_count"] = ocr_count
            parsed_result["metadata"]["vlm_enhanced"] = True

            if ocr_count > 0:
                print(f"[OCR] Enhanced {ocr_count} pages with VLM OCR")

            return parsed_result

        except ImportError:
            print("[OCR] PyMuPDF (fitz) not available for page-to-image conversion")
            return parsed_result
        except Exception as e:
            print(f"[OCR] VLM enhancement failed: {e}")
            return parsed_result

    def _sync_extract_pdf(
        self,
        content: bytes,
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Synchronous PDF extraction using pypdf."""
        from pypdf import PdfReader

        pdf_file = io.BytesIO(content)
        reader = PdfReader(pdf_file)

        # Extract real page count
        page_count = len(reader.pages)

        # Extract text from each page
        pages = []
        full_text = []
        image_count = 0

        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            pages.append({
                "page_number": i + 1,
                "content": page_text,
                "char_count": len(page_text)
            })
            full_text.append(page_text)

            # Count images in page (pypdf can detect image objects)
            try:
                if "/XObject" in page["/Resources"]:
                    x_objects = page["/Resources"]["/XObject"].get_object()
                    for obj_name in x_objects:
                        obj = x_objects[obj_name]
                        if obj["/Subtype"] == "/Image":
                            image_count += 1
            except (KeyError, TypeError, AttributeError):
                pass

        # Extract metadata
        pdf_metadata = reader.metadata or {}
        metadata = {
            "pages": page_count,
            "title": pdf_metadata.get("/Title", "").strip() if pdf_metadata.get("/Title") else "",
            "author": pdf_metadata.get("/Author", "").strip() if pdf_metadata.get("/Author") else "",
            "subject": pdf_metadata.get("/Subject", "").strip() if pdf_metadata.get("/Subject") else "",
            "creator": pdf_metadata.get("/Creator", "").strip() if pdf_metadata.get("/Creator") else "",
            "created_date": str(pdf_metadata.get("/CreationDate", "")) if pdf_metadata.get("/CreationDate") else "",
            "modified_date": str(pdf_metadata.get("/ModDate", "")) if pdf_metadata.get("/ModDate") else "",
            "pdf_version": f"{reader.pdf_header}" if hasattr(reader, 'pdf_header') else "unknown"
        }

        # Use filename as title if not available
        if not metadata["title"]:
            metadata["title"] = options.get("filename", "Untitled").replace(".pdf", "")

        # Create image info list with actual image data using PyMuPDF
        images = []
        if options.get("extract_images", True):
            try:
                import fitz  # PyMuPDF
                pdf_doc = fitz.open(stream=content, filetype="pdf")
                img_idx = 0
                for page_num in range(len(pdf_doc)):
                    page = pdf_doc[page_num]
                    image_list = page.get_images(full=True)
                    for img in image_list:
                        try:
                            xref = img[0]
                            base_image = pdf_doc.extract_image(xref)
                            if base_image:
                                image_bytes = base_image["image"]
                                image_ext = base_image["ext"]
                                # Only include images larger than 100x100
                                width = base_image.get("width", 0)
                                height = base_image.get("height", 0)
                                if width >= 100 and height >= 100:
                                    images.append(ImageInfo(
                                        id=f"img_{uuid.uuid4().hex[:8]}",
                                        page_number=page_num + 1,
                                        position={"x": 0, "y": 0, "width": width, "height": height},
                                        description=f"Image on page {page_num + 1}",
                                        alt_text=f"Embedded image {img_idx + 1}",
                                        data=image_bytes,  # Actual image binary data
                                        width=width,
                                        height=height,
                                        mime_type=f"image/{image_ext}"
                                    ))
                                    img_idx += 1
                        except Exception as img_err:
                            pass  # Skip problematic images
                pdf_doc.close()
            except ImportError:
                # PyMuPDF not available, create metadata-only entries
                for i in range(image_count):
                    images.append(ImageInfo(
                        id=f"img_{uuid.uuid4().hex[:8]}",
                        page_number=0,
                        position={"x": 0, "y": 0, "width": 0, "height": 0},
                        description=f"Image {i + 1}",
                        alt_text=f"Embedded image {i + 1}"
                    ))
            except Exception as e:
                print(f"Image extraction error: {e}")

        # Extract figure references and match to images
        if images:
            try:
                from .figure_reference_extractor import get_figure_extractor
                extractor = get_figure_extractor()

                # Extract figure references from page text
                figure_refs = extractor.extract_references(pages)

                if figure_refs:
                    # Convert images to dict format for matching
                    image_dicts = [{"page_number": img.page_number} for img in images]

                    # Match references to images
                    mappings = extractor.match_to_images(figure_refs, image_dicts)

                    # Update images with figure references
                    for mapping in mappings:
                        if 0 <= mapping.image_index < len(images):
                            img = images[mapping.image_index]
                            # Update the ImageInfo with figure reference
                            images[mapping.image_index] = ImageInfo(
                                id=img.id,
                                page_number=img.page_number,
                                position=img.position,
                                description=img.description,
                                alt_text=img.alt_text,
                                data=img.data,
                                width=img.width,
                                height=img.height,
                                mime_type=img.mime_type,
                                figure_reference=mapping.normalized,
                                figure_caption=mapping.caption
                            )
                            print(f"Matched figure {mapping.reference} -> image {mapping.image_index} (page {img.page_number})")
            except Exception as e:
                print(f"Figure reference extraction error: {e}")

        # Table detection (basic heuristic - count lines with multiple | or tabs)
        tables = []
        table_pattern = re.compile(r'(\|.*\|)|(\t.*\t.*\t)')
        table_count = 0
        for i, page in enumerate(pages):
            content = page.get("content", "")
            if table_pattern.search(content):
                table_count += 1
                tables.append(TableInfo(
                    id=f"table_{uuid.uuid4().hex[:8]}",
                    page_number=i + 1,
                    headers=[],
                    rows=[],
                    caption=f"Table detected on page {i + 1}",
                    markdown=""
                ))

        return {
            "text_content": "\n\n".join(full_text),
            "pages": pages,
            "metadata": metadata,
            "images": images,
            "tables": tables
        }

    async def _fallback_mock_extraction(self, content: bytes) -> Dict[str, Any]:
        """Fallback mock extraction when pypdf fails."""
        await asyncio.sleep(0.1)
        return {
            "text_content": "PDF content could not be extracted",
            "pages": [{"page_number": 1, "content": "Content extraction failed", "char_count": 0}],
            "metadata": {
                "pages": 1,
                "title": "Unknown",
                "author": "",
                "subject": "",
                "creator": "",
                "created_date": "",
                "modified_date": "",
                "pdf_version": "unknown"
            },
            "images": [],
            "tables": []
        }


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
            PDFParser(vlm_service),
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
