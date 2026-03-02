"""Knowledge extraction: ManualSection → ProductKnowledge."""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Dict, List, Set

from .config import GenerationConfig
from .manual_loader import PRODUCT_DISPLAY_NAMES
from .models import (
    APIItem,
    CommandItem,
    ConfigItem,
    ErrorItem,
    FeatureItem,
    ItemType,
    KnowledgeItem,
    Language,
    LimitationItem,
    ManualSection,
    MigrationItem,
    ProductKnowledge,
)

logger = logging.getLogger(__name__)

# ── Extraction Patterns (multilingual) ───────────────────────────

_COMMAND_PATTERNS = [
    re.compile(
        r"^([\w]+)\s+(?:コマンド|command|명령어)", re.MULTILINE | re.IGNORECASE
    ),
    re.compile(r"(?:構文|syntax|구문)\s*[:：]\s*(.+)", re.IGNORECASE),
    re.compile(r"^([a-z]\w*mgr)\s+(\w+)", re.MULTILINE),
]

_ERROR_PATTERNS = [
    re.compile(r"(-\d{4,5})\s*[:：]?\s*(.+)", re.MULTILINE),
    re.compile(
        r"(?:エラーコード|error\s*code|에러\s*코드)\s*[:：]?\s*(-?\d{4,5})",
        re.IGNORECASE,
    ),
]

_CONFIG_PATTERNS = [
    re.compile(r"^(\w[\w.]+)\s*=\s*(.+)", re.MULTILINE),
    re.compile(
        r"(?:パラメータ|parameter|파라미터)\s*[:：]?\s*(\w+)", re.IGNORECASE
    ),
]

_API_PATTERNS = [
    re.compile(r"^(\w+)\s*\(([^)]*)\)\s*→?\s*(.*)", re.MULTILINE),
    re.compile(r"(?:関数|function|함수)\s*[:：]?\s*(\w+)", re.IGNORECASE),
]

_FEATURE_PATTERNS = [
    re.compile(r"(?:機能|feature|기능)\s*[:：]?\s*(.+)", re.IGNORECASE),
    re.compile(r"(?:概要|overview|개요)", re.IGNORECASE),
]

_LIMITATION_PATTERNS = [
    re.compile(
        r"(?:制限|limitation|제한|注意|caution|주의)", re.IGNORECASE
    ),
]

_MIGRATION_PATTERNS = [
    re.compile(
        r"(?:移行|migration|마이그레이션|変換|convert|변환)", re.IGNORECASE
    ),
]

# Patterns for extracting sub-fields
_CAUSE_RE = re.compile(
    r"(?:原因|cause|원인)\s*[:：]\s*(.+?)(?:\n|$)", re.IGNORECASE
)
_RESOLUTION_RE = re.compile(
    r"(?:対処|対応|resolution|해결|조치)\s*[:：]\s*(.+?)(?:\n|$)", re.IGNORECASE
)
_DEFAULT_VALUE_RE = re.compile(
    r"(?:デフォルト|default|기본값)\s*[:：]?\s*(.+?)(?:\n|$)", re.IGNORECASE
)
_PARAM_LINE_RE = re.compile(
    r"^\s*[-・●]\s*(\w[\w_]*)\s*[:：]\s*(.+)", re.MULTILINE
)
_EXAMPLE_BLOCK_RE = re.compile(
    r"(?:例|example|예시)\s*[:：]?\s*\n((?:\s+.+\n?)+)", re.IGNORECASE
)
_CODE_BLOCK_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_WORKAROUND_RE = re.compile(
    r"(?:回避策|workaround|대안)\s*[:：]\s*(.+?)(?:\n|$)", re.IGNORECASE
)
_SEVERITY_RE = re.compile(
    r"(?:重大度|severity|심각도)\s*[:：]?\s*(\w+)", re.IGNORECASE
)
_RETURN_TYPE_RE = re.compile(
    r"(?:戻り値|return|반환)\s*[:：]?\s*(.+?)(?:\n|$)", re.IGNORECASE
)

# ── Extraction Filters ──────────────────────────────────────────

