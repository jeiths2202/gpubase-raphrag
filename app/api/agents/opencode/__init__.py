"""
OpenCode AI Agent Module

Document-Grounded Autonomous Execution with Hallucination Detection.

This module implements the OpenCode specification:
- 5-step mandatory workflow (keyword extraction -> summary search -> PDF verification -> tool selection -> answer generation)
- Automatic hallucination detection with retry (max 3 attempts)
- Vision LLM integration for visual content
- PostgreSQL execution logging
- Detailed progress streaming to UI
"""

from .types import (
    OpenCodeContext,
    OpenCodeResult,
    StepResult,
    StepStatus,
    ToolType,
    ExtractedKeywords,
    SummarySearchResult,
    PDFVerificationResult,
    ToolSelectionResult,
    HallucinationCheckResult,
    OpenCodeConfig,
)

from .executor import OpenCodeExecutor, get_opencode_executor

from .hallucination_detector import (
    HallucinationDetector,
    get_hallucination_detector,
)

__all__ = [
    # Types
    "OpenCodeContext",
    "OpenCodeResult",
    "StepResult",
    "StepStatus",
    "ToolType",
    "ExtractedKeywords",
    "SummarySearchResult",
    "PDFVerificationResult",
    "ToolSelectionResult",
    "HallucinationCheckResult",
    "OpenCodeConfig",
    # Executor
    "OpenCodeExecutor",
    "get_opencode_executor",
    # Hallucination detection
    "HallucinationDetector",
    "get_hallucination_detector",
]
