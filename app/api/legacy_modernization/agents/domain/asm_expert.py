"""ASM Domain Expert Agent (2D).

Responsibility:
- HLASM source -> column-based parsing
- Feature extraction (MACRO_USAGE, SUPERVISOR_CALL, ADDRESSING, BRANCH, DSECT_STRUCTURE, DATA_DEFINITION)
- SVC number -> service name mapping
- Dialect detection (hlasm, hlasm_zos, hlasm_zvse)
"""

from ...core.event_bus import EventBus
from ...core.shared_state import SharedStateStore
from ...models.enums import AgentRole
from ...parsers.asm_parser import ASMParser
from .expert_base import DomainExpertBase


class ASMExpertAgent(DomainExpertBase):
    """ASM domain expert with HLASM column-based parser."""

    def __init__(self, event_bus: EventBus, shared_state: SharedStateStore) -> None:
        super().__init__(
            role=AgentRole.ASM_EXPERT,
            parser=ASMParser(),
            event_bus=event_bus,
            shared_state=shared_state,
        )