# Words that should never be extracted as API function names
_SKIP_API_NAMES: set = {
    # C keywords and types
    "if", "else", "for", "while", "do", "switch", "case", "break", "continue",
    "return", "sizeof", "typeof", "void", "int", "char", "float", "double",
    "long", "short", "unsigned", "struct", "enum", "union", "class", "typedef",
    "static", "extern", "const", "register", "volatile",
    # C standard library
    "main", "printf", "fprintf", "sprintf", "snprintf", "scanf", "sscanf",
    "malloc", "calloc", "realloc", "free", "memcpy", "memset", "memmove",
    "strlen", "strcmp", "strncmp", "strcpy", "strncpy", "strcat", "strncat",
    "strstr", "strchr", "strrchr", "strtok",
    "fopen", "fclose", "fread", "fwrite", "fgets", "fputs", "fseek", "ftell",
    "exit", "abort", "atexit", "atoi", "atol", "atof", "strtol", "strtod",
    # Common non-API identifiers
    "true", "false", "null", "NULL", "none", "None",
    "result", "data", "value", "count", "size", "name", "type", "status",
    "error", "code", "message", "index", "key", "buf", "len", "ret", "rc",
    "get", "set", "put", "add", "remove", "delete", "new", "init", "close",
    "open", "read", "write", "send", "recv",
}

# Detects lines that are C/programming code (not documentation)
_CODE_LINE_INDICATOR_RE = re.compile(
    r"[{};]\s*$|"
    r"^\s*#\s*(?:include|define|ifdef|ifndef|endif|pragma)|"
    r"^\s*(?:int|void|char|float|double|unsigned|struct|enum|class|return|static|extern)\s|"
    r"\*\s*\w+\s*=|&\w+\b|->|<<|>>"
)

# Value-side patterns indicating code, not config values
_CODE_VALUE_INDICATOR_RE = re.compile(
    r"(?:malloc|calloc|sizeof|new\s+\w|NULL|nullptr|"
    r"\.\w+\(|;\s*$|\)\s*\{|->|<<|>>)"
)

# Detects error-code-like arguments in function call patterns (e.g., "-57019")
_ERROR_CODE_ARGS_RE = re.compile(r"^\s*-?\d{3,6}\s*$")

# CJK character ranges — names containing these are descriptions, not identifiers
_CJK_RE = re.compile(
    r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\uac00-\ud7af]"
)


