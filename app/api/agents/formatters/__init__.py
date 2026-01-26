"""
Formatters for agent responses.
Provides direct return formatting without LLM intervention.
"""

from .direct_return_formatter import (
    DirectReturnFormatter,
    HybridModeDecision,
)
# ResponseMode is defined in types.py to avoid circular imports
from ..types import ResponseMode

__all__ = [
    "DirectReturnFormatter",
    "ResponseMode",
    "HybridModeDecision",
]
