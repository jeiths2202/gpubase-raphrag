"""Manual loader: PDF/MD/TXT → List[ManualSection]."""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

from .config import GenerationConfig
from .models import ItemType, Language, ManualSection

logger = logging.getLogger(__name__)

# ── Product Directory Mapping ──────────────────────────────────────

DIRECTORY_TO_PRODUCT: Dict[str, str] = {
    "MVS_Openframe 7.1_v3.1.3_JP": "openframe_common_v2",
    "MSP_Openframe 7.3_v2.1.1_JP": "openframe_common_v2",
    "XSP_Openframe 7.3_v3.2.1_JP": "openframe_xsp_v2",
    "JEUS_8.5_v2.1.1_KR": "jeus_v2",
    "JEUS_8_v2.1.1_JP": "jeus_v2",
    "Tibero 7 FixSet01 Manual Set v2.1.1_jp": "tibero7_v2",
    "Tmax_6.0_v2.1.1_JP": "tmax_v2",
    "WebtoB_5Fix2_v2.1.3_JP": "webtob_v2",
    "OFAsm_4_v3.1.2_JP": "ofasm_v2",
    "OFCOBOL_4_v3.1.2_JP": "ofcobol_v2",
    "OFPli_3_v2.1.2_JP": "ofpli_v2",
    "OFStudio_7_v2.1.1_JP": "ofstudio_v2",
    "OFManager_7.2_v3.1.2_JP": "ofmanager_v2",
    "OFMiner_7Fix1_v2.1.5_JP": "ofminer_v2",
    "OFGW_7_v2.1.3_JP": "ofgw_v2",
    "ProSort_2SP3_v2.1.3_JP": "prosort_v2",
    "ProSync_FS01_JP": "prosync_v2",
    "ProTrieve_v2_1_JP": "protrieve_v2",
    "VOS3_Openframe 2.0 _v2.1.1 _JP": "openframe_vos3_v2",
}

DIRECTORY_LANGUAGE: Dict[str, Language] = {
    "JEUS_8.5_v2.1.1_KR": Language.KO,
}

PDF_COMPONENT_TO_PRODUCT: Dict[str, str] = {
    "Base": "openframe_base_v2",
    "HiDB": "openframe_hidb_v2",
    "AIM": "openframe_aim_v2",
    "Batch": "openframe_batch_v2",
    "OSC": "openframe_osc_v2",
    "OSI": "openframe_osi_v2",
    "TACF": "openframe_tacf_v2",
    "GW": "openframe_gw_v2",
    "Manager": "openframe_manager_v2",
    "NDB": "openframe_ndb_v2",
    "Common": "openframe_common_v2",
}

COMPONENT_SPLIT_DIRS = {
    "MVS_Openframe 7.1_v3.1.3_JP",
    "MSP_Openframe 7.3_v2.1.1_JP",
    "XSP_Openframe 7.3_v3.2.1_JP",
}

PRODUCT_DISPLAY_NAMES: Dict[str, str] = {
    "openframe_common_v2": "OpenFrame",
    "openframe_base_v2": "OpenFrame Base",
    "openframe_batch_v2": "OpenFrame Batch (TJES)",
    "openframe_osc_v2": "OpenFrame OSC",
    "openframe_tacf_v2": "OpenFrame TACF",
    "openframe_hidb_v2": "OpenFrame HiDB",
    "openframe_aim_v2": "OpenFrame AIM",
    "openframe_osi_v2": "OpenFrame OSI",
    "openframe_xsp_v2": "OpenFrame XSP",
    "openframe_vos3_v2": "OpenFrame VOS3",
    "openframe_gw_v2": "OpenFrame GW",
    "openframe_manager_v2": "OpenFrame Manager",
    "openframe_ndb_v2": "OpenFrame NDB",
    "jeus_v2": "JEUS",
    "tibero7_v2": "Tibero 7",
    "tmax_v2": "Tmax",
    "webtob_v2": "WebtoB",
    "ofasm_v2": "OpenFrame ASM",
    "ofcobol_v2": "OpenFrame COBOL",
    "ofpli_v2": "OpenFrame PL/I",
    "ofstudio_v2": "OFStudio",
    "ofmanager_v2": "OFManager",
    "ofminer_v2": "OFMiner",
    "ofgw_v2": "OFGW",
    "prosort_v2": "ProSort",
    "prosync_v2": "ProSync",
    "protrieve_v2": "ProTrieve",
}

