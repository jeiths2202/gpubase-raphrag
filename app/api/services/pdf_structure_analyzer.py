"""
PDF Structure Analyzer Service
PDF 구조 분석 서비스

Analyzes PDF documents to extract hierarchical structure and layout information.
"""
import hashlib
import io
import logging
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

from ..models.adaptive_chunk import (
    PDFStructureAnalysis,
    DocumentType,
    SectionInfo,
    LayoutInfo,
)
from ..ports.adaptive_embedding_port import PDFStructureAnalyzerPort
from ..core.settings import get_settings

logger = logging.getLogger(__name__)


class PDFStructureAnalyzer(PDFStructureAnalyzerPort):
    """
    Analyzes PDF structure for adaptive chunking.
    PDF 구조 분석을 통한 적응형 청킹 지원
    """

    # Section header patterns for different document types
    SECTION_PATTERNS = [
        # Numbered sections (e.g., "2.3.1 Title" or "2.3.1. Title")
        (r'^(\d+(?:\.\d+)*\.?)\s+([^\n]+)', 'numbered'),
        # Japanese chapter format (e.g., "第2章 Title")
        (r'^(第\d+章)\s+([^\n]+)', 'japanese_chapter'),
        # Japanese section format (e.g., "第2節 Title")
        (r'^(第\d+節)\s+([^\n]+)', 'japanese_section'),
        # English chapter format (e.g., "Chapter 2 Title")
        (r'^(Chapter\s+\d+)\s*[:\.]?\s*([^\n]+)', 'english_chapter'),
        # Appendix format (e.g., "Appendix A Title" or "付録A Title")
        (r'^((?:Appendix|付録)\s*[A-Z])\s*[:\.]?\s*([^\n]+)', 'appendix'),
        # Roman numeral sections (e.g., "III. Title")
        (r'^((?:I|II|III|IV|V|VI|VII|VIII|IX|X)+)\.\s+([^\n]+)', 'roman'),
    ]

    # Document type classification patterns
    DOC_TYPE_PATTERNS = {
        DocumentType.MANUAL: [
            r'マニュアル|manual|手順書|操作説明|user.?guide',
            r'リファレンス|reference|仕様書|specification',
        ],
        DocumentType.REPORT: [
            r'レポート|report|報告書|分析|analysis',
            r'調査|survey|結果|results',
        ],
        DocumentType.PAPER: [
            r'abstract|要旨|概要',
            r'introduction|序論|はじめに',
            r'conclusion|結論|おわりに',
            r'references|参考文献',
        ],
        DocumentType.CONTRACT: [
            r'契約|contract|agreement|合意',
            r'条項|clause|terms|条件',
        ],
        DocumentType.PRESENTATION: [
            r'プレゼンテーション|presentation|スライド|slide',
        ],
        DocumentType.FORM: [
            r'申請|application|フォーム|form',
            r'記入|fill|入力|input',
        ],
    }

    def __init__(self, min_section_length: int = None):
        """
        Initialize analyzer.

        Args:
            min_section_length: Minimum characters for a valid section (uses settings if None)
        """
        # Only load settings if parameter needs default value
        if min_section_length is None:
            settings = get_settings()
            self.min_section_length = settings.adaptive_embedding.min_section_length
        else:
            self.min_section_length = min_section_length

    async def analyze(
        self,
        pdf_content: bytes,
        pdf_id: str,
        language: str = "auto",
        document_name: Optional[str] = None
    ) -> PDFStructureAnalysis:
        """
        Analyze PDF structure and extract hierarchy.

        Args:
            pdf_content: Raw PDF bytes
            pdf_id: Unique document ID
            language: Document language (auto, en, ja, ko)
            document_name: Original filename for source reference
        """
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=pdf_content, filetype="pdf")

            # Extract text and compute page hashes
            pages_text = []
            page_hashes = {}
            total_images = 0
            total_tables = 0

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                pages_text.append((page_num + 1, text))

                # Compute page hash for incremental processing
                page_hash = hashlib.sha256(text.encode()).hexdigest()
                page_hashes[str(page_num + 1)] = page_hash

                # Count images
                image_list = page.get_images(full=False)
                total_images += len(image_list)

                # Detect tables (heuristic: multiple patterns)
                # 1. Markdown table: |...|
                # 2. Tab-separated: multiple tabs
                # 3. Definition list: 用語/説明, Term/Description patterns (JP/EN docs)
                # 4. Aligned columns: repeated "  " spacing patterns
                has_table = (
                    re.search(r'(\|.*\|)|(\t.*\t.*\t)', text) or  # Markdown or tabs
                    re.search(r'(説明|Description)\s*\n\s*(用語|Term|項目|パラメータ)', text, re.IGNORECASE) or  # JP/EN definition header
                    re.search(r'(用語|Term|項目|パラメータ)\s*\n\s*(説明|Description)', text, re.IGNORECASE) or  # Reversed header
                    len([line for line in text.split('\n') if re.match(r'^[^\s]{2,20}\s{2,}[^\s]', line)]) > 3  # Aligned columns
                )
                if has_table:
                    total_tables += 1

            # Combine all text
            full_text = "\n".join([text for _, text in pages_text])

            # Detect document type
            doc_type = await self.detect_document_type(pdf_content)

            # Detect language if auto
            if language == "auto":
                language = self._detect_language(full_text)

            # Extract hierarchy
            hierarchy = await self._extract_hierarchy_internal(pages_text, language)

            # Analyze layout
            layout_info = self._analyze_layout(doc, pages_text)

            doc.close()

            return PDFStructureAnalysis(
                pdf_id=pdf_id,
                document_type=doc_type,
                hierarchy=hierarchy,
                layout_info=layout_info,
                page_hashes=page_hashes,
                total_pages=len(pages_text),
                total_images=total_images,
                total_tables=total_tables,
                language=language,
                analyzed_at=datetime.now(timezone.utc),
                document_name=document_name
            )

        except ImportError:
            logger.warning("PyMuPDF not available, using fallback analysis")
            return await self._fallback_analyze(pdf_content, pdf_id, language, document_name)
        except Exception as e:
            logger.error(f"PDF structure analysis failed: {e}")
            raise

    async def detect_document_type(self, pdf_content: bytes) -> DocumentType:
        """Detect document type based on content patterns."""
        try:
            import fitz

            doc = fitz.open(stream=pdf_content, filetype="pdf")

            # Sample first few pages for classification
            sample_text = ""
            for i in range(min(5, len(doc))):
                sample_text += doc[i].get_text()

            doc.close()

            sample_lower = sample_text.lower()

            # Check each document type pattern
            type_scores = {}
            for doc_type, patterns in self.DOC_TYPE_PATTERNS.items():
                score = 0
                for pattern in patterns:
                    if re.search(pattern, sample_lower, re.IGNORECASE):
                        score += 1
                if score > 0:
                    type_scores[doc_type] = score

            if type_scores:
                return max(type_scores, key=type_scores.get)

            return DocumentType.OTHER

        except Exception as e:
            logger.warning(f"Document type detection failed: {e}")
            return DocumentType.OTHER

    async def extract_hierarchy(
        self,
        pdf_content: bytes,
        language: str = "auto"
    ) -> List[Dict[str, Any]]:
        """Extract section hierarchy from PDF."""
        try:
            import fitz

            doc = fitz.open(stream=pdf_content, filetype="pdf")

            pages_text = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                pages_text.append((page_num + 1, text))

            doc.close()

            if language == "auto":
                full_text = "\n".join([text for _, text in pages_text])
                language = self._detect_language(full_text)

            hierarchy = await self._extract_hierarchy_internal(pages_text, language)
            return [s.to_dict() for s in hierarchy]

        except Exception as e:
            logger.error(f"Hierarchy extraction failed: {e}")
            return []

    async def _extract_hierarchy_internal(
        self,
        pages_text: List[Tuple[int, str]],
        language: str
    ) -> List[SectionInfo]:
        """
        Internal method to extract section hierarchy.
        """
        sections = []
        current_positions = {}  # Track positions for each level

        # Combine all text with page markers
        combined_text = ""
        page_positions = {}  # char_position -> page_num
        current_pos = 0

        for page_num, text in pages_text:
            page_positions[current_pos] = page_num
            combined_text += text + "\n"
            current_pos = len(combined_text)

        # Find all section headers
        found_sections = []
        for pattern, pattern_type in self.SECTION_PATTERNS:
            for match in re.finditer(pattern, combined_text, re.MULTILINE):
                section_id = match.group(1).strip().rstrip('.')
                section_title = match.group(2).strip()

                # Filter noise
                if len(section_title) < 2:
                    continue
                if any(x in section_title for x in ['...', '●', '>>-', '---']):
                    continue

                # Determine page number
                char_pos = match.start()
                page_num = 1
                for pos, pnum in sorted(page_positions.items()):
                    if pos <= char_pos:
                        page_num = pnum
                    else:
                        break

                # Determine level based on pattern type and section_id
                level = self._determine_level(section_id, pattern_type)

                found_sections.append({
                    'id': section_id,
                    'title': section_title,
                    'level': level,
                    'page_start': page_num,
                    'position': char_pos,
                    'pattern_type': pattern_type
                })

        # Sort by position in document
        found_sections.sort(key=lambda x: x['position'])

        # Build hierarchy with parent-child relationships
        section_stack = []  # Stack of (level, section_id)

        for i, sec in enumerate(found_sections):
            # Determine page_end (next section's page_start - 1 or last page)
            if i + 1 < len(found_sections):
                page_end = found_sections[i + 1]['page_start']
            else:
                page_end = pages_text[-1][0] if pages_text else 1

            # Find parent
            parent_id = None
            while section_stack and section_stack[-1][0] >= sec['level']:
                section_stack.pop()
            if section_stack:
                parent_id = section_stack[-1][1]

            # Add to stack
            section_stack.append((sec['level'], sec['id']))

            sections.append(SectionInfo(
                id=sec['id'],
                title=sec['title'],
                level=sec['level'],
                page_start=sec['page_start'],
                page_end=page_end,
                parent_id=parent_id,
                children=[]
            ))

        # Build children lists
        section_map = {s.id: s for s in sections}
        for section in sections:
            if section.parent_id and section.parent_id in section_map:
                parent = section_map[section.parent_id]
                if section.id not in parent.children:
                    parent.children.append(section.id)

        return sections

    def _determine_level(self, section_id: str, pattern_type: str) -> int:
        """Determine section level from ID and pattern type."""
        if pattern_type == 'numbered':
            # Count dots to determine level
            return section_id.count('.') + 1
        elif pattern_type in ['japanese_chapter', 'english_chapter']:
            return 1
        elif pattern_type == 'japanese_section':
            return 2
        elif pattern_type == 'appendix':
            return 1
        elif pattern_type == 'roman':
            return 1
        return 1

    def _analyze_layout(self, doc, pages_text: List[Tuple[int, str]]) -> LayoutInfo:
        """Analyze document layout."""
        try:
            # Get page dimensions from first page
            first_page = doc[0]
            rect = first_page.rect
            page_dimensions = {"width": rect.width, "height": rect.height}

            # Detect columns (heuristic: check text block distribution)
            columns = 1
            if pages_text:
                _, first_text = pages_text[0]
                # If text has unusual spacing patterns, might be multi-column
                lines = first_text.split('\n')
                if lines:
                    avg_line_length = sum(len(l) for l in lines if l.strip()) / max(len([l for l in lines if l.strip()]), 1)
                    # Multi-column documents typically have shorter lines
                    if avg_line_length < 60 and rect.width > 500:
                        columns = 2

            # Detect header/footer
            has_header = False
            has_footer = False
            if len(pages_text) > 2:
                # Check if first few lines repeat across pages
                first_lines = [text.split('\n')[:3] for _, text in pages_text[:5]]
                if len(first_lines) > 2:
                    # Simple heuristic: if any short line appears on multiple pages
                    line_counts = {}
                    for lines in first_lines:
                        for line in lines:
                            line = line.strip()
                            if 5 < len(line) < 50:  # Header/footer length
                                line_counts[line] = line_counts.get(line, 0) + 1
                    has_header = any(c > 2 for c in line_counts.values())

                # Check footer (last few lines)
                last_lines = [text.split('\n')[-3:] for _, text in pages_text[:5]]
                if len(last_lines) > 2:
                    line_counts = {}
                    for lines in last_lines:
                        for line in lines:
                            line = line.strip()
                            if 1 < len(line) < 50:
                                line_counts[line] = line_counts.get(line, 0) + 1
                    has_footer = any(c > 2 for c in line_counts.values())

            # Detect TOC
            has_toc = False
            if pages_text:
                full_text = "\n".join([text for _, text in pages_text[:10]])
                toc_patterns = [
                    r'目次|table\s+of\s+contents|contents|index',
                    r'\.\s*\.\s*\.\s*\d+',  # Dotted leader lines
                ]
                for pattern in toc_patterns:
                    if re.search(pattern, full_text, re.IGNORECASE):
                        has_toc = True
                        break

            return LayoutInfo(
                columns=columns,
                has_header=has_header,
                has_footer=has_footer,
                has_toc=has_toc,
                page_dimensions=page_dimensions
            )

        except Exception as e:
            logger.warning(f"Layout analysis failed: {e}")
            return LayoutInfo()

    def _detect_language(self, text: str) -> str:
        """Detect document language from text content."""
        sample = text[:5000]  # Sample first 5000 chars

        # Count character types
        ja_chars = sum(1 for c in sample if '\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff')
        ko_chars = sum(1 for c in sample if '\uac00' <= c <= '\ud7af')
        ascii_chars = sum(1 for c in sample if c.isascii() and c.isalpha())

        total = len(sample)
        if total == 0:
            return "en"

        ja_ratio = ja_chars / total
        ko_ratio = ko_chars / total

        if ja_ratio > 0.1:
            return "ja"
        elif ko_ratio > 0.1:
            return "ko"
        else:
            return "en"

    async def _fallback_analyze(
        self,
        pdf_content: bytes,
        pdf_id: str,
        language: str,
        document_name: Optional[str] = None
    ) -> PDFStructureAnalysis:
        """Fallback analysis when PyMuPDF is not available."""
        # Use pypdf as fallback
        try:
            from pypdf import PdfReader

            pdf_file = io.BytesIO(pdf_content)
            reader = PdfReader(pdf_file)

            pages_text = []
            page_hashes = {}

            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages_text.append((i + 1, text))
                page_hash = hashlib.sha256(text.encode()).hexdigest()
                page_hashes[str(i + 1)] = page_hash

            full_text = "\n".join([text for _, text in pages_text])

            if language == "auto":
                language = self._detect_language(full_text)

            hierarchy = await self._extract_hierarchy_internal(pages_text, language)

            return PDFStructureAnalysis(
                pdf_id=pdf_id,
                document_type=DocumentType.OTHER,
                hierarchy=hierarchy,
                layout_info=LayoutInfo(),
                page_hashes=page_hashes,
                total_pages=len(pages_text),
                total_images=0,
                total_tables=0,
                language=language,
                analyzed_at=datetime.now(timezone.utc),
                document_name=document_name
            )

        except Exception as e:
            logger.error(f"Fallback analysis also failed: {e}")
            return PDFStructureAnalysis(
                pdf_id=pdf_id,
                document_type=DocumentType.OTHER,
                hierarchy=[],
                layout_info=LayoutInfo(),
                page_hashes={},
                total_pages=0,
                language=language,
                analyzed_at=datetime.now(timezone.utc),
                document_name=document_name
            )


    async def extract_images(
        self,
        pdf_content: bytes,
        pdf_id: str,
        min_size: int = 50,
        max_images: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Extract images from PDF.
        PDF에서 이미지 추출

        Args:
            pdf_content: PDF file bytes
            pdf_id: Document identifier
            min_size: Minimum image dimension (width or height)
            max_images: Maximum number of images to extract

        Returns:
            List of extracted image data dicts
        """
        try:
            import fitz

            doc = fitz.open(stream=pdf_content, filetype="pdf")
            extracted_images = []

            for page_num in range(len(doc)):
                if len(extracted_images) >= max_images:
                    break

                page = doc[page_num]
                image_list = page.get_images(full=True)

                for img_index, img_info in enumerate(image_list):
                    if len(extracted_images) >= max_images:
                        break

                    try:
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)

                        if not base_image:
                            continue

                        image_bytes = base_image["image"]
                        image_ext = base_image.get("ext", "png")
                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)

                        # Skip small images (likely icons/bullets)
                        if width < min_size or height < min_size:
                            continue

                        # Create unique image ID
                        image_id = f"img_{pdf_id}_{page_num + 1}_{img_index}"

                        # Determine MIME type
                        mime_map = {
                            "png": "image/png",
                            "jpeg": "image/jpeg",
                            "jpg": "image/jpeg",
                            "gif": "image/gif",
                            "bmp": "image/bmp",
                        }
                        mime_type = mime_map.get(image_ext.lower(), f"image/{image_ext}")

                        # Get image position on page
                        position = None
                        for img_rect in page.get_image_rects(xref):
                            position = {
                                "x": img_rect.x0,
                                "y": img_rect.y0,
                                "width": img_rect.width,
                                "height": img_rect.height
                            }
                            break

                        extracted_images.append({
                            "image_id": image_id,
                            "document_id": pdf_id,
                            "page_number": page_num + 1,
                            "image_data": image_bytes,
                            "mime_type": mime_type,
                            "width": width,
                            "height": height,
                            "file_size": len(image_bytes),
                            "position": position,
                        })

                        logger.debug(f"Extracted image {image_id}: {width}x{height} {mime_type}")

                    except Exception as img_error:
                        logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {img_error}")
                        continue

            doc.close()
            logger.info(f"Extracted {len(extracted_images)} images from PDF {pdf_id}")
            return extracted_images

        except ImportError:
            logger.warning("PyMuPDF not available for image extraction")
            return []
        except Exception as e:
            logger.error(f"Image extraction failed: {e}")
            return []


# Singleton instance
_analyzer: Optional[PDFStructureAnalyzer] = None


def get_pdf_structure_analyzer(
    min_section_length: int = None
) -> PDFStructureAnalyzer:
    """Get or create PDF structure analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = PDFStructureAnalyzer(min_section_length=min_section_length)
    return _analyzer
