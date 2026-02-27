"""Generate capability JSON files from OF7 source code.

Orchestrates all extractors to produce enriched capability JSON files
that are directly consumable by the ProductRegistry.

Usage:
    python -m scripts.of7_extractor.generate_capabilities \
        --of7-path OF7/ \
        --output-dir app/api/legacy_modernization/capabilities/ \
        [--dry-run]
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from .keyword_table_extractor import extract_cobol_keywords, extract_jcl_keywords
from .lex_extractor import extract_lex_tokens, extract_utility_lex_commands
from .yacc_extractor import extract_utility_yacc_commands
from .errcode_extractor import extract_error_codes, group_by_module
from .header_extractor import extract_defines

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# tjesmgr token → human-readable command mapping (strip TJ prefix)
_TJESMGR_PREFIX = "TJ"


def _build_capability_entry(
    category: str,
    pattern: str,
    support: str = "full",
    notes: str | None = None,
    valid_values: list[str] | None = None,
    parameters: list[str] | None = None,
    source_ref: str | None = None,
) -> Dict[str, Any]:
    """Build a single capability entry dict."""
    entry: Dict[str, Any] = {
        "category": category,
        "pattern": pattern,
        "support": support,
        "notes": notes,
    }
    if valid_values:
        entry["valid_values"] = valid_values
    if parameters:
        entry["parameters"] = parameters
    if source_ref:
        entry["source_ref"] = source_ref
    return entry


def generate_jcl_capabilities(
    of7_path: Path,
    jcl_variant: str = "mvsjcl",
) -> List[Dict[str, Any]]:
    """Generate JCL parameter capabilities from keyword tables."""
    # Determine source file
    keyword_table = of7_path / "base" / "parser" / jcl_variant / f"{jcl_variant}_keyword_table.c"
    if not keyword_table.exists():
        # Try alternate name for XSP
        keyword_table = of7_path / "base" / "parser" / jcl_variant / f"{jcl_variant}_keyword.c"
    if not keyword_table.exists():
        logger.warning("JCL keyword table not found for %s", jcl_variant)
        return []

    jcl_data = extract_jcl_keywords(keyword_table)
    entries: List[Dict[str, Any]] = []

    for stmt_type, keywords in jcl_data.items():
        for kw in keywords:
            keyword = kw["keyword"]
            valid_vals = kw.get("valid_values")

            # Build pattern: "JCL JOB REGION" or "JCL DD DCB RECFM"
            if stmt_type == "DCB":
                pattern = f"JCL DD DCB {keyword}"
            else:
                pattern = f"JCL {stmt_type} {keyword}"

            entries.append(_build_capability_entry(
                category="jcl_parameter",
                pattern=pattern,
                support="full",
                notes=f"JCL {stmt_type} statement {keyword} parameter",
                valid_values=valid_vals,
                source_ref=str(keyword_table.relative_to(of7_path)),
            ))

    return entries


def generate_cobol_capabilities(of7_path: Path) -> List[Dict[str, Any]]:
    """Generate COBOL keyword capabilities."""
    cobpar_path = of7_path / "base" / "parser" / "cobpar" / "cobpar_keyword.c"
    keywords = extract_cobol_keywords(cobpar_path)
    entries: List[Dict[str, Any]] = []

    for kw in keywords:
        keyword = kw["keyword"]
        dialect = kw["dialect"]

        # Map dialect to category detail
        if dialect == "common":
            notes = "Standard COBOL keyword"
        elif dialect == "micro_focus":
            notes = "Micro Focus COBOL extension"
        elif dialect == "osvs":
            notes = "OS/VS COBOL extension"
        else:
            notes = f"COBOL keyword ({dialect})"

        entries.append(_build_capability_entry(
            category="cobol_keyword",
            pattern=f"COBOL {keyword}",
            support="full",
            notes=notes,
            source_ref="base/parser/cobpar/cobpar_keyword.c",
        ))

    return entries


def generate_tool_capabilities(of7_path: Path) -> List[Dict[str, Any]]:
    """Generate tjesmgr and other tool command capabilities."""
    entries: List[Dict[str, Any]] = []

    # tjesmgr commands
    tjesmgr_lex = of7_path / "batch" / "tool" / "tjesmgr" / "tjesmgr_lex.l"
    if tjesmgr_lex.exists():
        tokens = extract_lex_tokens(tjesmgr_lex)
        seen_commands: set = set()
        for tok in tokens:
            cmd = tok["command"]
            # Remove TJ prefix if present in token name
            token_name = tok["token"]
            if token_name.startswith("TJ"):
                display_cmd = token_name[2:]  # TJBOOT → BOOT
            else:
                display_cmd = cmd

            if display_cmd in seen_commands:
                continue
            seen_commands.add(display_cmd)

            entries.append(_build_capability_entry(
                category="tool_command",
                pattern=f"tjesmgr {display_cmd}",
                support="full",
                notes=f"TJES manager command: {display_cmd}",
                source_ref="batch/tool/tjesmgr/tjesmgr_lex.l",
            ))

    # Other tools in batch/tool/
    tool_dir = of7_path / "batch" / "tool"
    if tool_dir.exists():
        for tool_sub in sorted(tool_dir.iterdir()):
            if not tool_sub.is_dir() or tool_sub.name == "tjesmgr":
                continue
            for lex_file in tool_sub.glob("*.l"):
                tokens = extract_lex_tokens(lex_file)
                for tok in tokens:
                    entries.append(_build_capability_entry(
                        category="tool_command",
                        pattern=f"{tool_sub.name} {tok['command']}",
                        support="full",
                        source_ref=str(lex_file.relative_to(of7_path)),
                    ))

    return entries


def generate_utility_capabilities(of7_path: Path) -> List[Dict[str, Any]]:
    """Generate utility program capabilities from lex/yacc files."""
    entries: List[Dict[str, Any]] = []

    # MVS utilities
    mvs_util_dir = of7_path / "batch" / "util" / "mvs"
    if mvs_util_dir.exists():
        lex_cmds = extract_utility_lex_commands(mvs_util_dir)
        yacc_cmds = extract_utility_yacc_commands(mvs_util_dir)

        # Merge lex and yacc results
        all_utils = set(list(lex_cmds.keys()) + list(yacc_cmds.keys()))
        for util_name in sorted(all_utils):
            commands = set()
            commands.update(lex_cmds.get(util_name, []))
            commands.update(yacc_cmds.get(util_name, []))

            # Add the utility itself as supported
            entries.append(_build_capability_entry(
                category="utility",
                pattern=f"PGM={util_name}",
                support="full",
                notes=f"MVS utility program {util_name}",
                parameters=sorted(commands) if commands else None,
                source_ref=f"batch/util/mvs/{util_name.lower()}/",
            ))

            # Add individual commands as sub-capabilities
            for cmd in sorted(commands):
                if len(cmd) >= 2 and cmd != util_name:
                    entries.append(_build_capability_entry(
                        category="utility_command",
                        pattern=f"{util_name} {cmd}",
                        support="full",
                        source_ref=f"batch/util/mvs/{util_name.lower()}/",
                    ))

    # XSP utilities
    xsp_util_dir = of7_path / "batch" / "util" / "xsp"
    if xsp_util_dir.exists():
        lex_cmds = extract_utility_lex_commands(xsp_util_dir)
        for util_name, commands in sorted(lex_cmds.items()):
            entries.append(_build_capability_entry(
                category="utility",
                pattern=f"PGM={util_name}",
                support="full",
                notes=f"XSP utility program {util_name}",
                parameters=sorted(commands) if commands else None,
                source_ref=f"batch/util/xsp/{util_name.lower()}/",
            ))

    return entries


def generate_aim_capabilities(of7_path: Path) -> List[Dict[str, Any]]:
    """Generate AIM/DC capabilities from lex files."""
    entries: List[Dict[str, Any]] = []

    aim_lex_files = [
        ("acp", of7_path / "aim" / "dc" / "acp" / "acp_l.l"),
        ("psam", of7_path / "aim" / "dc" / "psam" / "aimpsam_scan.l"),
        ("aimcmd", of7_path / "aim" / "dc" / "cmd" / "aimcmd_l.l"),
        ("aimsmr", of7_path / "aim" / "dc" / "smr" / "aimsmr_lex.l"),
    ]

    for component, lex_path in aim_lex_files:
        tokens = extract_lex_tokens(lex_path)
        for tok in tokens:
            entries.append(_build_capability_entry(
                category="aim_dc",
                pattern=f"AIM {component.upper()} {tok['command']}",
                support="full",
                source_ref=str(lex_path.relative_to(of7_path)),
            ))

    return entries


def generate_errcode_capabilities(of7_path: Path) -> Dict[str, List[Dict]]:
    """Generate error code reference data (for notes enrichment).

    Returns dict: module → list of error code dicts
    """
    all_codes: List[Dict] = []

    for errcode_dir in [
        of7_path / "batch" / "errcode",
        of7_path / "base" / "errcode",
        of7_path / "aim" / "errcode",
    ]:
        codes = extract_error_codes(errcode_dir)
        all_codes.extend(codes)

    return group_by_module(all_codes)


def _merge_into_json(
    json_path: Path,
    new_entries: List[Dict[str, Any]],
    dry_run: bool = False,
) -> int:
    """Merge new entries into an existing capability JSON file.

    Returns count of new entries added.
    """
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        data = {"capabilities": []}

    existing_patterns = {c["pattern"] for c in data.get("capabilities", [])}
    added = 0

    for entry in new_entries:
        if entry["pattern"] not in existing_patterns:
            data.setdefault("capabilities", []).append(entry)
            existing_patterns.add(entry["pattern"])
            added += 1

    if not dry_run and added > 0:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return added


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate capability JSON from OF7 sources",
    )
    parser.add_argument(
        "--of7-path", type=Path, required=True,
        help="Path to OF7/ source directory",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Path to capabilities/ output directory",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Don't write files, just show counts",
    )
    args = parser.parse_args()

    of7_path = args.of7_path.resolve()
    output_dir = args.output_dir.resolve()

    if not of7_path.exists():
        logger.error("OF7 path does not exist: %s", of7_path)
        sys.exit(1)

    total_entries = 0

    # ---- 1. COBOL keywords → _base.json ----
    logger.info("=== Extracting COBOL keywords ===")
    cobol_entries = generate_cobol_capabilities(of7_path)
    base_json = output_dir / "_base.json"
    added = _merge_into_json(base_json, cobol_entries, args.dry_run)
    logger.info("COBOL: %d new entries → _base.json", added)
    total_entries += added

    # ---- 2. MVS JCL keywords → batch/v7_3.json ----
    logger.info("=== Extracting MVS JCL keywords ===")
    mvs_jcl = generate_jcl_capabilities(of7_path, "mvsjcl")
    batch_json = output_dir / "batch" / "v7_3.json"
    added = _merge_into_json(batch_json, mvs_jcl, args.dry_run)
    logger.info("MVS JCL: %d new entries → batch/v7_3.json", added)
    total_entries += added

    # ---- 3. MSP JCL keywords → aim_msp/v7_3.json ----
    logger.info("=== Extracting MSP JCL keywords ===")
    msp_jcl = generate_jcl_capabilities(of7_path, "mspjcl")
    msp_json = output_dir / "aim_msp" / "v7_3.json"
    added = _merge_into_json(msp_json, msp_jcl, args.dry_run)
    logger.info("MSP JCL: %d new entries → aim_msp/v7_3.json", added)
    total_entries += added

    # ---- 4. VOS3 JCL keywords → batch/v7_3.json (as VOS3 category) ----
    logger.info("=== Extracting VOS3 JCL keywords ===")
    vos3_jcl = generate_jcl_capabilities(of7_path, "vos3jcl")
    # Tag VOS3 entries differently
    for entry in vos3_jcl:
        entry["category"] = "jcl_parameter_vos3"
    added = _merge_into_json(batch_json, vos3_jcl, args.dry_run)
    logger.info("VOS3 JCL: %d new entries → batch/v7_3.json", added)
    total_entries += added

    # ---- 5. XSP JCL keywords → aim_xsp/v7_3.json ----
    logger.info("=== Extracting XSP JCL keywords ===")
    xsp_jcl = generate_jcl_capabilities(of7_path, "xspjcl")
    xsp_json = output_dir / "aim_xsp" / "v7_3.json"
    added = _merge_into_json(xsp_json, xsp_jcl, args.dry_run)
    logger.info("XSP JCL: %d new entries → aim_xsp/v7_3.json", added)
    total_entries += added

    # ---- 6. Tool commands (tjesmgr, etc.) → batch/v7_3.json ----
    logger.info("=== Extracting tool commands ===")
    tool_entries = generate_tool_capabilities(of7_path)
    added = _merge_into_json(batch_json, tool_entries, args.dry_run)
    logger.info("Tools: %d new entries → batch/v7_3.json", added)
    total_entries += added

    # ---- 7. MVS utilities (IDCAMS, IEBGENER, etc.) → batch/v7_3.json ----
    logger.info("=== Extracting utility commands ===")
    util_entries = generate_utility_capabilities(of7_path)
    added = _merge_into_json(batch_json, util_entries, args.dry_run)
    logger.info("Utilities: %d new entries → batch/v7_3.json", added)
    total_entries += added

    # ---- 8. AIM/DC capabilities → aim_xsp/v7_3.json ----
    logger.info("=== Extracting AIM/DC capabilities ===")
    aim_entries = generate_aim_capabilities(of7_path)
    added = _merge_into_json(xsp_json, aim_entries, args.dry_run)
    logger.info("AIM/DC: %d new entries → aim_xsp/v7_3.json", added)
    total_entries += added

    # ---- 9. Error codes (metadata only, stored as reference) ----
    logger.info("=== Extracting error codes ===")
    errcode_data = generate_errcode_capabilities(of7_path)
    errcode_total = sum(len(codes) for codes in errcode_data.values())
    errcode_out = output_dir / "_error_codes.json"
    if not args.dry_run:
        errcode_out.write_text(
            json.dumps(errcode_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    logger.info("Error codes: %d codes in %d modules → _error_codes.json",
                errcode_total, len(errcode_data))

    # ---- Summary ----
    logger.info("=" * 60)
    logger.info("TOTAL: %d new capability entries generated", total_entries)
    logger.info("Error codes: %d (stored as reference)", errcode_total)
    if args.dry_run:
        logger.info("(DRY RUN — no files written)")
    else:
        logger.info("Files written to: %s", output_dir)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
