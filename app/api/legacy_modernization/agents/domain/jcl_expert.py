"""JCL Domain Expert Agent (2B).

Responsibility:
- JCL source -> column-based parsing
- Feature extraction (JOB, EXEC, DD, PROC, GDG, VSAM, UTILITY, JES_CONTROL)
- Dialect detection (mvs, jes2, jes3)
"""

from ...core.event_bus import EventBus
from ...core.shared_state import SharedStateStore
from ...models.enums import AgentRole
from ...parsers.jcl_parser import JCLParser
from .expert_base import DomainExpertBase


class JCLExpertAgent(DomainExpertBase):
    """JCL domain expert with column-based parser."""

    def __init__(self, event_bus: EventBus, shared_state: SharedStateStore) -> None:
        super().__init__(
            role=AgentRole.JCL_EXPERT,
            parser=JCLParser(),
            event_bus=event_bus,
            shared_state=shared_state,
        )