PRODUCT_CLUSTERS: Dict[str, List[str]] = {
    "openframe_core": [
        "openframe_common_v2",
        "openframe_base_v2",
        "openframe_batch_v2",
        "openframe_osc_v2",
        "openframe_tacf_v2",
        "openframe_hidb_v2",
        "openframe_aim_v2",
        "openframe_osi_v2",
        "openframe_xsp_v2",
        "openframe_vos3_v2",
        "openframe_gw_v2",
        "openframe_manager_v2",
        "openframe_ndb_v2",
    ],
    "openframe_tools": [
        "ofasm_v2",
        "ofcobol_v2",
        "ofpli_v2",
        "ofstudio_v2",
        "ofmanager_v2",
        "ofminer_v2",
        "ofgw_v2",
    ],
    "middleware": ["jeus_v2", "webtob_v2", "tmax_v2"],
    "database": ["tibero7_v2"],
    "utilities": ["prosort_v2", "prosync_v2", "protrieve_v2"],
}

# ── Tag Detection Patterns ─────────────────────────────────────────

_TAG_PATTERNS: Dict[ItemType, List[re.Pattern]] = {
    ItemType.COMMAND: [
        re.compile(r"(?:コマンド|command|명령)", re.IGNORECASE),
        re.compile(r"^[a-z]+mgr\b", re.IGNORECASE),
        re.compile(r"(?:構文|syntax|구문)\s*[:：]", re.IGNORECASE),
    ],
    ItemType.ERROR: [
        re.compile(r"-\d{4,5}"),
        re.compile(r"(?:エラー|error|에러|오류)", re.IGNORECASE),
        re.compile(r"(?:ABEND|異常終了)", re.IGNORECASE),
    ],
    ItemType.CONFIG: [
        re.compile(r"(?:設定|config|configuration|설정)", re.IGNORECASE),
        re.compile(r"(?:パラメータ|parameter|파라미터)", re.IGNORECASE),
        # Removed: bare `word=value` pattern — too many false positives from code
    ],
    ItemType.API: [
        re.compile(r"(?:API|関数|function|함수)", re.IGNORECASE),
        # Removed: bare `func()` pattern — too many false positives from code examples
    ],
    ItemType.CONCEPT: [
        re.compile(r"(?:概要|overview|개요)", re.IGNORECASE),
        re.compile(r"(?:とは|について|定義)", re.IGNORECASE),
    ],
    ItemType.MIGRATION: [
        re.compile(r"(?:移行|migration|마이그레이션|変換|convert)", re.IGNORECASE),
    ],
    ItemType.LIMITATION: [
        re.compile(r"(?:制限|limitation|제한|注意|caution|주의)", re.IGNORECASE),
    ],
}

# ── Text cleaning patterns ──────────────────────────────────────────

_TOC_LINE_RE = re.compile(r"^.*?\.{4,}\s*\d+\s*$", re.MULTILINE)
_FOOTER_RE = re.compile(
    r"^(?:Copyright|©|Tmax|TmaxSoft|All rights reserved).*$",
    re.MULTILINE | re.IGNORECASE,
)
_PAGE_NUM_RE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_SECTION_SPLIT_RE = re.compile(
    r"\n(?=第?\d+[章節]|[A-Z]\.\d+|\d+\.\d+\.|\#{1,3}\s)"
)


