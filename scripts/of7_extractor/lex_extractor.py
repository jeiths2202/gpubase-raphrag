"""Extract tokens from OF7 Lex (.l) files.

Parses lex definition sections to extract command/token names.
Handles two main patterns:
1. Macro definitions: TJBOOT {CHAR_B}{CHAR_O}{CHAR_O}{CHAR_T}
2. Rule tokens: "DEFINE" { return TOKEN_DEFINE; }
"""

import logging
import re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def extract_lex_tokens(lex_path: Path) -> List[Dict[str, str]]:
    """Extract command/token definitions from a .l lex file.

    Returns list of dicts: {"token": str, "command": str}
    - token: the lex macro name (e.g., TJBOOT)
    - command: the decoded human-readable command (e.g., BOOT)
    """
    if not lex_path.exists():
        logger.warning("Lex file not found: %s", lex_path)
        return []

    content = lex_path.read_text(encoding="utf-8", errors="replace")

    results: List[Dict[str, str]] = []

    # Strategy 1: CHAR_X macro pattern (tjesmgr style)
    # TJBOOT  {CHAR_B}{CHAR_O}{CHAR_O}{CHAR_T}
    char_macro_re = re.compile(
        r'^(\w+)\s+(\{CHAR_[A-Z]\}(?:\{CHAR_[A-Z]\})*)\s*$',
        re.MULTILINE,
    )
    for m in char_macro_re.finditer(content):
        token_name = m.group(1)
        char_seq = m.group(2)
        command = _decode_char_sequence(char_seq)
        if command:
            results.append({"token": token_name, "command": command})

    # Strategy 2: CHAR_X macro with alternatives (|)
    # TJCURRENTUSER {CHAR_C}{CHAR_U}|{CHAR_C}{CHAR_U}{CHAR_R}...
    alt_macro_re = re.compile(
        r'^(\w+)\s+((?:\{CHAR_[A-Z]\})+(?:\|(?:\{CHAR_[A-Z]\})+)+)\s*$',
        re.MULTILINE,
    )
    for m in alt_macro_re.finditer(content):
        token_name = m.group(1)
        if any(r["token"] == token_name for r in results):
            continue  # Already captured
        # Take the longest alternative (the full command name)
        alternatives = m.group(2).split("|")
        longest = max(alternatives, key=len)
        command = _decode_char_sequence(longest)
        if command:
            results.append({"token": token_name, "command": command})

    # Strategy 3: Quoted string rules (idcams, iebcopy, etc.)
    # "DEFINE"  { return TOKEN_DEFINE; } or similar
    rule_re = re.compile(
        r'"([A-Z][A-Z0-9_-]+)"\s*\{',
    )
    for m in rule_re.finditer(content):
        cmd = m.group(1)
        if cmd and len(cmd) >= 2 and not any(r["command"] == cmd for r in results):
            results.append({"token": cmd, "command": cmd})

    # Strategy 4: Case-insensitive lex patterns [Dd][Ee][Ff]...
    case_insensitive_re = re.compile(
        r'^(\w+)\s+(\[(?:[A-Za-z])\]\[(?:[A-Za-z])\](?:\[[A-Za-z]\])*)\s*$',
        re.MULTILINE,
    )
    for m in case_insensitive_re.finditer(content):
        token_name = m.group(1)
        pattern = m.group(2)
        if any(r["token"] == token_name for r in results):
            continue
        command = _decode_bracket_pattern(pattern)
        if command and len(command) >= 2:
            results.append({"token": token_name, "command": command})

    # Strategy 5: Inline rule keywords (AIM/DC style)
    # <OPERAND>ABENDEX  { return _acptok(ABENDEX); }
    # <INITIAL>JOB{ws}+ { BEGIN(OPERAND); return _acptok(JOB); }
    inline_re = re.compile(
        r'<\w+>([A-Z][A-Z0-9_]{1,})\b.*?\breturn\s+\w*\(?(\w+)\)?',
    )
    for m in inline_re.finditer(content):
        cmd = m.group(1)
        if cmd and len(cmd) >= 2 and not any(r["command"] == cmd for r in results):
            # Skip lex state names and common noise
            if cmd not in ("INITIAL", "OPERAND", "COMMENT", "BEGIN", "ECHO"):
                results.append({"token": cmd, "command": cmd})

    logger.info(
        "Extracted %d tokens from %s",
        len(results), lex_path.name,
    )
    return results


def extract_utility_lex_commands(util_dir: Path) -> Dict[str, List[str]]:
    """Extract commands from all utility lex files in a directory.

    Scans util_dir/*/[name].l or [name]_lex.l or [name]_scanner.l
    Returns dict: utility_name → list of commands
    """
    if not util_dir.exists():
        return {}

    results: Dict[str, List[str]] = {}
    for lex_file in sorted(util_dir.rglob("*.l")):
        util_name = lex_file.parent.name.upper()
        tokens = extract_lex_tokens(lex_file)
        if tokens:
            commands = sorted(set(t["command"] for t in tokens))
            if util_name in results:
                results[util_name].extend(commands)
                results[util_name] = sorted(set(results[util_name]))
            else:
                results[util_name] = commands

    return results


def _decode_char_sequence(seq: str) -> str:
    """Decode {CHAR_B}{CHAR_O}{CHAR_O}{CHAR_T} → BOOT"""
    chars = re.findall(r'\{CHAR_([A-Z])\}', seq)
    return "".join(chars) if chars else ""


def _decode_bracket_pattern(pattern: str) -> str:
    """Decode [Dd][Ee][Ff] → DEF (uppercase).

    Each bracket pair [Xx] represents one character; take first char of each pair.
    """
    # [Dd] has two chars but represents one letter
    pairs = re.findall(r'\[([A-Za-z])(?:[A-Za-z])?\]', pattern)
    return "".join(c.upper() for c in pairs) if pairs else ""
