"""에러 코드 설명 재추출 스크립트

Error Reference Guide PDF에서 에러 코드 설명을 재추출하여
기존 markdown 파일을 업데이트합니다.

PyMuPDF의 테이블 텍스트 추출 특성 처리:
  PDF 테이블에서 추출 시 라벨이 내용 뒤에 나타남:
    ERROR_NAME (-code)
    <description>     ← 설명 내용 (라벨보다 먼저)
    説明               ← 라벨
    <solution>        ← 대처방법 내용
    対処方法           ← 라벨
    <reference>       ← 참고 내용
    参考               ← 라벨

Usage:
    python -m scripts.fix_error_descriptions [--dry-run] [--pdf FILE]
"""

import re
import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Paths
BASE_DIR = Path(__file__).parent.parent
MANUALS_DIR = BASE_DIR / "uploads" / "manuals"
ERROR_CODES_DIR = BASE_DIR / "uploads" / "summaries" / "error-codes"

# Error Reference Guide PDFs
ERROR_GUIDE_PDFS = [
    MANUALS_DIR / "MVS_Openframe 7.1_v3.1.3_JP" / "OF_Common_MVS_7.1_Error-Reference-Guide_v3.1.3_JP.pdf",
    MANUALS_DIR / "MSP_Openframe 7.3_v2.1.1_JP" / "OF_Common_MSP_7.3_Error-Reference-Guide_v3.3.1_ja.pdf",
    MANUALS_DIR / "VOS3_Openframe 2.0 _v2.1.1 _JP" / "OF_VOS3_2.0_Error_Reference_Guide_v2.1.1_jp.pdf",
    MANUALS_DIR / "XSP_Openframe 7.3_v3.2.1_JP" / "OF_Common_XSP_7.3_Error-Reference-Guide_v3.2.1_ja.pdf",
    MANUALS_DIR / "Tibero 7 FixSet01 Manual Set v2.1.1_jp" / "Tibero_7_Error_Reference_Guide_v2.1.1_jp.pdf",
]

# Patterns
ERROR_PATTERN = re.compile(
    r"(?P<name>[A-Z][A-Z0-9_]+_ERR_[A-Z0-9_]+)\s*\((?P<code>-?\d+)\)"
)
# Section headers like "1.7. DSALC (-5000)" but NOT TOC entries with dots/page numbers
SECTION_PATTERN = re.compile(
    r"^\d+\.\d+\.?\s*(?P<module>[A-Za-z][A-Za-z0-9_-]+)\s*\((?P<code>-?\d+)\)\s*$",
    re.MULTILINE,
)
# TOC lines to filter: "4.9. AIM (-87000) . . . . . . . 213"
TOC_PATTERN = re.compile(
    r"^\d+\.\d+\.?\s*[A-Za-z][A-Za-z0-9_-]+\s*\(-?\d+\)\s*\.{2,}",
    re.MULTILINE,
)
# Standalone labels on their own line
LABEL_PATTERN = re.compile(r"^(説明|対処方法|参考)\s*$", re.MULTILINE)
# Footer patterns to filter out
FOOTER_PATTERN = re.compile(
    r"^(第\d+章\s+.+\d+\s*$|\d+\s+OpenFrame\s+.+$|\d+\s+Tibero\s+.+$)",
    re.MULTILINE,
)


@dataclass
class ErrorEntry:
    """Extracted error code entry"""
    code: int
    name: str
    description: str = ""
    solution: str = ""
    reference: str = ""
    source_file: str = ""


@dataclass
class ModuleEntry:
    """Extracted module section"""
    module_name: str
    range_code: int
    description: str = ""
    errors: List[ErrorEntry] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)


def clean_text(text: str) -> str:
    """Clean extracted text: remove footers, excess whitespace"""
    # Remove footer lines
    text = FOOTER_PATTERN.sub("", text)
    # Collapse multiple whitespace to single space
    text = re.sub(r"[ \t]+", " ", text)
    # Remove leading/trailing whitespace per line, then join
    lines = [line.strip() for line in text.strip().split("\n")]
    lines = [line for line in lines if line]
    return " ".join(lines)


