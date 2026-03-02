"""Extract error codes from OF7 header files.

Parses errcode_*.h files to extract #define error code definitions
with their names, base offsets, and computed values.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def extract_error_codes(errcode_dir: Path) -> List[Dict[str, str]]:
    """Extract all error codes from a directory of errcode_*.h files.

    Returns list of dicts: {
        "name": str,          # e.g., TJES_ERR_NOT_INITIALIZED
        "module": str,        # e.g., TJES
        "base_name": str,     # e.g., TJES_ERR_BASE
        "offset": int,        # e.g., 1
        "computed_value": int, # e.g., -9001
        "source_file": str,
    }
    """
    if not errcode_dir.exists():
        logger.warning("Error code directory not found: %s", errcode_dir)
        return []

    all_codes: List[Dict[str, str]] = []

    for h_file in sorted(errcode_dir.glob("errcode_*.h")):
        codes = _parse_errcode_file(h_file)
        all_codes.extend(codes)

    logger.info("Extracted %d error codes from %s", len(all_codes), errcode_dir)
    return all_codes


def _parse_errcode_file(h_file: Path) -> List[Dict]:
    """Parse a single errcode_*.h file."""
    content = h_file.read_text(encoding="utf-8", errors="replace")
    module = _extract_module_name(h_file.name)

    # First, find the BASE value: #define XXX_ERR_BASE (-5000)
    bases: Dict[str, int] = {}
    base_re = re.compile(r'#define\s+(\w+_ERR_BASE)\s+\((-?\d+)\)')
    for m in base_re.finditer(content):
        bases[m.group(1)] = int(m.group(2))

    results: List[Dict] = []

    # Pattern 1: #define ERR_NAME (BASE - offset)
    offset_re = re.compile(
        r'#define\s+(\w+)\s+\((\w+_ERR_BASE)\s*-\s*(\d+)\)',
    )
    for m in offset_re.finditer(content):
        name = m.group(1)
        base_name = m.group(2)
        offset = int(m.group(3))
        base_val = bases.get(base_name, 0)
        computed = base_val - offset

        results.append({
            "name": name,
            "module": module,
            "base_name": base_name,
            "offset": offset,
            "computed_value": computed,
            "source_file": h_file.name,
        })

    # Pattern 2: #define ERR_NAME  0  (success codes)
    success_re = re.compile(
        r'#define\s+(\w+_ERR_SUCCESS)\s+(\d+)',
    )
    for m in success_re.finditer(content):
        results.append({
            "name": m.group(1),
            "module": module,
            "base_name": "SUCCESS",
            "offset": 0,
            "computed_value": int(m.group(2)),
            "source_file": h_file.name,
        })

    return results


def _extract_module_name(filename: str) -> str:
    """Extract module name from filename: errcode_tjes.h → TJES"""
    m = re.match(r'errcode_(\w+)\.h', filename)
    return m.group(1).upper() if m else "UNKNOWN"


def group_by_module(codes: List[Dict]) -> Dict[str, List[Dict]]:
    """Group error codes by module name."""
    grouped: Dict[str, List[Dict]] = {}
    for code in codes:
        module = code["module"]
        if module not in grouped:
            grouped[module] = []
        grouped[module].append(code)
    return grouped
