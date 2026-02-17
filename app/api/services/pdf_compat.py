"""
PDF Compatibility Layer

pypdfium2 (Apache 2.0) + pdfplumber (MIT) wrapper that replaces PyMuPDF (AGPL v3).
All PDF operations are accessed through stateless functions that accept path + page_num.

Functions:
    open_pdf_toc       — TOC extraction (pypdfium2)
    get_page_count     — page count (pypdfium2)
    get_shaded_rects   — shaded/code-block rectangles (pdfplumber)
    extract_text_plain — plain text extraction (pdfplumber)
    extract_text_dict  — dict-style text with bbox (pdfplumber)
    find_tables        — table extraction (pdfplumber)
    get_images_metadata— image info list (pdfplumber)
    extract_image      — single image bitmap (pypdfium2)
    render_page_png    — page → PNG bytes (pypdfium2)
    get_page_dimensions— page width/height (pypdfium2)
"""
import io
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# pypdfium2 helpers
# ---------------------------------------------------------------------------

def _open_pdfium(path: str):
    """Open a PDF with pypdfium2. Caller must close the returned document."""
    import pypdfium2 as pdfium
    return pdfium.PdfDocument(path)


def open_pdf_toc(path: str) -> List[Tuple[int, str, int]]:
    """
    Extract the Table of Contents (bookmarks).

    Returns list of (level, title, page_number_1based) matching PyMuPDF's get_toc() format.
    """
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    toc: List[Tuple[int, str, int]] = []
    try:
        for item in doc.get_toc():
            level = item.n_count  # nesting level (0-based in pdfium, 1-based in PyMuPDF)
            title = item.title or ""
            # page index is 0-based in pypdfium2; PyMuPDF returns 1-based
            page_idx = item.page_index
            if page_idx is None or page_idx < 0:
                page_idx = 0
            toc.append((level + 1, title, page_idx + 1))
    except Exception as e:
        logger.debug(f"TOC extraction failed for {path}: {e}")
    finally:
        doc.close()
    return toc


