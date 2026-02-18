"""Extract grammar rules from OF7 Yacc (.y) files.

Parses yacc grammar sections to identify supported commands and
sub-command structures (e.g., IDCAMS DEFINE CLUSTER).
"""

import logging
import re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def extract_yacc_rules(yacc_path: Path) -> List[Dict[str, str]]:
    """Extract grammar rule names from a .y yacc file.

    Returns list of dicts: {"rule": str, "tokens": list[str]}
    """
    if not yacc_path.exists():
        logger.warning("Yacc file not found: %s", yacc_path)
        return []

    content = yacc_path.read_text(encoding="utf-8", errors="replace")

    results: List[Dict[str, str]] = []

    # Extract %token declarations → these are the recognized keywords
    token_re = re.compile(r'%token\s+(?:<\w+>\s+)?(.+)', re.MULTILINE)
    tokens: List[str] = []
    for m in token_re.finditer(content):
        line_tokens = m.group(1).strip().split()
        for t in line_tokens:
            t = t.strip()
            if t and t not in ("%token", "%left", "%right", "%nonassoc"):
                tokens.append(t)

    # Filter to meaningful command tokens (skip internal ones)
    for tok in tokens:
        # Skip lowercase internal tokens and common yacc tokens
        if tok.startswith("TOKEN_") or tok.startswith("TK_"):
            cmd = tok.replace("TOKEN_", "").replace("TK_", "")
            if len(cmd) >= 2:
                results.append({"rule": tok, "tokens": [cmd]})
        elif tok.isupper() and len(tok) >= 2:
            results.append({"rule": tok, "tokens": [tok]})

    logger.info("Extracted %d yacc tokens from %s", len(results), yacc_path.name)
    return results


def extract_utility_yacc_commands(util_dir: Path) -> Dict[str, List[str]]:
    """Extract commands from all utility yacc files in a directory.

    Returns dict: utility_name → list of commands
    """
    if not util_dir.exists():
        return {}

    results: Dict[str, List[str]] = {}
    for yacc_file in sorted(util_dir.rglob("*.y")):
        util_name = yacc_file.parent.name.upper()
        rules = extract_yacc_rules(yacc_file)
        if rules:
            commands = sorted(set(
                cmd
                for r in rules
                for cmd in r["tokens"]
            ))
            if util_name in results:
                results[util_name].extend(commands)
                results[util_name] = sorted(set(results[util_name]))
            else:
                results[util_name] = commands

    return results