def extract_error_fields(error_text: str) -> Tuple[str, str, str]:
    """Extract description, solution, reference from error text block.

    Handles TWO formats produced by PyMuPDF:

    Format A (Base modules - labels AFTER content):
        <description>
        説明
        <solution>
        対処方法
        <reference>
        参考

    Format B (AIM/NDB/PSAM - labels BEFORE content):
        説明
        <description>
        対処方法
        <solution>
        参考
        <reference>
    """
    lines = error_text.split("\n")

    # Find positions of standalone labels
    label_positions = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ("説明", "対処方法", "参考"):
            label_positions.append((i, stripped))

    if not label_positions:
        # No labels found - all text is description
        return clean_text(error_text), "", ""

    # Detect format: check if first non-empty line before first label has content
    first_label_idx = label_positions[0][0]
    text_before_first_label = "\n".join(lines[:first_label_idx])
    content_before = clean_text(text_before_first_label)

    if content_before:
        # Format A: labels AFTER content (Base modules)
        return _extract_format_a(lines, label_positions, content_before)
    else:
        # Format B: labels BEFORE content (AIM/NDB/PSAM)
        return _extract_format_b(lines, label_positions)


def _extract_format_a(
    lines: List[str],
    label_positions: List[Tuple[int, str]],
    content_before: str,
) -> Tuple[str, str, str]:
    """Format A: labels AFTER content.

    Description = text before 説明 label
    Solution = text between 説明 and 対処方法 labels
    Reference = text between 対処方法 and 参考 labels
    """
    description = content_before
    solution = ""
    reference = ""

    for i, (pos, label) in enumerate(label_positions):
        if i + 1 < len(label_positions):
            next_pos = label_positions[i + 1][0]
        else:
            next_pos = len(lines)

        content = "\n".join(lines[pos + 1:next_pos])
        content = clean_text(content)

        if label == "説明":
            solution = content
        elif label == "対処方法":
            reference = content

    return description, solution, reference


def _extract_format_b(
    lines: List[str],
    label_positions: List[Tuple[int, str]],
) -> Tuple[str, str, str]:
    """Format B: labels BEFORE content.

    Description = text after 説明 label
    Solution = text after 対処方法 label
    Reference = text after 参考 label
    """
    description = ""
    solution = ""
    reference = ""

    for i, (pos, label) in enumerate(label_positions):
        if i + 1 < len(label_positions):
            next_pos = label_positions[i + 1][0]
        else:
            next_pos = len(lines)

        content = "\n".join(lines[pos + 1:next_pos])
        content = clean_text(content)

        if label == "説明":
            description = content
        elif label == "対処方法":
            solution = content
        elif label == "参考":
            reference = content

    return description, solution, reference


def extract_from_pdf(pdf_path: Path) -> Dict[str, ModuleEntry]:
    """Extract error codes from a single PDF file."""
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF (fitz) not installed. Run: pip install pymupdf")
        sys.exit(1)

    logger.info(f"Processing: {pdf_path.name} ({pdf_path.stat().st_size // (1024*1024)}MB)")

    doc = fitz.open(str(pdf_path))
    page_count = len(doc)
    full_text = ""
    for page in doc:
        full_text += page.get_text("text") + "\n"
    doc.close()

    logger.info(f"  Extracted {len(full_text):,} chars from {page_count} pages")

    modules: Dict[str, ModuleEntry] = {}
    source_file = pdf_path.name

    # Remove TOC lines (contain dots before page numbers)
    full_text = TOC_PATTERN.sub("", full_text)

    # Find module sections
    section_matches = list(SECTION_PATTERN.finditer(full_text))
    logger.info(f"  Found {len(section_matches)} module sections")

    for i, match in enumerate(section_matches):
        module_name = match.group("module")
        range_code = int(match.group("code"))

        # Section text range
        start = match.start()
        end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(full_text)
        section_text = full_text[start:end]

        # Extract module description (text between section header and first error)
        header_end = match.end()
        error_matches = list(ERROR_PATTERN.finditer(section_text))

        if not error_matches:
            continue

        first_error_pos = error_matches[0].start()
        module_desc_text = section_text[header_end - start:first_error_pos]
        module_desc = clean_text(module_desc_text)

        module = ModuleEntry(
            module_name=module_name,
            range_code=range_code,
            description=module_desc,
            source_files=[source_file],
        )

        # Extract individual errors
        for j, ematch in enumerate(error_matches):
            error_name = ematch.group("name")
            error_code = int(ematch.group("code"))

            # Error text range (until next error or section end)
            e_start = ematch.end()
            if j + 1 < len(error_matches):
                e_end = error_matches[j + 1].start()
            else:
                e_end = len(section_text)

            error_text = section_text[e_start:e_end]

            # Extract fields
            description, solution, reference = extract_error_fields(error_text)

            entry = ErrorEntry(
                code=error_code,
                name=error_name,
                description=description,
                solution=solution,
                reference=reference,
                source_file=source_file,
            )
            module.errors.append(entry)

        # Merge with existing module or add new
        if module_name in modules:
            existing = modules[module_name]
            if source_file not in existing.source_files:
                existing.source_files.append(source_file)
            # Merge errors (prefer non-empty descriptions)
            existing_codes = {e.code for e in existing.errors}
            for error in module.errors:
                if error.code not in existing_codes:
                    existing.errors.append(error)
                else:
                    # Update if new entry has description but existing doesn't
                    for existing_error in existing.errors:
                        if existing_error.code == error.code:
                            if error.description and not existing_error.description:
                                existing_error.description = error.description
                                existing_error.solution = error.solution
                                existing_error.reference = error.reference
                            break
        else:
            modules[module_name] = module

        logger.info(f"  Module {module_name}: {len(module.errors)} errors extracted")

    return modules


