"""
Figure Reference Extractor Service
Extracts figure references (図1.1, Figure 1-1, 그림 1.1) from documents
and matches them to extracted images.
"""
import re
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


@dataclass
class FigureReference:
    """Represents a figure reference found in text"""
    reference: str  # e.g., "図1.1", "Figure 1-1"
    normalized: str  # e.g., "fig_1_1" for matching
    page_number: int
    position: int  # character position in text
    caption: Optional[str] = None


@dataclass
class FigureImageMapping:
    """Maps a figure reference to an image"""
    reference: str
    normalized: str
    image_index: int
    page_number: int
    caption: Optional[str] = None
    confidence: float = 0.0


class FigureReferenceExtractor:
    """
    Extracts figure references from document text and matches them to images.

    Supports patterns:
    - Japanese: 図1.1, 図 1-1, 図1
    - English: Figure 1.1, Fig. 1-1, Fig 1
    - Korean: 그림 1.1, 그림1-1
    """

    # Figure reference patterns for different languages
    PATTERNS = [
        # Japanese: 図1.1, 図 1-1, 図1, 図１.１ (full-width numbers)
        r'図\s*([0-9０-９]+)[.\-－。．]?([0-9０-９]*)',
        # English: Figure 1.1, Fig. 1-1, Fig 1
        r'(?:Figure|Fig\.?)\s*([0-9]+)[.\-]?([0-9]*)',
        # Korean: 그림 1.1, 그림1-1
        r'그림\s*([0-9]+)[.\-]?([0-9]*)',
    ]

    # Caption patterns - text following figure references
    CAPTION_PATTERNS = [
        # "図1.1: Caption text" or "図1.1 - Caption text"
        r'(?:図|Figure|Fig\.?|그림)\s*[0-9０-９]+[.\-]?[0-9]*\s*[:：\-－]\s*([^\n]{5,100})',
        # "Caption text" on next line after figure
        r'(?:図|Figure|Fig\.?|그림)\s*[0-9０-９]+[.\-]?[0-9]*\s*\n\s*([^\n]{5,100})',
    ]

    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.PATTERNS]
        self.compiled_caption_patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.CAPTION_PATTERNS]

    def extract_references(self, pages: List[Dict[str, Any]]) -> List[FigureReference]:
        """
        Extract figure references from all pages.

        Args:
            pages: List of page dicts with 'page_number' and 'content' keys

        Returns:
            List of FigureReference objects sorted by page and position
        """
        all_refs = []

        for page in pages:
            page_num = page.get("page_number", 0)
            content = page.get("content", "")

            if not content:
                continue

            # Find all figure references in this page
            for pattern in self.compiled_patterns:
                for match in pattern.finditer(content):
                    ref_text = match.group(0).strip()
                    major = self._normalize_number(match.group(1))
                    minor = self._normalize_number(match.group(2)) if match.lastindex >= 2 and match.group(2) else ""

                    # Create normalized reference for matching
                    if minor:
                        normalized = f"fig_{major}_{minor}"
                    else:
                        normalized = f"fig_{major}"

                    # Try to extract caption
                    caption = self._extract_caption(content, match.start())

                    ref = FigureReference(
                        reference=ref_text,
                        normalized=normalized,
                        page_number=page_num,
                        position=match.start(),
                        caption=caption
                    )

                    # Avoid duplicates on same page
                    if not any(r.normalized == normalized and r.page_number == page_num for r in all_refs):
                        all_refs.append(ref)
                        logger.debug(f"Found figure reference: {ref_text} -> {normalized} on page {page_num}")

        # Sort by page number then position
        all_refs.sort(key=lambda r: (r.page_number, r.position))

        return all_refs

    def _normalize_number(self, num_str: str) -> str:
        """Convert full-width numbers to half-width"""
        if not num_str:
            return ""
        # Full-width to half-width mapping
        fw_to_hw = str.maketrans('０１２３４５６７８９', '0123456789')
        return num_str.translate(fw_to_hw)

    def _extract_caption(self, content: str, ref_position: int) -> Optional[str]:
        """Try to extract caption text near a figure reference"""
        # Look at text starting from the reference position
        search_text = content[ref_position:ref_position + 200]

        for pattern in self.compiled_caption_patterns:
            match = pattern.search(search_text)
            if match:
                caption = match.group(1).strip()
                # Clean up caption
                caption = re.sub(r'\s+', ' ', caption)
                if len(caption) > 10:  # Minimum caption length
                    return caption

        return None

    def match_to_images(
        self,
        references: List[FigureReference],
        images: List[Dict[str, Any]]
    ) -> List[FigureImageMapping]:
        """
        Match figure references to images based on page proximity.

        Strategy:
        1. For each reference, find images on the same page
        2. If multiple images on same page, match in order of appearance
        3. If no image on same page, check next page

        Args:
            references: List of FigureReference objects
            images: List of image dicts with 'page_number' key

        Returns:
            List of FigureImageMapping objects
        """
        mappings = []
        used_images = set()

        # Group images by page
        images_by_page: Dict[int, List[Tuple[int, Dict]]] = {}
        for idx, img in enumerate(images):
            page = img.get("page_number", 0)
            if page not in images_by_page:
                images_by_page[page] = []
            images_by_page[page].append((idx, img))

        # Match each reference to an image
        for ref in references:
            best_match = None
            best_confidence = 0.0

            # First, try same page
            if ref.page_number in images_by_page:
                for idx, img in images_by_page[ref.page_number]:
                    if idx not in used_images:
                        best_match = idx
                        best_confidence = 1.0
                        break

            # Try next page if no match
            if best_match is None and (ref.page_number + 1) in images_by_page:
                for idx, img in images_by_page[ref.page_number + 1]:
                    if idx not in used_images:
                        best_match = idx
                        best_confidence = 0.8
                        break

            # Try previous page as last resort
            if best_match is None and (ref.page_number - 1) in images_by_page:
                for idx, img in images_by_page[ref.page_number - 1]:
                    if idx not in used_images:
                        best_match = idx
                        best_confidence = 0.6
                        break

            if best_match is not None:
                used_images.add(best_match)
                mapping = FigureImageMapping(
                    reference=ref.reference,
                    normalized=ref.normalized,
                    image_index=best_match,
                    page_number=ref.page_number,
                    caption=ref.caption,
                    confidence=best_confidence
                )
                mappings.append(mapping)
                logger.debug(f"Matched {ref.reference} to image {best_match} with confidence {best_confidence}")

        return mappings


