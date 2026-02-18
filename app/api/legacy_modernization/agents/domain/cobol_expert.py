"""COBOL Domain Expert Agent (2A).

Responsibility:
- COBOL source -> AST parsing (Tree-sitter with regex fallback)
- Feature extraction (CICS, DB2, IMS, FILE I/O, COPYBOOK, CALL, STRING, SORT)
- Trace evidence generation

Immutable rule: Parser results cannot be modified by non-parser agents.
"""

from ...core.event_bus import EventBus
from ...core.shared_state import SharedStateStore
from ...models.enums import AgentRole
from ...parsers.cobol_parser import COBOLParser
from .expert_base import DomainExpertBase


class COBOLExpertAgent(DomainExpertBase):
    """COBOL domain expert with Tree-sitter AST + regex fallback."""

    def __init__(self, event_bus: EventBus, shared_state: SharedStateStore) -> None:
        super().__init__(
            role=AgentRole.COBOL_EXPERT,
            parser=COBOLParser(),
            event_bus=event_bus,
            shared_state=shared_state,
        )