def get_module_prefix(module_name: str) -> str:
    """Get the file prefix for a module name.

    Based on existing error-codes file naming convention:
    - BASE-*: OpenFrame Base modules (Non-VSAM, TSAM, DSIO, ICF, AMS, DSALC, etc.)
    - BATCH-*: Batch processing modules (TJES, SPOOL, TSO, MVSSYS)
    - TACF-*: TACF security module
    - AIM-*: AIM/DB modules
    - NDB-*: NDB modules
    - UNKNOWN-*: HiDB, IMS, OSI, etc. (kept for compatibility)
    """
    prefix_map = {
        # BASE modules (OpenFrame Base)
        "Non-VSAM": "BASE",
        "TSAM": "BASE",
        "DSIO": "BASE",
        "ICF": "BASE",
        "AMS": "BASE",
        "DSALC": "BASE",
        "VOLM": "BASE",
        "LOCKM": "BASE",
        "PGMDD": "BASE",
        "AMSX": "BASE",
        "SMS": "BASE",
        "DSCOM": "BASE",
        "CPMLIB": "BASE",
        "SAF": "BASE",
        "OFCOM": "BASE",
        "SAFX": "BASE",
        "SAFO": "BASE",
        "TLIC": "BASE",
        "SVRCOM": "BASE",
        "CONSOLE": "BASE",
        "SPIO": "BASE",
        "SMF": "BASE",
        "DSORG": "BASE",
        "DSCRE": "BASE",
        "DSENV": "BASE",
        "DSCUR": "BASE",
        "TEXTFH": "BASE",
        "OFSTUDIO": "BASE",
        # BATCH modules
        "TJES": "BATCH",
        "OpenFrame-TJES": "BATCH",
        "SPOOL": "BATCH",
        "MVSSYS": "BATCH",
        "TSO": "BATCH",
        "PROSORT": "BATCH",
        # TACF (separate prefix)
        "TACF": "TACF",
        # AIM modules
        "AIM": "AIM",
        "AIMDB": "AIM",
        "AIMDBRP": "AIM",
        "AIM-RPC": "AIM",
        "AIM-IDCM": "AIM",
        "AIM-DC": "AIM",
        "AIMCOM": "AIM",
        "AIMACP": "AIM",
        "AIMCTL": "AIM",
        "AIMAIS": "AIM",
        "AIMSMR": "AIM",
        "AIMCMD": "AIM",
        "ADL": "AIM",
        "AIMTOOL": "AIM",
        "DDMS": "AIM",
        "PSAM": "AIM",
        # NDB modules
        "NDB": "NDB",
        "NDBMETA": "NDB",
        "NDBRSTD": "NDB",
        # Other modules (keep existing UNKNOWN prefix for compatibility)
        "HiDB": "UNKNOWN",
        "IMS": "UNKNOWN",
        "OSI": "UNKNOWN",
        "OSC": "UNKNOWN",
        "OUTQ": "BATCH",
        "CMD": "BASE",
        "COMMAND": "BASE",
    }
    return prefix_map.get(module_name, "UNKNOWN")


def get_range_bucket(code: int) -> int:
    """Get the range bucket for a module code.

    Uses the exact module code from the PDF section header,
    preserving 100-level granularity for AIM/NDB modules.
    """
    return abs(code)


def generate_markdown(module: ModuleEntry, prefix: str) -> str:
    """Generate markdown content for a module's error codes."""
    range_code = abs(module.range_code)
    range_bucket = get_range_bucket(range_code)

    # Sort errors by code
    errors = sorted(module.errors, key=lambda e: abs(e.code))

    # Generate markdown
    lines = [
        "---",
        "type: error-codes",
        f"module: {module.module_name}",
        f"range: -{range_bucket} ~ -{range_bucket + 999}",
        "language: ja",
        f"generated: {datetime.now().isoformat()}",
        "source_files:",
    ]
    for sf in module.source_files:
        lines.append(f"  - {sf}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {module.module_name} エラーコード (-{range_code})")
    lines.append("")
    lines.append("## モジュール概要")
    lines.append(module.description or f"{module.module_name}モジュールのエラーコードです。")
    lines.append("")
    lines.append("## エラー目録")
    lines.append("")

    filled_count = 0
    for error in errors:
        lines.append(f"### {error.name} ({error.code})")
        lines.append(f"- **설명**: {error.description}")
        lines.append(f"- **대처방법**: {error.solution}")
        if error.reference:
            lines.append(f"- **참고**: {error.reference}")
        lines.append("")

        if error.description:
            filled_count += 1

    return "\n".join(lines), len(errors), filled_count


