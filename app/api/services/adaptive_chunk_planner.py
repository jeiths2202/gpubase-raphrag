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

    def __init__(
        self,
        max_chunk_size: int = 1500,
        min_chunk_size: int = 100,
        overlap_size: int = 100,
        preserve_tables: bool = True,
        preserve_sections: bool = True
    ):
        """
        Initialize planner.

        Args:
            max_chunk_size: Maximum chunk size in characters
            min_chunk_size: Minimum chunk size in characters
            overlap_size: Overlap between adjacent chunks
            preserve_tables: Keep tables as single chunks
            preserve_sections: Respect section boundaries
        """
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

        plans = []

        if preserve_sections and structure.hierarchy:
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
                # Split large section
                sub_plans = self._split_section(
                    section_content, section, page_start, page_end, max_size
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
        max_size: int
    ) -> List[ChunkPlan]:
        """Split a large section into multiple chunks."""
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
                plans.append(ChunkPlan(
                    chunk_type=ChunkType.TEXT_CHUNK,
                    content=header + chunk_content,
                    page_start=page_start,
                    page_end=page_end,
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
        """Find the start position of a section in text."""
        # Try exact match first
        pattern = re.escape(f"{section.id}") + r'[\.\s]+' + re.escape(section.title[:20])
        match = re.search(pattern, text)
        if match:
            return match.start()

        # Try title only
        title_match = re.search(re.escape(section.title[:30]), text)
        if title_match:
            return title_match.start()

        return -1

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
    max_chunk_size: int = 1500,
    min_chunk_size: int = 100,
    overlap_size: int = 100
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
