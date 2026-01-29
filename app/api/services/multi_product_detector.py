"""
Multi-Product Detector for Query Analysis.

Detects multiple products mentioned in a query by:
1. Direct product name matching (OSC, TJES, HiDB, etc.)
2. Dynamic keyword-to-product mapping from summaries
3. Technical term association (BMS→OSC, MFS→OSI)

This replaces hardcoded keyword-to-product mappings with dynamic discovery.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from dataclasses import dataclass
from collections import Counter
import json

logger = logging.getLogger(__name__)


@dataclass
class ProductMatch:
    """A detected product match in the query."""
    product: str           # Product name (e.g., "OSC", "OSI")
    keyword: str           # Matched keyword (e.g., "BMS", "MFS")
    confidence: float      # Match confidence (0.0-1.0)
    source: str            # How it was matched (direct, summary, association)
    position: int          # Position in query


# CJK character ranges for word boundary detection in mixed-language text
# Covers Japanese (Hiragana, Katakana, Kanji), Chinese, Korean
CJK_RANGES = r'\u3000-\u9FFF\uAC00-\uD7AF\uFF00-\uFFEF'


def _build_multilang_pattern(term: str) -> str:
    """
    Build regex pattern that works for both English and mixed CJK text.

    Standard \\b word boundary doesn't work well with Japanese/Korean text.
    This creates a pattern that matches:
    - Start of string or after whitespace
    - After CJK characters (Japanese, Chinese, Korean)
    - Before whitespace or CJK characters
    - End of string

    Examples:
        "MFS" matches in: "MFSについて", "What is MFS?", "MFS map"
    """
    escaped = re.escape(term)
    # Match: start of string OR whitespace OR CJK character before term
    # Match: end of string OR whitespace OR CJK character after term
    before = rf'(?:^|(?<=\s)|(?<=[{CJK_RANGES}]))'
    after = rf'(?=$|\s|[{CJK_RANGES}])'
    return f'{before}{escaped}{after}'


# Known OpenFrame products with aliases
KNOWN_PRODUCTS = {
    "OSC": {
        "aliases": ["OSC", "osc", "CICS"],
        "related_terms": ["BMS", "map", "マップ", "online", "transaction"],
        "description": "Online Service Controller (CICS equivalent)",
    },
    "OSI": {
        "aliases": ["OSI", "osi", "IMS"],
        "related_terms": ["MFS", "DL/I", "hierarchical", "message format"],
        "description": "Online Service Interface (IMS DC equivalent)",
    },
    "TJES": {
        "aliases": ["TJES", "tjes", "JES", "JES2", "JES3"],
        "related_terms": ["tjesmgr", "batch", "job", "spool", "scheduler"],
        "description": "Tmax Job Entry Subsystem",
    },
    "TACF": {
        "aliases": ["TACF", "tacf", "RACF"],
        "related_terms": ["tacfmgr", "security", "access control", "permission"],
        "description": "Tmax Access Control Facility",
    },
    "HiDB": {
        "aliases": ["HiDB", "HIDB", "hidb", "IMS DB"],
        "related_terms": ["hidbmgr", "hierarchical", "database", "segment"],
        "description": "Hierarchical Database (IMS DB equivalent)",
    },
    "NDB": {
        "aliases": ["NDB", "ndb"],
        "related_terms": ["ndbmgr", "network database"],
        "description": "Network Database",
    },
    "Base": {
        "aliases": ["Base", "BASE", "base", "OpenFrame Base"],
        "related_terms": ["dataset", "VSAM", "JCL", "utility"],
        "description": "OpenFrame Base System",
    },
    "Batch": {
        "aliases": ["Batch", "BATCH", "batch"],
        "related_terms": ["job", "JCL", "step", "proc"],
        "description": "Batch Processing System",
    },
    "Tibero": {
        "aliases": ["Tibero", "TIBERO", "tibero"],
        "related_terms": ["database", "SQL", "RDBMS"],
        "description": "Tibero RDBMS",
    },
}

# Cache for dynamic keyword-to-product mapping
_keyword_product_cache: Dict[str, List[Tuple[str, int]]] = {}
_cache_loaded = False


class MultiProductDetector:
    """
    Detects multiple products mentioned in a query.

    Uses multiple strategies:
    1. Direct matching: Known product names and aliases
    2. Dynamic lookup: Search summaries for keyword associations
    3. Related terms: Known technical associations (BMS→OSC)
    """

    def __init__(self, summaries_dir: Optional[Path] = None):
        """
        Initialize the detector.

        Args:
            summaries_dir: Path to summaries directory for dynamic lookup
        """
        self.summaries_dir = summaries_dir or self._find_summaries_dir()
        self._load_keyword_cache()
        logger.info(f"MultiProductDetector initialized with summaries: {self.summaries_dir}")

    def _find_summaries_dir(self) -> Path:
        """Find the summaries directory."""
        candidates = [
            Path("uploads/summaries"),
            Path("/opt/kms/uploads/summaries"),
        ]
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    def _load_keyword_cache(self) -> None:
        """Load or build keyword-to-product cache from summaries."""
        global _keyword_product_cache, _cache_loaded

        if _cache_loaded:
            return

        cache_file = self.summaries_dir / ".keyword_product_cache.json"

        # Try to load existing cache
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    _keyword_product_cache = json.load(f)
                _cache_loaded = True
                logger.info(f"Loaded keyword-product cache: {len(_keyword_product_cache)} keywords")
                return
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

        # Build cache from summaries
        _keyword_product_cache = self._build_keyword_cache()
        _cache_loaded = True

        # Save cache
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(_keyword_product_cache, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved keyword-product cache: {len(_keyword_product_cache)} keywords")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _build_keyword_cache(self) -> Dict[str, List[Tuple[str, int]]]:
        """Build keyword-to-product mapping from summaries."""
        cache = {}

        # Product patterns in filenames
        product_patterns = [
            (r"_OSC_|OpenFrame_OSC", "OSC"),
            (r"_OSI_|OpenFrame_OSI", "OSI"),
            (r"_TJES_|OpenFrame_TJES", "TJES"),
            (r"_TACF_|OpenFrame_TACF", "TACF"),
            (r"_HiDB_|OpenFrame_HiDB|_HIDB_", "HiDB"),
            (r"_NDB_|OpenFrame_NDB", "NDB"),
            (r"_Base_|OpenFrame_Base", "Base"),
            (r"_Batch_|OpenFrame_Batch", "Batch"),
            (r"_Common_|OpenFrame_Common", "Common"),
        ]

        # Keywords to search for in summaries
        technical_keywords = [
            "BMS", "MFS", "DL/I", "PSB", "PCB", "DBD",
            "JCL", "PROC", "DD", "VSAM", "KSDS", "ESDS",
            "CICS", "IMS", "TSO", "ISPF",
        ]

        if not self.summaries_dir.exists():
            return cache

        for subdir in ["commands", "concepts", "configs", "glossary", "terms"]:
            search_dir = self.summaries_dir / subdir
            if not search_dir.exists():
                continue

            for md_file in search_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8")
                    filename = md_file.name

                    # Determine product from filename
                    file_product = None
                    for pattern, product in product_patterns:
                        if re.search(pattern, filename):
                            file_product = product
                            break

                    if not file_product:
                        # Try to get from PDF references in content
                        pdf_refs = re.findall(r'OF_([A-Za-z]+)_', content)
                        for ref in pdf_refs:
                            ref_upper = ref.upper()
                            if ref_upper in KNOWN_PRODUCTS:
                                file_product = ref_upper
                                break

                    if not file_product:
                        continue

                    # Find technical keywords in this file
                    for keyword in technical_keywords:
                        if keyword in content or keyword.lower() in content.lower():
                            if keyword not in cache:
                                cache[keyword] = []
                            # Add product with count
                            existing = [p for p, c in cache[keyword] if p == file_product]
                            if existing:
                                # Increment count
                                cache[keyword] = [
                                    (p, c + 1) if p == file_product else (p, c)
                                    for p, c in cache[keyword]
                                ]
                            else:
                                cache[keyword].append((file_product, 1))

                except Exception as e:
                    logger.debug(f"Error processing {md_file}: {e}")
                    continue

        return cache

    def detect(self, query: str) -> List[ProductMatch]:
        """
        Detect all products mentioned in the query.

        Args:
            query: User query string

        Returns:
            List of ProductMatch objects sorted by confidence
        """
        matches: List[ProductMatch] = []
        matched_products: Set[str] = set()

        # Strategy 1: Direct product name matching
        for product, info in KNOWN_PRODUCTS.items():
            for alias in info["aliases"]:
                # Use multilingual pattern for CJK support
                pattern = _build_multilang_pattern(alias)
                match = re.search(pattern, query, re.IGNORECASE)
                if match and product not in matched_products:
                    matches.append(ProductMatch(
                        product=product,
                        keyword=alias,
                        confidence=1.0,
                        source="direct",
                        position=match.start()
                    ))
                    matched_products.add(product)
                    break

        # Strategy 2: Related terms matching
        for product, info in KNOWN_PRODUCTS.items():
            if product in matched_products:
                continue
            for term in info["related_terms"]:
                # Use multilingual pattern for CJK support
                pattern = _build_multilang_pattern(term)
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    matches.append(ProductMatch(
                        product=product,
                        keyword=term,
                        confidence=0.85,
                        source="related_term",
                        position=match.start()
                    ))
                    matched_products.add(product)
                    break

        # Strategy 3: Dynamic keyword lookup from cache
        # Extract uppercase keywords from query (handle mixed CJK text)
        # Pattern matches: start/whitespace/CJK + 2-5 uppercase letters + end/whitespace/CJK
        keyword_extract_pattern = rf'(?:^|[\s{CJK_RANGES}])([A-Z]{{2,5}})(?=$|[\s{CJK_RANGES}])'
        query_keywords = re.findall(keyword_extract_pattern, query.upper())

        for keyword in query_keywords:
            if keyword in _keyword_product_cache:
                product_counts = _keyword_product_cache[keyword]
                if product_counts:
                    # Get product with highest count
                    best_product, count = max(product_counts, key=lambda x: x[1])
                    if best_product not in matched_products:
                        # Find position in original query using multilingual pattern
                        match = re.search(_build_multilang_pattern(keyword), query, re.IGNORECASE)
                        position = match.start() if match else 0
                        matches.append(ProductMatch(
                            product=best_product,
                            keyword=keyword,
                            confidence=min(0.8, 0.5 + count * 0.1),
                            source="summary_lookup",
                            position=position
                        ))
                        matched_products.add(best_product)

        # Sort by position in query, then by confidence
        matches.sort(key=lambda m: (m.position, -m.confidence))

        logger.info(f"Detected products in query: {[m.product for m in matches]}")
        return matches

    def get_products(self, query: str) -> List[str]:
        """
        Get list of product names detected in query.

        Args:
            query: User query string

        Returns:
            List of product names (e.g., ["OSC", "OSI"])
        """
        matches = self.detect(query)
        return [m.product for m in matches]

    def refresh_cache(self) -> None:
        """Force refresh of keyword-product cache."""
        global _cache_loaded
        _cache_loaded = False
        cache_file = self.summaries_dir / ".keyword_product_cache.json"
        if cache_file.exists():
            cache_file.unlink()
        self._load_keyword_cache()


# Singleton instance
_detector_instance: Optional[MultiProductDetector] = None


def get_multi_product_detector() -> MultiProductDetector:
    """Get or create singleton MultiProductDetector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = MultiProductDetector()
    return _detector_instance