class KnowledgeExtractor:
    """Extract structured knowledge from manual sections."""

    def __init__(self, config: GenerationConfig):
        self.config = config

    # ── Public API ────────────────────────────────────────────────

    def extract_all(
        self, sections: List[ManualSection]
    ) -> Dict[str, ProductKnowledge]:
        """Extract knowledge from all sections, grouped by product."""
        by_product: Dict[str, List[ManualSection]] = defaultdict(list)
        for sec in sections:
            by_product[sec.product].append(sec)

        result: Dict[str, ProductKnowledge] = {}
        for product, product_sections in by_product.items():
            display = PRODUCT_DISPLAY_NAMES.get(product, product)
            lang = product_sections[0].language if product_sections else Language.JA

            pk = ProductKnowledge(
                product=product, display_name=display, language=lang
            )

            for sec in product_sections:
                extracted = self._extract_from_section(sec)
                pk.commands.extend(extracted.get("commands", []))
                pk.errors.extend(extracted.get("errors", []))
                pk.configs.extend(extracted.get("configs", []))
                pk.apis.extend(extracted.get("apis", []))
                pk.features.extend(extracted.get("features", []))
                pk.limitations.extend(extracted.get("limitations", []))
                pk.migrations.extend(extracted.get("migrations", []))

            # Deduplicate within product
            pk.commands = self._deduplicate_items(pk.commands)
            pk.errors = self._deduplicate_items(pk.errors)
            pk.configs = self._deduplicate_items(pk.configs)
            pk.apis = self._deduplicate_items(pk.apis)
            pk.features = self._deduplicate_items(pk.features)
            pk.limitations = self._deduplicate_items(pk.limitations)
            pk.migrations = self._deduplicate_items(pk.migrations)

            result[product] = pk
            logger.info(
                "  %s: %d items (%d cmd, %d err, %d cfg, %d api, %d feat)",
                product,
                pk.total_items,
                len(pk.commands),
                len(pk.errors),
                len(pk.configs),
                len(pk.apis),
                len(pk.features),
            )

        logger.info(
            "Knowledge extraction: %d products, %d total items",
            len(result),
            sum(pk.total_items for pk in result.values()),
        )
        return result

    # ── Per-section extraction ────────────────────────────────────

    def _extract_from_section(
        self, section: ManualSection
    ) -> Dict[str, List]:
        """Run all extraction patterns on a single section."""
        result: Dict[str, List] = {
            "commands": [],
            "errors": [],
            "configs": [],
            "apis": [],
            "features": [],
            "limitations": [],
            "migrations": [],
        }

        tags = set(section.tags)

        if ItemType.COMMAND in tags or not tags - {ItemType.CONCEPT}:
            result["commands"] = self._extract_commands(section)

        if ItemType.ERROR in tags:
            result["errors"] = self._extract_errors(section)

        if ItemType.CONFIG in tags:
            result["configs"] = self._extract_configs(section)

        if ItemType.API in tags:
            result["apis"] = self._extract_apis(section)

        if ItemType.LIMITATION in tags:
            result["limitations"] = self._extract_limitations(section)

        if ItemType.MIGRATION in tags:
            result["migrations"] = self._extract_migrations(section)

        # Features from concept/overview sections
        if ItemType.CONCEPT in tags:
            result["features"] = self._extract_features(section)

        return result

    # ── Command extraction ────────────────────────────────────────

    def _extract_commands(self, section: ManualSection) -> List[CommandItem]:
        items: List[CommandItem] = []
        content = section.content
        found_names: Set[str] = set()

        for pattern in _COMMAND_PATTERNS:
            for m in pattern.finditer(content):
                name = m.group(1).strip()
                if len(name) < 2 or len(name) > 60 or name in found_names:
                    continue
                found_names.add(name)

                # Extract syntax
                syntax = ""
                syntax_m = re.search(
                    r"(?:構文|syntax|구문)\s*[:：]\s*(.+)",
                    content[m.start() :],
                    re.IGNORECASE,
                )
                if syntax_m:
                    syntax = syntax_m.group(1).strip()[:200]

                # Extract parameters
                params = self._extract_parameters(content[m.start() :])

                # Extract examples
                examples = self._extract_examples(content[m.start() :])

                # Context: surrounding 500 chars
                ctx_start = max(0, m.start() - 100)
                ctx_end = min(len(content), m.end() + 400)
                context = content[ctx_start:ctx_end]

                description = self._extract_nearby_description(
                    content, m.start(), section.section_title
                )

                items.append(
                    CommandItem(
                        name=name,
                        description=description,
                        product=section.product,
                        source_file=section.source_file,
                        source_page=(
                            section.page_range[0] if section.page_range else 0
                        ),
                        language=section.language,
                        context=context,
                        syntax=syntax,
                        parameters=params,
                        examples=examples,
                    )
                )

        return items

    # ── Error extraction ──────────────────────────────────────────

    def _extract_errors(self, section: ManualSection) -> List[ErrorItem]:
        items: List[ErrorItem] = []
        content = section.content
        found_codes: Set[str] = set()

        for pattern in _ERROR_PATTERNS:
            for m in pattern.finditer(content):
                code = m.group(1).strip()
                if code in found_codes:
                    continue
                found_codes.add(code)

                desc = m.group(2).strip() if m.lastindex >= 2 else ""

                # Extract cause/resolution from nearby text
                nearby = content[m.start() : min(len(content), m.start() + 500)]
                cause = ""
                cause_m = _CAUSE_RE.search(nearby)
                if cause_m:
                    cause = cause_m.group(1).strip()

                resolution = ""
                res_m = _RESOLUTION_RE.search(nearby)
                if res_m:
                    resolution = res_m.group(1).strip()

                severity = ""
                sev_m = _SEVERITY_RE.search(nearby)
                if sev_m:
                    severity = sev_m.group(1).strip()

                # Determine module from product or section title
                module = section.section_title.split()[0] if section.section_title else ""

                items.append(
                    ErrorItem(
                        name=code,
                        description=desc[:300],
                        product=section.product,
                        source_file=section.source_file,
                        source_page=(
                            section.page_range[0] if section.page_range else 0
                        ),
                        language=section.language,
                        context=nearby,
                        error_code=code,
                        module=module,
                        cause=cause[:300],
                        resolution=resolution[:300],
                        severity=severity,
                    )
                )

        return items

    # ── Config extraction ─────────────────────────────────────────

    def _extract_configs(self, section: ManualSection) -> List[ConfigItem]:
        items: List[ConfigItem] = []
        content = section.content
        found_names: Set[str] = set()

        for pattern in _CONFIG_PATTERNS:
            for m in pattern.finditer(content):
                name = m.group(1).strip()
                if len(name) < 2 or len(name) > 80 or name in found_names:
                    continue
                # Skip common false positives
                if name.lower() in ("true", "false", "null", "none", "yes", "no"):
                    continue

                # Skip names containing CJK characters (descriptions, not identifiers)
                if _CJK_RE.search(name):
                    continue

                # Skip if the matched line looks like C/programming code
                line_start = content.rfind("\n", 0, m.start()) + 1
                line_end = content.find("\n", m.end())
                if line_end == -1:
                    line_end = len(content)
                matched_line = content[line_start:line_end]
                if _CODE_LINE_INDICATOR_RE.search(matched_line):
                    continue

                # Skip if the value part looks like code
                value_part = m.group(2).strip() if m.lastindex >= 2 else ""
                if value_part and _CODE_VALUE_INDICATOR_RE.search(value_part):
                    continue

                found_names.add(name)

                default_val = ""
                if m.lastindex >= 2:
                    default_val = m.group(2).strip()[:100]

                nearby = content[m.start() : min(len(content), m.start() + 400)]

                # Try to find default value pattern
                def_m = _DEFAULT_VALUE_RE.search(nearby)
                if def_m:
                    default_val = def_m.group(1).strip()[:100]

                # Determine config file from section title
                config_file = ""
                for ext in (".conf", ".cfg", ".properties", ".xml", ".ini"):
                    if ext in section.section_title.lower():
                        config_file = section.section_title
                        break

                description = self._extract_nearby_description(
                    content, m.start(), section.section_title
                )

                items.append(
                    ConfigItem(
                        name=name,
                        description=description,
                        product=section.product,
                        source_file=section.source_file,
                        source_page=(
                            section.page_range[0] if section.page_range else 0
                        ),
                        language=section.language,
                        context=nearby,
                        parameter_name=name,
                        default_value=default_val,
                        config_file=config_file,
                    )
                )

        return items

    # ── API extraction ────────────────────────────────────────────

    def _extract_apis(self, section: ManualSection) -> List[APIItem]:
        items: List[APIItem] = []
        content = section.content
        found_names: Set[str] = set()

        for pattern in _API_PATTERNS:
            for m in pattern.finditer(content):
                name = m.group(1).strip()
                if len(name) < 2 or len(name) > 80 or name in found_names:
                    continue

                # Skip C/programming keywords and common function names
                if name.lower() in _SKIP_API_NAMES:
                    continue

                # Skip names containing CJK characters (descriptions, not identifiers)
                if _CJK_RE.search(name):
                    continue

                # Skip if the "arguments" are an error code (e.g., "-57019")
                args_str = m.group(2).strip() if m.lastindex >= 2 else ""
                if args_str and _ERROR_CODE_ARGS_RE.match(args_str):
                    continue

                # Skip if the matched line looks like C/programming code
                line_start = content.rfind("\n", 0, m.start()) + 1
                line_end = content.find("\n", m.end())
                if line_end == -1:
                    line_end = len(content)
                matched_line = content[line_start:line_end]
                if _CODE_LINE_INDICATOR_RE.search(matched_line):
                    continue

                found_names.add(name)

                signature = m.group(0).strip()[:200]
                params_str = m.group(2).strip() if m.lastindex >= 2 else ""
                return_type = m.group(3).strip() if m.lastindex >= 3 else ""

                # Parse parameters
                params: List[Dict[str, str]] = []
                if params_str:
                    for p in params_str.split(","):
                        p = p.strip()
                        if p:
                            params.append({"name": p, "description": ""})

                nearby = content[m.start() : min(len(content), m.start() + 500)]

                # Try return type
                if not return_type:
                    rt_m = _RETURN_TYPE_RE.search(nearby)
                    if rt_m:
                        return_type = rt_m.group(1).strip()[:100]

                examples = self._extract_examples(nearby)

                description = self._extract_nearby_description(
                    content, m.start(), section.section_title
                )

                items.append(
                    APIItem(
                        name=name,
                        description=description,
                        product=section.product,
                        source_file=section.source_file,
                        source_page=(
                            section.page_range[0] if section.page_range else 0
                        ),
                        language=section.language,
                        context=nearby,
                        signature=signature,
                        parameters=params,
                        return_type=return_type,
                        examples=examples,
                    )
                )

        return items

    # ── Feature extraction ────────────────────────────────────────

    def _extract_features(self, section: ManualSection) -> List[FeatureItem]:
        items: List[FeatureItem] = []
        content = section.content

        for pattern in _FEATURE_PATTERNS:
            m = pattern.search(content)
            if m:
                name = section.section_title or (
                    m.group(1).strip() if m.lastindex >= 1 else "Feature"
                )
                # Use section content as description (truncated)
                desc = content[:500].strip()

                items.append(
                    FeatureItem(
                        name=name,
                        description=desc,
                        product=section.product,
                        source_file=section.source_file,
                        source_page=(
                            section.page_range[0] if section.page_range else 0
                        ),
                        language=section.language,
                        context=content[:500],
                        category=section.section_title,
                    )
                )
                break  # One feature per section

        return items

    # ── Limitation extraction ─────────────────────────────────────

    def _extract_limitations(
        self, section: ManualSection
    ) -> List[LimitationItem]:
        items: List[LimitationItem] = []
        content = section.content

        for pattern in _LIMITATION_PATTERNS:
            if pattern.search(content):
                workaround = ""
                wa_m = _WORKAROUND_RE.search(content)
                if wa_m:
                    workaround = wa_m.group(1).strip()[:300]

                items.append(
                    LimitationItem(
                        name=section.section_title or "Limitation",
                        description=content[:500].strip(),
                        product=section.product,
                        source_file=section.source_file,
                        source_page=(
                            section.page_range[0] if section.page_range else 0
                        ),
                        language=section.language,
                        context=content[:500],
                        scope=section.section_title,
                        workaround=workaround,
                    )
                )
                break

        return items

    # ── Migration extraction ──────────────────────────────────────

    def _extract_migrations(
        self, section: ManualSection
    ) -> List[MigrationItem]:
        items: List[MigrationItem] = []
        content = section.content
        title_lower = (section.section_title or "").lower()

        # Require migration keywords in the SECTION TITLE, not just content body.
        # This prevents error-code sections that incidentally mention "移行" from
        # being misclassified as migration content.
        has_migration_title = bool(re.search(
            r"(?:移行|migration|마이그레이션|変換|convert|変換)",
            title_lower,
            re.IGNORECASE,
        ))
        if not has_migration_title:
            return items

        for pattern in _MIGRATION_PATTERNS:
            if pattern.search(content):
                # Try to detect source/target platforms
                source = ""
                target = ""
                platform_m = re.search(
                    r"(?:から|from)\s*(\w[\w\s/]*?)(?:へ|to|으로)\s*(\w[\w\s/]*)",
                    content,
                    re.IGNORECASE,
                )
                if platform_m:
                    source = platform_m.group(1).strip()[:50]
                    target = platform_m.group(2).strip()[:50]

                # Extract numbered steps
                steps: List[str] = []
                step_matches = re.finditer(
                    r"(?:^\s*\d+[.．)）]\s*(.+))$", content, re.MULTILINE
                )
                for sm in step_matches:
                    step = sm.group(1).strip()
                    if len(step) > 5:
                        steps.append(step[:200])

                items.append(
                    MigrationItem(
                        name=section.section_title or "Migration",
                        description=content[:500].strip(),
                        product=section.product,
                        source_file=section.source_file,
                        source_page=(
                            section.page_range[0] if section.page_range else 0
                        ),
                        language=section.language,
                        context=content[:500],
                        source_platform=source,
                        target_platform=target,
                        steps=steps[:20],
                    )
                )
                break

        return items

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _extract_nearby_description(
        content: str, match_pos: int, fallback: str = ""
    ) -> str:
        """Extract a meaningful description from text near a regex match.

        Looks at lines following the matched pattern for descriptive text,
        rather than using the section title as a generic placeholder.
        """
        nearby = content[match_pos:match_pos + 500]
        lines = nearby.split("\n")

        # Try lines after the match line for a descriptive sentence
        for line in lines[1:5]:
            stripped = line.strip()
            if (
                len(stripped) > 20
                and not stripped.startswith(("-", "●", "・", "*", "#", "```", "//"))
                and not re.match(r"^\s*\d+[.．)）]", stripped)
                and not re.match(r"^\s*[-=]+\s*$", stripped)
            ):
                return stripped[:300]

        return fallback

    @staticmethod
    def _extract_parameters(text: str) -> List[Dict[str, str]]:
        """Extract parameter list from nearby text."""
        params: List[Dict[str, str]] = []
        for m in _PARAM_LINE_RE.finditer(text[:1000]):
            params.append(
                {"name": m.group(1).strip(), "description": m.group(2).strip()[:200]}
            )
        return params[:20]

    @staticmethod
    def _extract_examples(text: str) -> List[str]:
        """Extract code examples from text."""
        examples: List[str] = []

        # Try code blocks first
        for m in _CODE_BLOCK_RE.finditer(text[:2000]):
            ex = m.group(1).strip()
            if ex:
                examples.append(ex[:500])

        # Try indented example blocks
        if not examples:
            for m in _EXAMPLE_BLOCK_RE.finditer(text[:2000]):
                ex = m.group(1).strip()
                if ex:
                    examples.append(ex[:500])

        return examples[:5]

    @staticmethod
    def _deduplicate_items(items: List) -> List:
        """Remove items with duplicate (name, type) within a product."""
        seen: Set[str] = set()
        unique: List = []
        for item in items:
            key = f"{type(item).__name__}:{item.name}"
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique
