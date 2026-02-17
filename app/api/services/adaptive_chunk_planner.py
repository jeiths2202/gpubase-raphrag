"""
Adaptive Chunk Planner Service
적응형 청크 계획 서비스

Plans chunks based on semantic boundaries rather than fixed sizes.
"""
import hashlib
import io
import logging
import re
import uuid
from typing import List, Dict, Any, Tuple, Optional

from ..models.adaptive_chunk import (
    AdaptiveChunk,
    ChunkPlan,
    ChunkType,
    ChunkRelations,
    PDFStructureAnalysis,
    SectionInfo,
)
from ..ports.adaptive_embedding_port import AdaptiveChunkPlannerPort
from ..core.settings import get_settings

logger = logging.getLogger(__name__)


class AdaptiveChunkPlanner(AdaptiveChunkPlannerPort):
    """
    Plans chunks based on semantic boundaries.
    의미적 경계를 기반으로 청크 계획 수립
    """

    # Sentence ending patterns for various languages
    SENTENCE_ENDINGS = [
        r'。',      # Japanese period
        r'．',      # Full-width period
        r'\.',      # ASCII period
        r'！',      # Japanese exclamation
        r'？',      # Japanese question
        r'!',       # ASCII exclamation
        r'\?',      # ASCII question
    ]

    # Table detection patterns
    TABLE_PATTERNS = [
        r'\|[^\|]+\|',  # Markdown table
        r'┌.*┐',        # Box drawing table
        r'╔.*╗',        # Double box table
        r'┏.*┓',        # Heavy box table
    ]

    # Error code patterns for error reference documents
    # 에러 참조 문서의 에러 코드 패턴
    ERROR_CODE_PATTERNS = [
        # Product-specific error codes
        r'(?:JEUS|TIBERO|TMAX|OFM|OFCOBOL|OFASM|TLIC|DSALC|OSALC|CDSAL|TDSAL)[-_]?(?:ERR[-_])?[A-Z_]*\s*\(?-?\d+\)?',
        # Standard error codes
        r'(?:ORA|SQL|ERR|ERROR)[-_]\d{4,5}',
        # Negative numeric error codes like (-5212)
        r'\(-\d{4,5}\)',
        # Error code with name pattern: NAME (-1234)
        r'[A-Z][A-Z0-9_]+\s*\(-\d+\)',
    ]

    # Error reference document detection keywords
    ERROR_DOC_KEYWORDS = [
        'Error Reference',
        'エラーリファレンス',
        '에러 참조',
        'Error Code',
        'エラーコード',
        '에러 코드',
        'Error Messages',
        'エラーメッセージ',
        '에러 메시지',
    ]

    def __init__(
        self,
        max_chunk_size: int = None,
        min_chunk_size: int = None,
        overlap_size: int = None,
        preserve_tables: bool = None,
        preserve_sections: bool = None
    ):
        """
        Initialize planner.

        Args:
            max_chunk_size: Maximum chunk size in characters (uses settings if None)
            min_chunk_size: Minimum chunk size in characters (uses settings if None)
            overlap_size: Overlap between adjacent chunks (uses settings if None)
            preserve_tables: Keep tables as single chunks (uses settings if None)
            preserve_sections: Respect section boundaries (uses settings if None)
        """
        # Only load settings if any parameter needs default value
        needs_settings = any(p is None for p in [
            max_chunk_size, min_chunk_size, overlap_size,
            preserve_tables, preserve_sections
        ])

        if needs_settings:
            settings = get_settings()
            adaptive = settings.adaptive_embedding
            self.max_chunk_size = max_chunk_size if max_chunk_size is not None else adaptive.max_chunk_size
            self.min_chunk_size = min_chunk_size if min_chunk_size is not None else adaptive.min_chunk_size
            self.overlap_size = overlap_size if overlap_size is not None else adaptive.overlap_size
            self.preserve_tables = preserve_tables if preserve_tables is not None else adaptive.preserve_tables
            self.preserve_sections = preserve_sections if preserve_sections is not None else adaptive.preserve_sections
        else:
            self.max_chunk_size = max_chunk_size
            self.min_chunk_size = min_chunk_size
            self.overlap_size = overlap_size
            self.preserve_tables = preserve_tables
            self.preserve_sections = preserve_sections

    async def create_chunk_plan(
        self,
        pdf_content: bytes,
        structure: PDFStructureAnalysis,
        options: Dict[str, Any]
    ) -> List[ChunkPlan]:
        """
        Create a chunking plan based on structure analysis.
        """
        # Extract text with page info
        pages_text = await self._extract_pages_text(pdf_content)
        if not pages_text:
            return []

        # Override defaults with options
        max_size = options.get('max_chunk_size', self.max_chunk_size)
        min_size = options.get('min_chunk_size', self.min_chunk_size)
        preserve_tables = options.get('preserve_tables', self.preserve_tables)
        preserve_sections = options.get('preserve_sections', self.preserve_sections)
        filename = options.get('filename', '')

        plans = []

        # 🔴 PRIORITY 1: Try error code-specific chunking for error reference documents
        # 에러 참조 문서인 경우 에러 코드별 독립 청킹 우선 적용
        error_plans = await self._create_error_code_plan(pages_text, structure, filename)
        if error_plans:
            logger.info(f"Using error-specific chunking: {len(error_plans)} error chunks")
            plans = error_plans
        elif preserve_sections and structure.hierarchy:
            # Section-aware chunking
            plans = await self._create_section_based_plan(
                pages_text, structure, max_size, min_size
            )
        else:
            # Fallback to semantic boundary chunking
            plans = await self._create_semantic_plan(
                pages_text, max_size, min_size
            )

        # Extract tables as separate chunks if enabled
        if preserve_tables:
            table_plans = await self._extract_table_plans(pages_text)
            plans.extend(table_plans)

        # Sort plans by page and position
        plans.sort(key=lambda p: (p.page_start, p.section_path or ""))

        return plans

    async def detect_semantic_boundaries(
        self,
        text: str,
        structure: PDFStructureAnalysis
    ) -> List[int]:
        """
        Detect semantic boundary positions in text.
        """
        boundaries = []

        # Section headers are strong boundaries
        for section in structure.hierarchy:
            # Find section header in text
            title_pattern = re.escape(section.title[:30])  # First 30 chars
            for match in re.finditer(title_pattern, text):
                boundaries.append(match.start())

        # Paragraph breaks (double newlines)
        for match in re.finditer(r'\n\s*\n', text):
            boundaries.append(match.start())

        # Sentence endings followed by newline
        sentence_pattern = '|'.join(self.SENTENCE_ENDINGS)
        for match in re.finditer(f'({sentence_pattern})\s*\n', text):
            boundaries.append(match.end())

        # Remove duplicates and sort
        boundaries = sorted(set(boundaries))

        return boundaries

    async def build_chunk_relations(
        self,
        chunks: List[AdaptiveChunk]
    ) -> List[AdaptiveChunk]:
        """
        Build relationships between chunks (previous, next, references).
        """
        # Group chunks by PDF
        pdf_chunks: Dict[str, List[AdaptiveChunk]] = {}
        for chunk in chunks:
            if chunk.pdf_id not in pdf_chunks:
                pdf_chunks[chunk.pdf_id] = []
            pdf_chunks[chunk.pdf_id].append(chunk)

        # Build relations for each PDF
        result_chunks = []
        for pdf_id, pdf_chunk_list in pdf_chunks.items():
            # Sort by page and section
            pdf_chunk_list.sort(key=lambda c: (c.page_start, c.section_path or ""))

            for i, chunk in enumerate(pdf_chunk_list):
                relations = ChunkRelations()

                # Previous chunk
                if i > 0:
                    relations.previous = pdf_chunk_list[i - 1].chunk_id

                # Next chunk
                if i < len(pdf_chunk_list) - 1:
                    relations.next = pdf_chunk_list[i + 1].chunk_id

                # Parent (by section path)
                if chunk.section_path:
                    parent_path = self._get_parent_section_path(chunk.section_path)
                    if parent_path:
                        for other in pdf_chunk_list:
                            if other.section_path == parent_path:
                                relations.parent = other.chunk_id
                                break

                # Children (by section path)
                if chunk.section_path:
                    child_prefix = chunk.section_path + "."
                    for other in pdf_chunk_list:
                        if other.section_path and other.section_path.startswith(child_prefix):
                            # Only direct children (one level deeper)
                            remaining = other.section_path[len(child_prefix):]
                            if '.' not in remaining:
                                relations.children.append(other.chunk_id)

                # Update chunk with relations
                chunk.relations = relations
                result_chunks.append(chunk)

        return result_chunks

    async def _extract_pages_text(
        self,
        pdf_content: bytes
    ) -> List[Tuple[int, str]]:
        """Extract text from PDF pages."""
        try:
            import fitz

            doc = fitz.open(stream=pdf_content, filetype="pdf")
            pages = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    pages.append((page_num + 1, text))
            doc.close()
            return pages

        except ImportError:
            # Fallback to pypdf
            try:
                from pypdf import PdfReader

                pdf_file = io.BytesIO(pdf_content)
                reader = PdfReader(pdf_file)
                pages = []
                for i, page in enumerate(reader.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        pages.append((i + 1, text))
                return pages
            except Exception as e:
                logger.error(f"Failed to extract PDF text: {e}")
                return []

        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}")
            return []

    async def _create_section_based_plan(
        self,
        pages_text: List[Tuple[int, str]],
        structure: PDFStructureAnalysis,
        max_size: int,
        min_size: int
    ) -> List[ChunkPlan]:
        """Create chunk plan based on document sections."""
        plans = []

        # Build full text with page position tracking
        full_text = ""
        page_positions = {}  # char_position -> page_num
        current_pos = 0

        for page_num, text in pages_text:
            page_positions[current_pos] = page_num
            full_text += text + "\n"
            current_pos = len(full_text)

        # Track used page ranges to prevent duplicates
        used_page_ranges = set()  # (page_start, page_end, content_hash)

        # Process each section
        for i, section in enumerate(structure.hierarchy):
            # Find section content
            section_start = self._find_section_start(full_text, section)
            if section_start < 0:
                continue

            # Find section end (next section or end of document)
            section_end = len(full_text)
            for j, next_section in enumerate(structure.hierarchy):
                if j > i:
                    next_start = self._find_section_start(full_text, next_section)
                    if next_start > section_start:
                        section_end = next_start
                        break

            section_content = full_text[section_start:section_end].strip()

            # Skip if too short
            if len(section_content) < min_size:
                continue

            # Determine page range
            page_start = self._get_page_at_position(page_positions, section_start)
            page_end = self._get_page_at_position(page_positions, section_end - 1)

            # Generate content hash for deduplication (use first 500 chars of body)
            body_for_hash = section_content[:500] if len(section_content) > 500 else section_content
            content_hash = hashlib.md5(body_for_hash.encode()).hexdigest()[:16]
            page_key = (page_start, page_end, content_hash)

            # Skip if this page range with similar content already exists
            if page_key in used_page_ranges:
                logger.debug(f"Skipping duplicate chunk: section {section.id} pages {page_start}-{page_end}")
                continue

            used_page_ranges.add(page_key)

            # If section fits in one chunk
            if len(section_content) <= max_size:
                # Add section header to content
                header = f"[{section.id}. {section.title}]\n\n"
                plans.append(ChunkPlan(
                    chunk_type=ChunkType.TEXT_CHUNK,
                    content=header + section_content,
                    page_start=page_start,
                    page_end=page_end,
                    section_path=section.id,
                    section_title=section.title,
                    parent_section_id=section.parent_id
                ))
            else:
                # Split large section with page position tracking
                sub_plans = self._split_section(
                    section_content, section, page_start, page_end, max_size,
                    page_positions=page_positions,
                    section_start_offset=section_start
                )
                plans.extend(sub_plans)

        return plans

    async def _create_semantic_plan(
        self,
        pages_text: List[Tuple[int, str]],
        max_size: int,
        min_size: int
    ) -> List[ChunkPlan]:
        """Create chunk plan based on semantic boundaries (no section info)."""
        plans = []

        for page_num, page_text in pages_text:
            # Find natural break points
            paragraphs = re.split(r'\n\s*\n', page_text)

            current_content = ""
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                # Check if adding this paragraph exceeds max size
                if len(current_content) + len(para) + 2 > max_size:
                    # Save current content if large enough
                    if len(current_content) >= min_size:
                        plans.append(ChunkPlan(
                            chunk_type=ChunkType.TEXT_CHUNK,
                            content=current_content,
                            page_start=page_num,
                            page_end=page_num
                        ))
                    current_content = para
                else:
                    if current_content:
                        current_content += "\n\n" + para
                    else:
                        current_content = para

            # Save remaining content
            if len(current_content) >= min_size:
                plans.append(ChunkPlan(
                    chunk_type=ChunkType.TEXT_CHUNK,
                    content=current_content,
                    page_start=page_num,
                    page_end=page_num
                ))

        return plans

    async def _extract_table_plans(
        self,
        pages_text: List[Tuple[int, str]]
    ) -> List[ChunkPlan]:
        """Extract tables as separate chunk plans."""
        plans = []

        for page_num, text in pages_text:
            # Find markdown-style tables
            table_pattern = r'(\|[^\n]+\|\n)+(\|[\-:]+\|[\-:|\s]+\n)?(\|[^\n]+\|\n)+'
            for match in re.finditer(table_pattern, text):
                table_content = match.group(0).strip()
                if len(table_content) > 20:  # Minimum table size
                    plans.append(ChunkPlan(
                        chunk_type=ChunkType.TABLE_CHUNK,
                        content=table_content,
                        page_start=page_num,
                        page_end=page_num,
                        metadata={"source": "table_extraction"}
                    ))

        return plans

    def _split_section(
        self,
        content: str,
        section: SectionInfo,
        page_start: int,
        page_end: int,
        max_size: int,
        page_positions: Dict[int, int] = None,
        section_start_offset: int = 0
    ) -> List[ChunkPlan]:
        """Split a large section into multiple chunks with accurate page tracking."""
        plans = []
        header = f"[{section.id}. {section.title}]\n\n"
        header_len = len(header)
        available_size = max_size - header_len

        start = 0
        chunk_index = 0

        while start < len(content):
            end = min(start + available_size, len(content))

            # Find natural break point if not at end
            if end < len(content):
                # Try to break at paragraph
                last_para = content.rfind('\n\n', start, end)
                if last_para > start + available_size * 0.5:
                    end = last_para

                # Otherwise try sentence
                else:
                    for ending in self.SENTENCE_ENDINGS:
                        last_sentence = content.rfind(ending, start, end)
                        if last_sentence > start + available_size * 0.5:
                            end = last_sentence + len(ending)
                            break

            chunk_content = content[start:end].strip()
            if chunk_content:
                # Calculate accurate page range for this sub-chunk
                if page_positions:
                    chunk_page_start = self._get_page_at_position(
                        page_positions, section_start_offset + start
                    )
                    chunk_page_end = self._get_page_at_position(
                        page_positions, section_start_offset + end - 1
                    )
                else:
                    # Fallback: estimate page based on position ratio
                    total_chars = len(content)
                    total_pages = page_end - page_start + 1
                    chunk_page_start = page_start + int((start / total_chars) * total_pages)
                    chunk_page_end = page_start + int((end / total_chars) * total_pages)
                    chunk_page_start = max(page_start, min(chunk_page_start, page_end))
                    chunk_page_end = max(page_start, min(chunk_page_end, page_end))

                plans.append(ChunkPlan(
                    chunk_type=ChunkType.TEXT_CHUNK,
                    content=header + chunk_content,
                    page_start=chunk_page_start,
                    page_end=chunk_page_end,
                    section_path=section.id,
                    section_title=section.title,
                    parent_section_id=section.parent_id,
                    metadata={"chunk_index": chunk_index}
                ))
                chunk_index += 1

            # Move to next position with overlap
            start = end - self.overlap_size if end < len(content) else len(content)

        return plans

    def _find_section_start(self, text: str, section: SectionInfo) -> int:
        """Find the start position of a section in text, skipping TOC entries."""
        # Try exact match first
        pattern = re.escape(f"{section.id}") + r'[\.\s]+' + re.escape(section.title[:20])

        # Find ALL occurrences and filter out TOC entries
        for match in re.finditer(pattern, text):
            if not self._is_toc_entry(text, match.start()):
                return match.start()

        # Try title only (skip TOC)
        for match in re.finditer(re.escape(section.title[:30]), text):
            if not self._is_toc_entry(text, match.start()):
                return match.start()

        return -1

    def _is_toc_entry(self, text: str, position: int) -> bool:
        """Check if the position is within a TOC entry (has page reference like '... 44')."""
        # Get the line containing this position
        line_start = text.rfind('\n', 0, position) + 1
        line_end = text.find('\n', position)
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]

        # TOC patterns: dots followed by page number, or multiple section listings
        toc_patterns = [
            r'\.{3,}\s*\d+',           # ... 44
            r'\.{2,}\s*\d+',           # .. 44
            r'\s{3,}\d+$',             # spaces followed by page number at end
            r'\d+\.\d+\.\s+.+\.{2,}',  # section.subsec. title ... pattern
        ]

        for pattern in toc_patterns:
            if re.search(pattern, line):
                return True

        return False

    def _get_page_at_position(
        self,
        page_positions: Dict[int, int],
        char_pos: int
    ) -> int:
        """Get page number for a character position."""
        result = 1
        for pos, page_num in sorted(page_positions.items()):
            if pos <= char_pos:
                result = page_num
            else:
                break
        return result

    def _get_parent_section_path(self, section_path: str) -> Optional[str]:
        """Get parent section path (e.g., '2.3.1' -> '2.3')."""
        parts = section_path.split('.')
        if len(parts) > 1:
            return '.'.join(parts[:-1])
        return None

    def _is_error_reference_document(self, full_text: str, filename: str = "") -> bool:
        """
        Check if document is an Error Reference Guide.
        에러 참조 가이드 문서인지 확인

        Args:
            full_text: Full document text
            filename: Optional filename for detection

        Returns:
            True if document appears to be an error reference
        """
        # Check filename
        filename_lower = filename.lower()
        if any(kw.lower() in filename_lower for kw in ['error', 'エラー', '에러']):
            return True

        # Check document content for keywords
        text_sample = full_text[:5000]  # Check first 5000 chars
        for keyword in self.ERROR_DOC_KEYWORDS:
            if keyword.lower() in text_sample.lower():
                return True

        # Check for high density of error code patterns
        error_count = 0
        combined_pattern = '|'.join(self.ERROR_CODE_PATTERNS)
        matches = re.findall(combined_pattern, full_text[:20000], re.IGNORECASE)
        error_count = len(matches)

        # If more than 10 error codes in first 20K chars, likely error reference
        if error_count >= 10:
            logger.info(f"Detected error reference document: {error_count} error codes found")
            return True

        return False

    def _extract_error_code_from_text(self, text: str) -> Optional[str]:
        """
        Extract primary error code from text block.
        텍스트 블록에서 주요 에러 코드 추출

        Returns:
            Error code string like "DSALC_ERR_DATASET_NOT_FOUND (-5212)" or None
        """
        # Pattern: ERROR_NAME (negative_number)
        match = re.search(r'([A-Z][A-Z0-9_]+)\s*\((-\d+)\)', text)
        if match:
            name, code = match.groups()
            return f"{name} ({code})"

        # Pattern: PRODUCT_ERROR_NAME
        match = re.search(
            r'((?:JEUS|TIBERO|TMAX|OFM|OFCOBOL|OFASM|TLIC|DSALC|OSALC|CDSAL|TDSAL)[-_]?(?:ERR[-_])?[A-Z_]+)',
            text
        )
        if match:
            error_name = match.group(1)
            # Try to find associated number
            num_match = re.search(r'\((-?\d+)\)', text)
            if num_match:
                return f"{error_name} ({num_match.group(1)})"
            return error_name

        # Pattern: just (-XXXXX)
        match = re.search(r'\((-\d{4,5})\)', text)
        if match:
            return f"Error {match.group(1)}"

        return None

    async def _create_error_code_plan(
        self,
        pages_text: List[Tuple[int, str]],
        structure: PDFStructureAnalysis,
        filename: str = ""
    ) -> List[ChunkPlan]:
        """
        Create chunk plan specifically for error reference documents.
        에러 참조 문서용 청크 계획 생성 (에러 코드별 독립 청크)

        Each error code becomes an independent chunk with:
        - section_title: "Error: ERROR_NAME (-CODE)"
        - chunk size: 500-800 characters
        """
        plans = []

        # Build full text with page tracking
        full_text = ""
        page_positions = {}
        current_pos = 0

        for page_num, text in pages_text:
            page_positions[current_pos] = page_num
            full_text += text + "\n"
            current_pos = len(full_text)

        # Check if this is an error reference document
        if not self._is_error_reference_document(full_text, filename):
            return []  # Return empty to use default chunking

        logger.info(f"Processing as Error Reference document: {filename}")

        # Pattern to find error entry boundaries
        # Look for patterns like: ERROR_NAME (-XXXX) or section headers with error codes
        error_entry_pattern = r'(?:^|\n)([A-Z][A-Z0-9_]+\s*\(-?\d+\)|[•●■]\s*[A-Z][A-Z0-9_]+)'

        # Split by error entries
        error_matches = list(re.finditer(error_entry_pattern, full_text))

        if len(error_matches) < 5:
            # Not enough error entries found, try alternative pattern
            # Pattern for lines starting with error-like content
            alt_pattern = r'\n([A-Z][A-Z0-9_]{3,}[^a-z\n]{0,50}(?:\(-?\d+\))?)'
            error_matches = list(re.finditer(alt_pattern, full_text))

        if len(error_matches) < 5:
            logger.info("Not enough error entries for error-specific chunking, using default")
            return []

        logger.info(f"Found {len(error_matches)} potential error entries")

        # Process each error entry
        for i, match in enumerate(error_matches):
            start = match.start()

            # Find end (next error entry or +800 chars max)
            if i + 1 < len(error_matches):
                end = min(error_matches[i + 1].start(), start + 800)
            else:
                end = min(start + 800, len(full_text))

            # Ensure minimum content (at least 100 chars)
            content = full_text[start:end].strip()
            if len(content) < 100:
                # Try to extend to next paragraph
                extended_end = full_text.find('\n\n', end)
                if extended_end > 0 and extended_end < start + 1000:
                    content = full_text[start:extended_end].strip()

            if len(content) < 50:
                continue

            # Extract error code for section title
            error_code = self._extract_error_code_from_text(content)
            if not error_code:
                # Use first line as fallback
                first_line = content.split('\n')[0][:60]
                error_code = first_line

            section_title = f"Error: {error_code}"

            # Get page number
            page_num = self._get_page_at_position(page_positions, start)

            plans.append(ChunkPlan(
                chunk_type=ChunkType.TEXT_CHUNK,
                content=content,
                page_start=page_num,
                page_end=page_num,
                section_path=f"error_{i:04d}",
                section_title=section_title,
                metadata={
                    "error_code": error_code,
                    "chunk_strategy": "error_code_independent"
                }
            ))

        logger.info(f"Created {len(plans)} error-specific chunks")
        return plans


def create_chunk_from_plan(
    plan: ChunkPlan,
    pdf_id: str,
    chunk_index: int
) -> AdaptiveChunk:
    """
    Create an AdaptiveChunk from a ChunkPlan.

    Args:
        plan: The chunk plan
        pdf_id: Document ID
        chunk_index: Index for generating chunk ID
    """
    chunk_id = f"chunk_{pdf_id}_{chunk_index:04d}"
    content_hash = hashlib.sha256(plan.content.encode()).hexdigest()

    return AdaptiveChunk(
        pdf_id=pdf_id,
        chunk_id=chunk_id,
        chunk_type=plan.chunk_type,
        content=plan.content,
        page_start=plan.page_start,
        page_end=plan.page_end,
        section_path=plan.section_path,
        section_title=plan.section_title,
        parent_section_id=plan.parent_section_id,
        relations=ChunkRelations(),
        content_hash=content_hash,
        metadata=plan.metadata
    )


# Singleton instance
_planner: Optional[AdaptiveChunkPlanner] = None


def get_adaptive_chunk_planner(
    max_chunk_size: int = None,
    min_chunk_size: int = None,
    overlap_size: int = None
) -> AdaptiveChunkPlanner:
    """Get or create adaptive chunk planner instance."""
    global _planner
    if _planner is None:
        _planner = AdaptiveChunkPlanner(
            max_chunk_size=max_chunk_size,
            min_chunk_size=min_chunk_size,
            overlap_size=overlap_size
        )
    return _planner
