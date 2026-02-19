"""Legacy Chat Adapter - HOST domain knowledge → vLLM streaming chat.

Builds system prompts from dialect patterns, migration patterns,
and capability model knowledge, then streams responses via vLLM.
Supports source code line-by-line explanation mode.
"""

import logging
import re
from typing import Any, AsyncGenerator, Dict, Optional

from .legacy_knowledge import _DIALECT_PATTERNS, _MIGRATION_PATTERNS

logger = logging.getLogger(__name__)

# System prompt template for HOST legacy analysis chat
_HOST_SYSTEM_PROMPT = """You are a Legacy Mainframe Modernization Expert specializing in HOST system analysis.
You help engineers understand legacy COBOL, JCL, MAP (BMS/PSAM), and Assembler code,
and guide migration to TmaxSoft OpenFrame.

Your knowledge includes:
- IBM z/OS, MVS, MSP, and Fujitsu XSP/OSIV mainframe systems
- COBOL dialects: IBM Enterprise, Micro Focus, Fujitsu NetCOBOL
- CICS, IMS/DC, AIM/DC online transaction processing
- DB2, IMS/DLI, AIM/DB database systems
- JES2/JES3 batch processing, JCL syntax
- VSAM (KSDS, ESDS, RRDS), PDS, sequential file systems
- BMS screen maps, PSAM screen definitions

Migration knowledge:
{migration_context}

Dialect patterns:
{dialect_context}

{analysis_context}

Respond in {language}. Be specific and cite technical details.
When discussing migration, reference OpenFrame equivalents:
- CICS → OSC (OpenFrame CICS)
- IMS/DLI → HIDB (OpenFrame IMS)
- JES2/JES3 → TJES (Tmax Job Entry Subsystem)
- VSAM → TSAM (Tmax Sequential Access Method)
- DB2 → Tibero
- VTAM → VTAM-G / TCP/IP
"""


# Source code explanation prompt - line-by-line analysis
_SOURCE_EXPLANATION_PROMPT = """You are a Legacy Mainframe Source Code Analyst.
Analyze the following {asset_type} source code and explain what each section does.

Instructions:
- Explain each logical section/block of the code
- For each section, describe: what it does, why it matters, and any migration considerations
- Use clear section headers and structured formatting
- Include line number references where helpful
- Highlight any notable patterns, potential issues, or migration risks

{asset_type_guide}

Source file: {file_name}

```
{source_code}
```

Respond in {language}. Use Markdown formatting with headers (##, ###), bullet points, and code references.
"""

# Asset-type specific analysis guides
_ASSET_TYPE_GUIDES = {
    "jcl": """JCL Analysis Guide:
- Identify JOB, EXEC, DD statements and their parameters
- Explain PROCs and cataloged procedures
- Note dataset definitions (DSN, DISP, SPACE, DCB)
- Identify utility programs (IEBGENER, IEBCOPY, IDCAMS, SORT)
- Flag XSP-specific statements (backslash syntax) vs MVS JCL""",
    "cobol": """COBOL Analysis Guide:
- Explain each DIVISION (IDENTIFICATION, ENVIRONMENT, DATA, PROCEDURE)
- Describe SECTION and PARAGRAPH structure
- Note COPY/COPYBOOK references
- Identify EXEC CICS or EXEC SQL embedded commands
- Describe FILE-CONTROL and data definitions (FD, 01, 77 levels)
- Explain PERFORM, CALL, and control flow""",
    "asm": """Assembler Analysis Guide:
- Identify CSECT, DSECT, MACRO definitions
- Explain register usage conventions (R0-R15)
- Note SVC calls and system macros
- Describe USING/DROP register base addressing
- Identify I/O operations (GET, PUT, OPEN, CLOSE)
- Explain linkage conventions (BALR, BR 14)""",
    "map": """MAP/BMS Analysis Guide:
- Identify MAPSET and MAP definitions (DFHMSD, DFHMDI, DFHMDF)
- Explain field attributes (ATTRB, POS, LENGTH, INITIAL)
- Note cursor positioning and field validation
- Describe screen layout and field flow
- For PSAM: identify Fujitsu screen definitions""",
}

# Intent detection patterns for source code explanation requests
_SOURCE_EXPLAIN_PATTERNS = [
    # Korean
    r"이\s*소스.*(설명|분석|해석|알려)",
    r"소스\s*코드.*(설명|분석|해석|알려)",
    r"코드.*(설명|분석|해석).*해",
    r"라인\s*별.*설명",
    r"소스.*읽어",
    # Japanese
    r"このソース.*(説明|分析|解析|教)",
    r"ソースコード.*(説明|分析|解析|教)",
    r"コード.*(説明|分析|解析).*して",
    r"行ごと.*説明",
    r"ソース.*読[んみ]",
    r"ソース.*解説",
    # English
    r"explain\s+(this\s+)?(source|code)",
    r"(describe|analyze)\s+(this\s+)?(source|code)",
    r"line[\s-]*by[\s-]*line",
    r"what\s+does\s+this\s+(source|code)\s+do",
    r"walk.*through.*(source|code)",
]

_SOURCE_EXPLAIN_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SOURCE_EXPLAIN_PATTERNS]


