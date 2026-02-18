"""Legacy Chat Adapter - HOST domain knowledge → vLLM streaming chat.

Builds system prompts from dialect patterns, migration patterns,
and capability model knowledge, then streams responses via vLLM.
"""

import logging
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

        # Build system prompt
        lang_map = {"ja": "Japanese", "en": "English", "ko": "Korean"}
        system_prompt = _HOST_SYSTEM_PROMPT.format(
            migration_context=self._migration_context,
            dialect_context=self._dialect_context,
            analysis_context=_build_analysis_context(analysis_context),
            language=lang_map.get(language, "Japanese"),
        )

        yield {"type": "system_info", "system_type": "host"}

        try:
            token_count = 0
            async for token in adapter.generate_stream(
                question=message,
                context=system_prompt,
                max_new_tokens=1024,
                temperature=0.3,
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


# Singleton
_adapter_instance: Optional[LegacyChatAdapter] = None


def get_legacy_chat_adapter() -> LegacyChatAdapter:
    """Get or create LegacyChatAdapter singleton."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = LegacyChatAdapter()
    return _adapter_instance