class ManualLoader:
    """Load product manuals and extract semantic sections."""

    def __init__(self, config: GenerationConfig):
        self.config = config
        self.manuals_dir = Path(config.manuals_dir)

    def load_all(self) -> List[ManualSection]:
        """Discover and load all manuals from all product directories."""
        all_sections: List[ManualSection] = []

        if not self.manuals_dir.exists():
            logger.error("Manuals directory not found: %s", self.manuals_dir)
            return all_sections

        for item in sorted(self.manuals_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                try:
                    sections = self.load_product_dir(item)
                    all_sections.extend(sections)
                    logger.info(
                        "  %s → %d sections", item.name, len(sections)
                    )
                except Exception:
                    logger.exception("Failed to load directory: %s", item.name)

        logger.info(
            "Total: %d sections from %d directories",
            len(all_sections),
            sum(1 for d in self.manuals_dir.iterdir() if d.is_dir()),
        )
        return all_sections

    def load_product_dir(self, dir_path: Path) -> List[ManualSection]:
        """Load all files from a single product directory."""
        dir_name = dir_path.name
        language = DIRECTORY_LANGUAGE.get(dir_name, Language.JA)
        sections: List[ManualSection] = []

        for file_path in sorted(dir_path.rglob("*")):
            if file_path.is_dir():
                continue
            suffix = file_path.suffix.lower()
            product = self._resolve_product_id(file_path.name, dir_name)
            try:
                if suffix == ".pdf":
                    sections.extend(
                        self._load_pdf(file_path, product, language)
                    )
                elif suffix in (".md", ".markdown"):
                    sections.extend(
                        self._load_markdown(file_path, product, language)
                    )
                elif suffix in (".txt", ".text"):
                    sections.extend(
                        self._load_text(file_path, product, language)
                    )
            except Exception:
                logger.warning("Failed to load file: %s", file_path, exc_info=True)

        return sections

    # ── File type loaders ────────────────────────────────────────

    def _load_pdf(
        self, pdf_path: Path, product: str, language: Language
    ) -> List[ManualSection]:
        """Extract text from PDF with TOC-based section splitting."""
        sections: List[ManualSection] = []
        rel_path = str(pdf_path)

        try:
            doc = fitz.open(str(pdf_path))
        except Exception:
            logger.warning("Cannot open PDF: %s", pdf_path)
            return sections

        toc = doc.get_toc()

        if toc and len(toc) >= 3:
            sections = self._split_by_toc(doc, toc, product, language, rel_path)
        else:
            sections = self._split_by_pages(doc, product, language, rel_path)

        doc.close()
        return sections

    def _split_by_toc(
        self,
        doc: fitz.Document,
        toc: list,
        product: str,
        language: Language,
        rel_path: str,
    ) -> List[ManualSection]:
        """Split PDF by table-of-contents entries."""
        sections: List[ManualSection] = []
        total_pages = len(doc)

        for i, (level, title, page_num) in enumerate(toc):
            if level > 2:
                continue
            start_page = max(0, page_num - 1)
            if i + 1 < len(toc):
                end_page = min(total_pages, toc[i + 1][2] - 1)
            else:
                end_page = total_pages

            text_parts = []
            for pg in range(start_page, end_page):
                if pg < total_pages:
                    text_parts.append(doc[pg].get_text())

            content = self._normalize_text("\n".join(text_parts))
            if len(content) < self.config.min_chunk_size:
                continue

            for chunk in self._chunk_section(content, self.config.max_chunk_size):
                tags = self._detect_tags(chunk)
                sections.append(
                    ManualSection(
                        product=product,
                        section_title=title.strip(),
                        content=chunk,
                        source_file=rel_path,
                        page_range=(start_page + 1, end_page),
                        language=language,
                        tags=tags,
                    )
                )

        return sections

    def _split_by_pages(
        self,
        doc: fitz.Document,
        product: str,
        language: Language,
        rel_path: str,
    ) -> List[ManualSection]:
        """Fallback: split PDF by page groups when no TOC."""
        sections: List[ManualSection] = []
        buffer = ""
        start_page = 0

        for pg_num in range(len(doc)):
            page_text = doc[pg_num].get_text()
            buffer += page_text + "\n"

            if len(buffer) >= self.config.chunk_size or pg_num == len(doc) - 1:
                content = self._normalize_text(buffer)
                if len(content) >= self.config.min_chunk_size:
                    tags = self._detect_tags(content)
                    sections.append(
                        ManualSection(
                            product=product,
                            section_title=f"Page {start_page + 1}-{pg_num + 1}",
                            content=content,
                            source_file=rel_path,
                            page_range=(start_page + 1, pg_num + 1),
                            language=language,
                            tags=tags,
                        )
                    )
                buffer = ""
                start_page = pg_num + 1

        return sections

    def _load_markdown(
        self, md_path: Path, product: str, language: Language
    ) -> List[ManualSection]:
        """Split markdown by heading levels."""
        text = md_path.read_text(encoding="utf-8", errors="replace")
        sections: List[ManualSection] = []
        rel_path = str(md_path.relative_to(Path.cwd()))

        parts = re.split(r"\n(?=#{1,3}\s)", text)
        for part in parts:
            lines = part.strip().split("\n", 1)
            title = lines[0].lstrip("#").strip() if lines else "Untitled"
            content = self._normalize_text(lines[1] if len(lines) > 1 else part)
            if len(content) < self.config.min_chunk_size:
                continue
            tags = self._detect_tags(content)
            sections.append(
                ManualSection(
                    product=product,
                    section_title=title,
                    content=content,
                    source_file=rel_path,
                    page_range=None,
                    language=language,
                    tags=tags,
                )
            )
        return sections

    def _load_text(
        self, txt_path: Path, product: str, language: Language
    ) -> List[ManualSection]:
        """Split plain text by blank-line paragraphs."""
        text = txt_path.read_text(encoding="utf-8", errors="replace")
        sections: List[ManualSection] = []
        rel_path = str(txt_path.relative_to(Path.cwd()))

        chunks = self._chunk_section(
            self._normalize_text(text), self.config.max_chunk_size
        )
        for i, chunk in enumerate(chunks):
            if len(chunk) < self.config.min_chunk_size:
                continue
            tags = self._detect_tags(chunk)
            sections.append(
                ManualSection(
                    product=product,
                    section_title=f"Section {i + 1}",
                    content=chunk,
                    source_file=rel_path,
                    page_range=None,
                    language=language,
                    tags=tags,
                )
            )
        return sections

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _resolve_product_id(filename: str, dir_name: str) -> str:
        """Resolve product_id from PDF filename + directory."""
        if dir_name in COMPONENT_SPLIT_DIRS:
            stem = Path(filename).stem
            # Pattern: "OF_{Component}_..." or "OF7_{Component}_..."
            m = re.match(r"OF\d?_(\w+?)_", stem)
            if m:
                component = m.group(1)
                if component in PDF_COMPONENT_TO_PRODUCT:
                    return PDF_COMPONENT_TO_PRODUCT[component]

        if dir_name in DIRECTORY_TO_PRODUCT:
            return DIRECTORY_TO_PRODUCT[dir_name]

        # Fallback: slugify directory name
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", dir_name).strip("_").lower()
        return slug

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Clean extracted text."""
        text = unicodedata.normalize("NFKC", text)
        # Remove control chars except newlines/tabs
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        # Remove TOC dotted lines
        text = _TOC_LINE_RE.sub("", text)
        # Remove footer/copyright lines
        text = _FOOTER_RE.sub("", text)
        # Remove bare page numbers
        text = _PAGE_NUM_RE.sub("", text)
        # Collapse excessive blank lines
        text = _MULTI_BLANK_RE.sub("\n\n", text)
        return text.strip()

    @staticmethod
    def _detect_tags(content: str) -> List[ItemType]:
        """Auto-detect content type tags from text patterns."""
        tags: List[ItemType] = []
        sample = content[:1000]
        for item_type, patterns in _TAG_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(sample):
                    tags.append(item_type)
                    break
        if not tags:
            tags.append(ItemType.CONCEPT)
        return tags

    def _chunk_section(self, content: str, max_size: int) -> List[str]:
        """Split oversized sections into smaller chunks."""
        if len(content) <= max_size:
            return [content]

        chunks: List[str] = []
        paragraphs = content.split("\n\n")
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 > max_size and current:
                chunks.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para

        if current.strip():
            chunks.append(current.strip())

        # If any single paragraph is still too large, split by sentences
        final: List[str] = []
        for chunk in chunks:
            if len(chunk) <= max_size:
                final.append(chunk)
            else:
                sentences = re.split(r"(?<=[。．.!?])\s*", chunk)
                buf = ""
                for s in sentences:
                    if len(buf) + len(s) > max_size and buf:
                        final.append(buf.strip())
                        buf = s
                    else:
                        buf = buf + s if buf else s
                if buf.strip():
                    final.append(buf.strip())

        return final