def _is_source_explanation_request(message: str) -> bool:
    """Detect if the user is asking for source code explanation."""
    return any(p.search(message) for p in _SOURCE_EXPLAIN_COMPILED)


def _build_migration_context() -> str:
    """Build migration pattern context string."""
    lines = []
    for mp in _MIGRATION_PATTERNS:
        lines.append(f"- {mp['name']}: {mp['description']}")
        lines.append(f"  Recommendation: {mp['recommendation']}")
    return "\n".join(lines)


def _build_dialect_context() -> str:
    """Build dialect pattern context string."""
    lines = []
    for dialect, patterns in _DIALECT_PATTERNS.items():
        lines.append(f"[{dialect}]")
        for p in patterns:
            lines.append(f"  - {p['pattern']}: {p['note']} ({p['category']})")
    return "\n".join(lines)


def _build_analysis_context(ctx: Optional[Dict[str, Any]]) -> str:
    """Build analysis context section if available."""
    if not ctx:
        return ""
    parts = ["Current analysis context:"]
    if ctx.get("file_name"):
        parts.append(f"- File: {ctx['file_name']}")
    if ctx.get("asset_type"):
        parts.append(f"- Asset type: {ctx['asset_type']}")
    if ctx.get("target_product"):
        parts.append(f"- Target product: {ctx['target_product']}")
    if ctx.get("source_code_snippet"):
        snippet = ctx["source_code_snippet"][:1000]
        parts.append(f"- Source code snippet:\n```\n{snippet}\n```")
    return "\n".join(parts)


class LegacyChatAdapter:
    """Adapter for HOST domain knowledge chat via vLLM streaming."""

    def __init__(self):
        self._migration_context = _build_migration_context()
        self._dialect_context = _build_dialect_context()
        self._adapter = None

    def _get_adapter(self):
        """Get or create VLLMAdapter instance (lazy init)."""
        if self._adapter is None:
            from ...adapters.learning_llm.vllm_adapter import VLLMAdapter
            self._adapter = VLLMAdapter()
            logger.info(f"LegacyChatAdapter: VLLMAdapter created → {self._adapter.base_url}")
        return self._adapter

    async def stream_chat(
        self,
        message: str,
        language: str = "ja",
        analysis_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream chat response for HOST system questions.

        Yields SSE-compatible event dicts:
          {"type": "system_info", "system_type": "host"}
          {"type": "llm_token", "token": "...", "source_system": "host"}
          {"type": "done", "source_system": "host"}
        """
        adapter = self._get_adapter()
        lang_map = {"ja": "Japanese", "en": "English", "ko": "Korean"}
        lang_name = lang_map.get(language, "Japanese")

        # Check if this is a source explanation request
        source_code = self._extract_source_code(analysis_context)
        is_explain = _is_source_explanation_request(message) and source_code

        if is_explain:
            asset_type = (analysis_context or {}).get("asset_type", "cobol")
            file_name = (analysis_context or {}).get("file_name", "unknown")
            system_prompt = _SOURCE_EXPLANATION_PROMPT.format(
                asset_type=asset_type.upper(),
                asset_type_guide=_ASSET_TYPE_GUIDES.get(asset_type, ""),
                file_name=file_name,
                source_code=source_code,
                language=lang_name,
            )
            max_tokens = 4096
            temperature = 0.1
            logger.info(
                f"Source explanation mode: {file_name} ({asset_type}), "
                f"{len(source_code)} chars"
            )
        else:
            system_prompt = _HOST_SYSTEM_PROMPT.format(
                migration_context=self._migration_context,
                dialect_context=self._dialect_context,
                analysis_context=_build_analysis_context(analysis_context),
                language=lang_name,
            )
            max_tokens = 1024
            temperature = 0.3

        yield {"type": "system_info", "system_type": "host"}

        if is_explain:
            yield {
                "type": "source_explanation_start",
                "file_name": (analysis_context or {}).get("file_name", ""),
                "asset_type": (analysis_context or {}).get("asset_type", ""),
                "source_system": "host",
            }

        try:
            token_count = 0
            async for token in adapter.generate_stream(
                question=message,
                context=system_prompt,
                max_new_tokens=max_tokens,
                temperature=temperature,
                product="openframe_base",
            ):
                token_count += 1
                yield {"type": "llm_token", "token": token, "source_system": "host"}

            if token_count == 0:
                yield {
                    "type": "llm_token",
                    "token": "No response from LLM. Please check the vLLM server status.",
                    "source_system": "host",
                }

            yield {"type": "done", "source_system": "host"}

        except Exception as e:
            logger.error(f"LegacyChatAdapter stream error: {e}")
            yield {"type": "error", "message": str(e), "source_system": "host"}

    @staticmethod
    def _extract_source_code(ctx: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract full source code from analysis context, with fallback to snippet."""
        if not ctx:
            return None
        return ctx.get("source_code_full") or ctx.get("source_code_snippet") or None


# Singleton
_adapter_instance: Optional[LegacyChatAdapter] = None


def get_legacy_chat_adapter() -> LegacyChatAdapter:
    """Get or create LegacyChatAdapter singleton."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = LegacyChatAdapter()
    return _adapter_instance
