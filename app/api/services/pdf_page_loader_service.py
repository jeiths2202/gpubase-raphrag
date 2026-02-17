"""
PDF Page Loader Service

Loads specific pages from PDF files on demand.
Used by Summary-First RAG to fetch original content when summary matches are found.

Features:
- LRU cache for frequently accessed pages
- Context-aware loading (surrounding pages)
- Table structure preservation
- Async-compatible interface
"""

import logging
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from functools import lru_cache
import asyncio
from collections import OrderedDict

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    """Content extracted from a PDF page"""
    page_number: int
    text: str
    tables: List[str] = field(default_factory=list)  # Markdown tables
    images: List[Dict[str, Any]] = field(default_factory=list)  # Image metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_tables(self) -> bool:
        return bool(self.tables)

    @property
    def has_images(self) -> bool:
        return bool(self.images)

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def to_context_string(self) -> str:
        """Format page content for LLM context"""
        parts = [f"[Page {self.page_number}]", self.text]

        if self.tables:
            parts.append("\n[Tables]")
            for table in self.tables:
                parts.append(table)

        return "\n".join(parts)


class LRUCache:
    """Thread-safe LRU cache for page content"""

    def __init__(self, max_size: int = 100):
        self._cache: OrderedDict[str, PageContent] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[PageContent]:
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    async def set(self, key: str, value: PageContent):
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = value

    async def clear(self):
        async with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class PDFPageLoaderService:
    """
    Loads specific pages from PDF files on demand.

    This service is used when Summary-First search finds a match
    and we need to fetch the original PDF content for that page.
    """

    def __init__(
        self,
        uploads_dir: Optional[Path] = None,
        cache_size: int = 100,
    ):
        """
        Initialize PDF page loader.

        Args:
            uploads_dir: Base directory for PDF files
            cache_size: LRU cache size for page content
        """
        self.uploads_dir = uploads_dir or Path("/opt/kms/uploads")
        self._cache = LRUCache(max_size=cache_size)
        self._pdf_cache: Dict[str, Any] = {}  # Cache for PDF document objects

    def _find_pdf_path(self, pdf_name: str) -> Optional[Path]:
        """
        Find PDF file path by name.

        Searches in uploads directory and subdirectories.

        Args:
            pdf_name: PDF filename or partial path

        Returns:
            Full path to PDF file or None if not found
        """
        # Direct path
        if Path(pdf_name).exists():
            return Path(pdf_name)

        # Search in uploads directory
        search_paths = [
            self.uploads_dir / pdf_name,
            self.uploads_dir / "documents" / pdf_name,
            self.uploads_dir / "pdfs" / pdf_name,
        ]

        for path in search_paths:
            if path.exists():
                return path

        # Recursive search (limited depth)
        try:
            for pdf_path in self.uploads_dir.rglob(f"*{pdf_name}"):
                if pdf_path.suffix.lower() == '.pdf':
                    return pdf_path
        except Exception as e:
            logger.warning(f"PDF search error: {e}")

        return None

    async def load_pages(
        self,
        pdf_path: str,
        page_numbers: List[int],
    ) -> List[PageContent]:
        """
        Extract full text from specific PDF pages.

        Args:
            pdf_path: Path to PDF file (can be filename or full path)
            page_numbers: List of page numbers to extract (1-indexed)

        Returns:
            List of PageContent for each requested page
        """
        # Find actual PDF path
        actual_path = self._find_pdf_path(pdf_path)
        if not actual_path:
            logger.warning(f"PDF not found: {pdf_path}")
            return []

        results = []

        # Check cache first
        cache_hits = []
        cache_misses = []
        for page_num in page_numbers:
            cache_key = f"{actual_path}:{page_num}"
            cached = await self._cache.get(cache_key)
            if cached:
                cache_hits.append((page_num, cached))
            else:
                cache_misses.append(page_num)

        # Add cached results
        for page_num, content in cache_hits:
            results.append(content)

        # Load uncached pages
        if cache_misses:
            try:
                # Open PDF (async-compatible via executor)
                loop = asyncio.get_event_loop()
                new_pages = await loop.run_in_executor(
                    None,
                    self._load_pages_sync,
                    actual_path,
                    cache_misses
                )

                for page_content in new_pages:
                    # Cache the result
                    cache_key = f"{actual_path}:{page_content.page_number}"
                    await self._cache.set(cache_key, page_content)
                    results.append(page_content)

            except Exception as e:
                logger.error(f"Failed to load PDF pages: {e}")

        # Sort by page number
        results.sort(key=lambda p: p.page_number)
        return results

    def _load_pages_sync(self, pdf_path: Path, page_numbers: List[int]) -> List[PageContent]:
        """
        Synchronous page loading (called via executor).

        Args:
            pdf_path: Path to PDF file
            page_numbers: Page numbers to load (1-indexed)

        Returns:
            List of PageContent
        """
        from . import pdf_compat

        results = []
        path_str = str(pdf_path)

        try:
            total_pages = pdf_compat.get_page_count(path_str)

            for page_num in page_numbers:
                # Convert to 0-indexed
                idx = page_num - 1

                if idx < 0 or idx >= total_pages:
                    logger.warning(f"Page {page_num} out of range for {pdf_path} (total: {total_pages})")
                    continue

                try:
                    # Extract text
                    text = pdf_compat.extract_text_plain(path_str, idx)

                    # Extract tables (attempt structured extraction)
                    tables = self._extract_tables_from_path(path_str, idx)

                    # Extract image metadata
                    images = []
                    for img_index, img in enumerate(pdf_compat.get_images_metadata(path_str, idx)):
                        images.append({
                            "index": img_index,
                            "xref": img[0],
                            "width": img[2],
                            "height": img[3],
                        })

                    # Page metadata
                    pw, ph = pdf_compat.get_page_dimensions(path_str, idx)
                    metadata = {
                        "pdf_path": path_str,
                        "total_pages": total_pages,
                        "page_width": pw,
                        "page_height": ph,
                    }

                    results.append(PageContent(
                        page_number=page_num,
                        text=text.strip(),
                        tables=tables,
                        images=images,
                        metadata=metadata
                    ))

                except Exception as e:
                    logger.warning(f"Failed to extract page {page_num} from {pdf_path}: {e}")

        except Exception as e:
            logger.error(f"Failed to open PDF {pdf_path}: {e}")

        return results

    def _extract_tables_from_path(self, pdf_path: str, page_num: int) -> List[str]:
        """
        Attempt to extract table structures from a PDF page.

        Uses pdf_compat dict-style text extraction with block analysis
        to identify table-like structures.

        Args:
            pdf_path: Path to PDF file
            page_num: 0-indexed page number

        Returns:
            List of markdown-formatted tables
        """
        from . import pdf_compat
        tables = []

        try:
            page_dict = pdf_compat.extract_text_dict(pdf_path, page_num)
            blocks = page_dict.get("blocks", [])

            for block in blocks:
                if block.get("type") == 0:  # Text block
                    lines = block.get("lines", [])
                    if len(lines) >= 3:
                        if self._looks_like_table(lines):
                            table_text = self._extract_table_text(lines)
                            if table_text:
                                tables.append(table_text)

        except Exception as e:
            logger.debug(f"Table extraction failed: {e}")

        return tables

    def _looks_like_table(self, lines: List[Dict]) -> bool:
        """Check if lines look like a table structure"""
        if len(lines) < 2:
            return False

        # Check for consistent column structure
        x_positions = []
        for line in lines[:3]:
            spans = line.get("spans", [])
            xs = [span.get("bbox", [0])[0] for span in spans]
            x_positions.append(set(int(x / 10) * 10 for x in xs))  # Bucket by 10 pixels

        if not x_positions:
            return False

        # If first few lines have similar x-positions, likely a table
        common = x_positions[0]
        for xset in x_positions[1:]:
            common = common & xset

        return len(common) >= 2

    def _extract_table_text(self, lines: List[Dict]) -> Optional[str]:
        """Convert table lines to markdown format"""
        try:
            rows = []
            for line in lines:
                cells = []
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text:
                        cells.append(text)
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")

            if len(rows) >= 2:
                # Add separator after first row (header)
                separator = "| " + " | ".join(["---"] * len(rows[0].split("|")[1:-1])) + " |"
                result = [rows[0], separator] + rows[1:]
                return "\n".join(result)

        except Exception as e:
            logger.debug(f"Table formatting failed: {e}")

        return None

    async def load_page_with_context(
        self,
        pdf_path: str,
        page_number: int,
        context_pages: int = 1,
    ) -> List[PageContent]:
        """
        Load a page with surrounding context pages.

        Useful when a summary reference points to a specific page,
        but related content may span multiple pages.

        Args:
            pdf_path: Path to PDF file
            page_number: Central page number (1-indexed)
            context_pages: Number of pages before and after to include

        Returns:
            List of PageContent for requested range
        """
        page_numbers = list(range(
            max(1, page_number - context_pages),
            page_number + context_pages + 1
        ))
        return await self.load_pages(pdf_path, page_numbers)

    async def get_page_text(
        self,
        pdf_path: str,
        page_number: int,
    ) -> Optional[str]:
        """
        Get just the text content from a single page.

        Convenience method for simple text retrieval.

        Args:
            pdf_path: Path to PDF file
            page_number: Page number (1-indexed)

        Returns:
            Text content or None if not found
        """
        pages = await self.load_pages(pdf_path, [page_number])
        if pages:
            return pages[0].text
        return None

    async def clear_cache(self):
        """Clear the page content cache"""
        await self._cache.clear()
        self._pdf_cache.clear()
        logger.info("PDF page cache cleared")

    @property
    def cache_size(self) -> int:
        """Get current cache size"""
        return self._cache.size


# Singleton instance
_pdf_loader: Optional[PDFPageLoaderService] = None


def get_pdf_page_loader_service() -> PDFPageLoaderService:
    """Get or create singleton PDFPageLoaderService instance"""
    global _pdf_loader
    if _pdf_loader is None:
        _pdf_loader = PDFPageLoaderService()
    return _pdf_loader
