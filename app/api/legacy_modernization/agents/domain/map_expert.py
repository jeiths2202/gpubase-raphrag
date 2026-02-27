"""MAP Domain Expert Agent (2C).

Responsibility:
- BMS (CICS) / MFS (IMS) screen definition parsing
- Feature extraction (SCREEN_LAYOUT, FIELD_DEFINITION, ATTRIBUTE, MAPSET_STRUCTURE)
- Auto-detect BMS vs MFS dialect
"""

from ...core.event_bus import EventBus
from ...core.shared_state import SharedStateStore
from ...models.enums import AgentRole
from ...parsers.map_parser import MAPParser
from .expert_base import DomainExpertBase


class MAPExpertAgent(DomainExpertBase):
    """MAP domain expert with regex-based BMS/MFS parser."""

    def __init__(self, event_bus: EventBus, shared_state: SharedStateStore) -> None:
        super().__init__(
            role=AgentRole.MAP_EXPERT,
            parser=MAPParser(),
            event_bus=event_bus,
            shared_state=shared_state,
        )