class FigureReferenceDetector:
    """
    Detects figure references in LLM response text.
    Used to find which figures are mentioned so their images can be displayed.
    """

    # Patterns to detect figure mentions in response text
    DETECTION_PATTERNS = [
        r'図\s*([0-9０-９]+)[.\-－。．]?([0-9０-９]*)',
        r'(?:Figure|Fig\.?)\s*([0-9]+)[.\-]?([0-9]*)',
        r'그림\s*([0-9]+)[.\-]?([0-9]*)',
    ]

    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.DETECTION_PATTERNS]

    def detect_references(self, text: str) -> List[str]:
        """
        Detect figure references in text.

        Args:
            text: LLM response text

        Returns:
            List of normalized reference strings (e.g., ["fig_1_1", "fig_2"])
        """
        found = set()

        for pattern in self.compiled_patterns:
            for match in pattern.finditer(text):
                major = self._normalize_number(match.group(1))
                minor = self._normalize_number(match.group(2)) if match.lastindex >= 2 and match.group(2) else ""

                if minor:
                    normalized = f"fig_{major}_{minor}"
                else:
                    normalized = f"fig_{major}"

                found.add(normalized)

        result = list(found)
        if result:
            logger.debug(f"Detected figure references in response: {result}")

        return result

    def _normalize_number(self, num_str: str) -> str:
        """Convert full-width numbers to half-width"""
        if not num_str:
            return ""
        fw_to_hw = str.maketrans('０１２３４５６７８９', '0123456789')
        return num_str.translate(fw_to_hw)


# Singleton instances
_extractor: Optional[FigureReferenceExtractor] = None
_detector: Optional[FigureReferenceDetector] = None


def get_figure_extractor() -> FigureReferenceExtractor:
    """Get singleton FigureReferenceExtractor instance"""
    global _extractor
    if _extractor is None:
        _extractor = FigureReferenceExtractor()
    return _extractor


def get_figure_detector() -> FigureReferenceDetector:
    """Get singleton FigureReferenceDetector instance"""
    global _detector
    if _detector is None:
        _detector = FigureReferenceDetector()
    return _detector
