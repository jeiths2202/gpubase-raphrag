"""Extract limits, constants, and type definitions from OF7 header files.

Parses JCL limit headers, dataset type definitions, and VSAM constants.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def extract_defines(header_path: Path, prefix: str = "") -> Dict[str, Any]:
    """Extract #define constants from a header file.

    Args:
        header_path: Path to .h file
        prefix: Only extract defines starting with this prefix

    Returns dict: name → value (int or str)
    """
    if not header_path.exists():
        logger.warning("Header file not found: %s", header_path)
        return {}

    content = header_path.read_text(encoding="utf-8", errors="replace")
    results: Dict[str, Any] = {}

    # #define NAME value  or  #define NAME (expr)
    define_re = re.compile(
        r'#define\s+(\w+)\s+(\(?.+?\)?)\s*(?:/\*.*?\*/)?$',
        re.MULTILINE,
    )
    for m in define_re.finditer(content):
        name = m.group(1)
        value_str = m.group(2).strip()

        if prefix and not name.startswith(prefix):
            continue
        # Skip include guards and internal macros
        if name.startswith("__") or name.endswith("_H_"):
            continue

        # Try integer parsing
        value = _try_parse_int(value_str)
        if value is not None:
            results[name] = value
        elif value_str.startswith('"'):
            # String constant
            results[name] = value_str.strip('"')
        else:
            results[name] = value_str

    logger.info("Extracted %d defines from %s", len(results), header_path.name)
    return results


def extract_enum_values(header_path: Path, enum_prefix: str = "") -> List[Dict[str, Any]]:
    """Extract enum values from a header file.

    Returns list of dicts: {"name": str, "value": int|None}
    """
    if not header_path.exists():
        return []

    content = header_path.read_text(encoding="utf-8", errors="replace")
    results: List[Dict[str, Any]] = []

    # Match enum blocks
    enum_re = re.compile(r'enum\s*\w*\s*\{([^}]+)\}', re.DOTALL)
    for m in enum_re.finditer(content):
        body = m.group(1)
        counter = 0
        for line in body.split(","):
            line = line.strip()
            if not line or line.startswith("/*") or line.startswith("//"):
                continue

            # NAME = value  or just NAME
            eq_match = re.match(r'(\w+)\s*=\s*(\w+)', line)
            name_match = re.match(r'(\w+)', line)

            if eq_match:
                name = eq_match.group(1)
                val = _try_parse_int(eq_match.group(2))
                if val is not None:
                    counter = val
                results.append({"name": name, "value": counter})
            elif name_match:
                name = name_match.group(1)
                results.append({"name": name, "value": counter})

            counter += 1

    if enum_prefix:
        results = [r for r in results if r["name"].startswith(enum_prefix)]

    return results


def extract_dataset_types(ds_header_dir: Path) -> Dict[str, List[str]]:
    """Extract supported dataset types from ds include headers.

    Scans for DSORG, RECFM, DISP type definitions.
    Returns dict: category → list of valid values
    """
    results: Dict[str, List[str]] = {}

    # Common dataset-related defines to look for
    target_prefixes = [
        "DSORG_", "RECFM_", "DISP_", "DCB_",
        "VSAM_", "KSDS", "ESDS", "LDS", "GDG",
    ]

    for h_file in sorted(ds_header_dir.rglob("*.h")):
        content = h_file.read_text(encoding="utf-8", errors="replace")

        for prefix in target_prefixes:
            define_re = re.compile(
                rf'#define\s+({prefix}\w*)\s+',
            )
            for m in define_re.finditer(content):
                name = m.group(1)
                category = prefix.rstrip("_")
                if category not in results:
                    results[category] = []
                if name not in results[category]:
                    results[category].append(name)

    return results


def _try_parse_int(s: str) -> int | None:
    """Try to parse a string as an integer (decimal, hex, or octal)."""
    s = s.strip().strip("()")
    try:
        if s.startswith("0x") or s.startswith("0X"):
            return int(s, 16)
        elif s.startswith("0") and len(s) > 1 and s[1:].isdigit():
            return int(s, 8)
        else:
            return int(s)
    except (ValueError, TypeError):
        return None