def get_page_count(path: str) -> int:
    """Return total number of pages."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    try:
        return len(doc)
    finally:
        doc.close()


def get_page_dimensions(path: str, page_num: int) -> Tuple[float, float]:
    """
    Return (width, height) in points for the given 0-indexed page.
    """
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    try:
        page = doc[page_num]
        return page.get_width(), page.get_height()
    finally:
        doc.close()


def render_page_png(path: str, page_num: int, zoom: float = 2.0) -> bytes:
    """
    Render a 0-indexed page to PNG bytes at the given zoom factor.

    zoom=2.0 ≈ 144 DPI (PyMuPDF's Matrix(2,2)).
    """
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    try:
        page = doc[page_num]
        bitmap = page.render(scale=zoom)
        pil_image = bitmap.to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# pdfplumber helpers
# ---------------------------------------------------------------------------

def _open_plumber(path: str):
    """Open a PDF with pdfplumber. Caller must close the returned object."""
    import pdfplumber
    return pdfplumber.open(path)


def get_shaded_rects(path: str, page_num: int) -> Tuple[list, int]:
    """
    Detect shaded (code-block) rectangles on a 0-indexed page.

    Replaces PyMuPDF's page.get_drawings() approach.

    Returns:
        (shaded_rects, drawing_count) where each rect is a dict with
        keys x0, y0, x1, y1 (matching pdfplumber rect format).
    """
    import pdfplumber
    pdf = pdfplumber.open(path)
    try:
        if page_num >= len(pdf.pages):
            return [], 0
        page = pdf.pages[page_num]
        rects_raw = page.rects or []
        drawing_count = len(rects_raw)
        shaded: list = []

        for r in rects_raw:
            fill = r.get("non_stroking_color")
            if fill is None:
                continue

            x0 = float(r.get("x0", 0))
            y0 = float(r.get("top", 0))
            x1 = float(r.get("x1", 0))
            y1 = float(r.get("bottom", 0))
            w = x1 - x0
            h = y1 - y0

            if w < 200 or h < 15:
                continue

            # Normalize fill to RGB floats
            if isinstance(fill, (list, tuple)):
                if len(fill) >= 3:
                    fr, fg, fb = float(fill[0]), float(fill[1]), float(fill[2])
                elif len(fill) == 1:
                    fr = fg = fb = float(fill[0])
                else:
                    continue
            elif isinstance(fill, (int, float)):
                fr = fg = fb = float(fill)
            else:
                continue

            # pdfplumber gives colors in 0-1 range (or 0-255 for some PDFs)
            # Normalize to 0-1 if needed
            if fr > 1.0 or fg > 1.0 or fb > 1.0:
                fr, fg, fb = fr / 255.0, fg / 255.0, fb / 255.0

            # Skip white (>0.98) and black (<0.05)
            if fr > 0.98 and fg > 0.98 and fb > 0.98:
                continue
            if fr < 0.05 and fg < 0.05 and fb < 0.05:
                continue

            shaded.append(_ShadedRect(x0, y0, x1, y1))

        return shaded, drawing_count
    finally:
        pdf.close()


class _ShadedRect:
    """Minimal rect class matching PyMuPDF Rect interface used in structured_knowledge_store."""
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0: float, y0: float, x1: float, y1: float):
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def extract_text_plain(path: str, page_num: int) -> str:
    """
    Extract plain text from a 0-indexed page.

    Replaces PyMuPDF's page.get_text("text").
    """
    import pdfplumber
    pdf = pdfplumber.open(path)
    try:
        if page_num >= len(pdf.pages):
            return ""
        page = pdf.pages[page_num]
        text = page.extract_text() or ""
        return text
    finally:
        pdf.close()


def extract_text_dict(path: str, page_num: int) -> Dict[str, Any]:
    """
    Extract text with block/line/span structure (dict mode).

    Replaces PyMuPDF's page.get_text("dict").
    Returns a dict with "blocks" key containing text blocks structured like PyMuPDF.
    """
    import pdfplumber
    pdf = pdfplumber.open(path)
    try:
        if page_num >= len(pdf.pages):
            return {"blocks": []}
        page = pdf.pages[page_num]
        words = page.extract_words(
            keep_blank_chars=True,
            extra_attrs=["fontname", "size"],
        )

        # Group words into lines by y-coordinate proximity
        if not words:
            return {"blocks": []}

        # Sort by top then x0
        words.sort(key=lambda w: (round(w["top"], 1), w["x0"]))

        # Group into lines (words with similar top coordinate)
        lines: list = []
        current_line: list = []
        current_top = None
        LINE_TOLERANCE = 3.0  # pixels

        for w in words:
            wtop = w["top"]
            if current_top is None or abs(wtop - current_top) > LINE_TOLERANCE:
                if current_line:
                    lines.append(current_line)
                current_line = [w]
                current_top = wtop
            else:
                current_line.append(w)
        if current_line:
            lines.append(current_line)

        # Build PyMuPDF-compatible blocks structure
        blocks = []
        for line_words in lines:
            if not line_words:
                continue

            # Calculate line bbox
            x0 = min(w["x0"] for w in line_words)
            y0 = min(w["top"] for w in line_words)
            x1 = max(w["x1"] for w in line_words)
            y1 = max(w["bottom"] for w in line_words)

            # Build spans from words
            spans = []
            for w in line_words:
                spans.append({
                    "text": w["text"],
                    "bbox": (w["x0"], w["top"], w["x1"], w["bottom"]),
                    "font": w.get("fontname", ""),
                    "size": w.get("size", 0),
                })

            blocks.append({
                "type": 0,  # text block
                "bbox": (x0, y0, x1, y1),
                "lines": [{
                    "bbox": (x0, y0, x1, y1),
                    "spans": spans,
                }],
            })

        return {"blocks": blocks}
    finally:
        pdf.close()


def find_tables(path: str, page_num: int) -> list:
    """
    Extract tables from a 0-indexed page.

    Returns list of table objects, each with:
        - .extract() method returning list of rows (list of cells)
        - .bbox attribute (x0, y0, x1, y1)

    Replaces PyMuPDF's page.find_tables().
    """
    import pdfplumber
    pdf = pdfplumber.open(path)
    try:
        if page_num >= len(pdf.pages):
            return []
        page = pdf.pages[page_num]
        tables_raw = page.find_tables() or []
        result = []
        for t in tables_raw:
            result.append(_PlumberTable(t))
        return result
    finally:
        pdf.close()


class _PlumberTable:
    """Wrapper matching PyMuPDF table interface (extract() + bbox)."""

    def __init__(self, plumber_table):
        self._table = plumber_table
        # pdfplumber Table has .bbox as (x0, top, x1, bottom)
        self.bbox = plumber_table.bbox

    def extract(self) -> list:
        """Return list of rows, each row is a list of cell strings."""
        return self._table.extract()


def get_images_metadata(path: str, page_num: int) -> list:
    """
    Get image metadata from a 0-indexed page.

    Returns list of dicts with keys:
        xref, width, height, name, bpc, colorspace, ...

    Replaces PyMuPDF's page.get_images(full=True).
    Each item is a tuple-like: (xref, smask, width, height, bpc, colorspace, ..., name, filter, referencer)
    to match PyMuPDF format where img[0]=xref, img[2]=width, img[3]=height.
    """
    import pdfplumber
    pdf = pdfplumber.open(path)
    try:
        if page_num >= len(pdf.pages):
            return []
        page = pdf.pages[page_num]
        images = page.images or []
        result = []
        for idx, img in enumerate(images):
            # Build a tuple matching PyMuPDF's get_images(full=True) format:
            # (xref, smask, width, height, bpc, colorspace, alt, name, filter, referencer)
            w = int(img.get("width", 0))
            h = int(img.get("height", 0))
            xref = idx  # pdfplumber doesn't have xref; use index
            result.append((xref, 0, w, h, 8, "", "", f"img_{idx}", "", ""))
        return result
    finally:
        pdf.close()


def extract_image(path: str, page_num: int, img_index: int) -> Optional[bytes]:
    """
    Extract a specific image from a page as PNG bytes.

    Uses pypdfium2 for reliable image extraction.

    Args:
        path: PDF file path
        page_num: 0-indexed page number
        img_index: image index on the page
    """
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    try:
        page = doc[page_num]
        # Get all image objects on the page
        images = list(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]))
        if img_index >= len(images):
            return None

        img_obj = images[img_index]
        bitmap = img_obj.get_bitmap()
        pil_image = bitmap.to_pil()

        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.debug(f"Image extraction failed: page={page_num}, idx={img_index}: {e}")
        return None
    finally:
        doc.close()


def extract_image_pil(path: str, page_num: int, img_index: int):
    """
    Extract a specific image from a page as a PIL Image.

    Returns (pil_image, width, height) or (None, 0, 0).
    Replaces PyMuPDF's Pixmap extraction + conversion.
    """
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(path)
    try:
        page = doc[page_num]
        images = list(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]))
        if img_index >= len(images):
            return None, 0, 0

        img_obj = images[img_index]
        bitmap = img_obj.get_bitmap()
        pil_image = bitmap.to_pil().convert("RGB")
        return pil_image, pil_image.width, pil_image.height
    except Exception as e:
        logger.debug(f"Image PIL extraction failed: page={page_num}, idx={img_index}: {e}")
        return None, 0, 0
    finally:
        doc.close()
