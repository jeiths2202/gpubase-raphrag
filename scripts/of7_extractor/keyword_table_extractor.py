"""Extract JCL keyword tables and COBOL keywords from OF7 C source files.

Parses `mvsjcl_keyword_table.c` to extract key_job[], key_exec[], key_dd[]
arrays with their valid values. Also extracts COBOL keywords from
`cobpar_keyword.c` with dialect flags.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def extract_jcl_keywords(keyword_table_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Parse mvsjcl_keyword_table.c (or msp/vos3/xsp variants).

    Returns dict with keys "JOB", "EXEC", "DD", "OUTPUT", etc.
    Each value is a list of dicts: {"keyword": str, "valid_values": list[str]|None}
    """
    if not keyword_table_path.exists():
        logger.warning("JCL keyword table not found: %s", keyword_table_path)
        return {}

    content = keyword_table_path.read_text(encoding="utf-8", errors="replace")

    # Parse keyval_t arrays for valid values: keyval_t dd_recfm_val[] = {"F","FA",..., NULL};
    keyval_map: Dict[str, List[str]] = {}
    keyval_re = re.compile(
        r'keyval_t\s+(\w+)\[\]\s*=\s*\{([^}]+)\}',
        re.DOTALL,
    )
    for m in keyval_re.finditer(content):
        name = m.group(1)
        raw_vals = m.group(2)
        vals = _parse_string_array(raw_vals)
        # Filter meta-values like "^0", "^8", "%class", "%dsname"
        clean_vals = [v for v in vals if not v.startswith(("^", "%")) and v != "NULL"]
        if clean_vals:
            keyval_map[name] = clean_vals

    # Parse key_xxx[] arrays to extract keyword names and link to valid values
    result: Dict[str, List[Dict[str, Any]]] = {}
    key_array_re = re.compile(
        r'static\s+struct\s+key_s\s+(key_\w+)\[\]\s*=\s*\{(.*?)\n\};',
        re.DOTALL,
    )
    for m in key_array_re.finditer(content):
        array_name = m.group(1)  # e.g., key_job, key_exec, key_dd
        array_body = m.group(2)
        stmt_type = _array_name_to_stmt(array_name)
        if not stmt_type:
            continue

        entries = _parse_key_entries(array_body, keyval_map)
        result[stmt_type] = entries
        logger.info(
            "Extracted %d %s keywords from %s",
            len(entries), stmt_type, keyword_table_path.name,
        )

    # Also extract DCB sub-parameters from dd_dcb[] array
    dcb_re = re.compile(
        r'static\s+struct\s+key_s\s+dd_dcb\[\]\s*=\s*\{(.*?)\n\};',
        re.DOTALL,
    )
    dcb_match = dcb_re.search(content)
    if dcb_match:
        dcb_entries = _parse_key_entries(dcb_match.group(1), keyval_map)
        result["DCB"] = dcb_entries
        logger.info("Extracted %d DCB sub-parameters", len(dcb_entries))

    return result


def extract_cobol_keywords(cobpar_keyword_path: Path) -> List[Dict[str, Any]]:
    """Parse cobpar_keyword.c to extract COBOL keywords with dialect flags.

    Returns list of dicts: {"keyword": str, "dialect": str, "token": str}
    where dialect is "COM" (common), "MF" (Micro Focus), "OSVS" (OS/VS), "DEAD" (unused)
    """
    if not cobpar_keyword_path.exists():
        logger.warning("COBOL keyword file not found: %s", cobpar_keyword_path)
        return []

    content = cobpar_keyword_path.read_text(encoding="utf-8", errors="replace")

    # Pattern: {  "KEYWORD"  ,  TOKEN  ,  L_COM  ,  ALL  },
    entry_re = re.compile(
        r'\{\s*"([^"]+)"\s*,\s*(\w+)\s*,\s*(L_\w+)\s*,',
    )

    dialect_map = {
        "L_COM": "common",
        "L_MF": "micro_focus",
        "L_OSVS": "osvs",
        "L_DEAD": "dead",
    }

    results: List[Dict[str, Any]] = []
    seen: set = set()
    for m in entry_re.finditer(content):
        keyword = m.group(1)
        token = m.group(2)
        lang = m.group(3)

        if keyword in seen:
            continue
        seen.add(keyword)

        dialect = dialect_map.get(lang, "unknown")
        if dialect == "dead":
            continue  # Skip dead/unused keywords

        results.append({
            "keyword": keyword,
            "token": token,
            "dialect": dialect,
        })

    logger.info("Extracted %d COBOL keywords from %s", len(results), cobpar_keyword_path.name)
    return results


def _array_name_to_stmt(name: str) -> Optional[str]:
    """Map array name to JCL statement type."""
    mapping = {
        "key_job": "JOB",
        "key_exec": "EXEC",
        "key_dd": "DD",
        "key_output": "OUTPUT",
        "key_include": "INCLUDE",
        "key_jcllib": "JCLLIB",
        "key_xmit": "XMIT",
        "key_export": "EXPORT",
    }
    return mapping.get(name)


def _parse_string_array(raw: str) -> List[str]:
    """Parse C string array contents: "F","FA",...,NULL → ["F", "FA"]"""
    return [
        m.group(1)
        for m in re.finditer(r'"([^"]*)"', raw)
        if m.group(1)
    ]


def _parse_key_entries(
    body: str,
    keyval_map: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """Parse entries inside a key_s array body."""
    # Pattern: {"KEYWORD", sub_count, subtab_or_null, keyvals_or_null},
    entry_re = re.compile(
        r'\{"([^"]+)"\s*,\s*\d+\s*,\s*(\w+)\s*,\s*(\w+)\s*\}',
    )
    results = []
    for m in entry_re.finditer(body):
        keyword = m.group(1)
        # Skip sentinel ("") and positional params (#1, #2, ...)
        if not keyword or keyword.startswith("#"):
            continue

        # Clean keyword: remove .^8 suffixes (step-name overrides)
        clean_keyword = keyword.split(".")[0] if ".^" in keyword else keyword

        # Look up valid values
        vals_ref = m.group(3)
        valid_values = keyval_map.get(vals_ref) if vals_ref != "NULL" else None

        results.append({
            "keyword": clean_keyword,
            "valid_values": valid_values,
        })

    return results