def main():
    parser = argparse.ArgumentParser(description="Re-extract error descriptions from PDFs")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files, just report")
    parser.add_argument("--pdf", type=str, help="Process specific PDF only")
    parser.add_argument("--stats", action="store_true", help="Show statistics only")
    args = parser.parse_args()

    # Collect all errors from all PDFs
    all_modules: Dict[str, ModuleEntry] = {}

    pdfs_to_process = ERROR_GUIDE_PDFS
    if args.pdf:
        pdfs_to_process = [Path(args.pdf)]

    for pdf_path in pdfs_to_process:
        if not pdf_path.exists():
            logger.warning(f"PDF not found: {pdf_path}")
            continue

        modules = extract_from_pdf(pdf_path)

        # Merge into all_modules
        for name, module in modules.items():
            if name in all_modules:
                existing = all_modules[name]
                for sf in module.source_files:
                    if sf not in existing.source_files:
                        existing.source_files.append(sf)
                # Merge errors
                existing_codes = {e.code for e in existing.errors}
                for error in module.errors:
                    if error.code not in existing_codes:
                        existing.errors.append(error)
                    else:
                        for existing_error in existing.errors:
                            if existing_error.code == error.code:
                                if error.description and not existing_error.description:
                                    existing_error.description = error.description
                                    existing_error.solution = error.solution
                                    existing_error.reference = error.reference
                                break
            else:
                all_modules[name] = module

    # Group modules by file prefix and range bucket
    file_groups: Dict[str, List[ModuleEntry]] = {}

    for module_name, module in all_modules.items():
        prefix = get_module_prefix(module_name)
        range_bucket = get_range_bucket(module.range_code)
        file_key = f"{prefix}-{range_bucket}"

        if file_key not in file_groups:
            file_groups[file_key] = []
        file_groups[file_key].append(module)

    # Statistics
    total_errors = 0
    total_filled = 0
    total_empty = 0

    print("\n" + "=" * 70)
    print("  Error Code Description Re-extraction Report")
    print("=" * 70)

    # Process each file group
    for file_key, modules in sorted(file_groups.items()):
        filename = f"{file_key}.md"
        filepath = ERROR_CODES_DIR / filename

        # Merge all modules in this file group
        all_errors = []
        all_source_files = []
        group_module_name = modules[0].module_name
        group_desc = modules[0].description

        for module in modules:
            for error in module.errors:
                all_errors.append(error)
            for sf in module.source_files:
                if sf not in all_source_files:
                    all_source_files.append(sf)

            error_count = len(module.errors)
            filled_count = sum(1 for e in module.errors if e.description)
            empty_count = error_count - filled_count

            total_errors += error_count
            total_filled += filled_count
            total_empty += empty_count

            fill_pct = (filled_count / error_count * 100) if error_count > 0 else 0
            status = "OK" if fill_pct > 80 else "IMPROVED" if fill_pct > 0 else "EMPTY"

            print(f"  [{file_key:20s}] {module.module_name:20s} | {error_count:4d} errors | {filled_count:4d} filled | {fill_pct:5.1f}% | {status}")

        if not args.dry_run and not args.stats:
            # Create merged module for file writing
            merged = ModuleEntry(
                module_name=group_module_name,
                range_code=modules[0].range_code,
                description=group_desc,
                errors=all_errors,
                source_files=all_source_files,
            )
            content, _, _ = generate_markdown(merged, file_key.split("-")[0])

            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            logger.info(f"  Written: {filepath.name} ({len(all_errors)} errors)")

    print("\n" + "-" * 70)
    fill_pct = (total_filled / total_errors * 100) if total_errors > 0 else 0
    print(f"  Total: {total_errors} errors | {total_filled} filled | {total_empty} empty | {fill_pct:.1f}% filled")
    print("=" * 70)

    if args.dry_run:
        print("\n  [DRY RUN] No files were written. Remove --dry-run to write.")
    elif args.stats:
        print("\n  [STATS] No files were written. Remove --stats to write.")


if __name__ == "__main__":
    main()
