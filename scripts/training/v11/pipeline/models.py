"""Core data models for the Qwen3 dataset pipeline."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Enums ──────────────────────────────────────────────────────────


class Language(str, enum.Enum):
    JA = "ja"
    KO = "ko"
    EN = "en"


class ItemType(str, enum.Enum):
    COMMAND = "command"
    ERROR = "error"
    CONFIG = "config"
    API = "api"
    CONCEPT = "concept"
    PROCEDURE = "procedure"
    LIMITATION = "limitation"
    MIGRATION = "migration"


class SFTCategory(str, enum.Enum):
    SINGLE_PRODUCT = "single_product"
    CROSS_PRODUCT = "cross_product"
    ARCHITECTURE = "architecture"


class DPOStrategy(str, enum.Enum):
    CROSS_PRODUCT = "cross_product"
    FACT_MUTATION = "fact_mutation"
    OVER_CLAIMING = "over_claiming"
    SPECULATIVE = "speculative"


# ── Manual Loader Models ───────────────────────────────────────────


@dataclass
class ManualSection:
    """A semantic section extracted from a product manual."""

    product: str
    section_title: str
    content: str
    source_file: str
    page_range: Optional[Tuple[int, int]]
    language: Language
    tags: List[ItemType] = field(default_factory=list)
    char_count: int = 0

    def __post_init__(self):
        self.char_count = len(self.content)


# ── Knowledge Extraction Models ────────────────────────────────────


@dataclass
class KnowledgeItem:
    """Base for extracted knowledge items."""

    name: str
    description: str
    product: str
    source_file: str
    source_page: int = 0
    language: Language = Language.JA
    context: str = ""


@dataclass
class CommandItem(KnowledgeItem):
    syntax: str = ""
    parameters: List[Dict[str, str]] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    return_codes: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class ErrorItem(KnowledgeItem):
    error_code: str = ""
    module: str = ""
    cause: str = ""
    resolution: str = ""
    severity: str = ""


@dataclass
class ConfigItem(KnowledgeItem):
    parameter_name: str = ""
    default_value: str = ""
    valid_values: List[str] = field(default_factory=list)
    config_file: str = ""


@dataclass
class APIItem(KnowledgeItem):
    signature: str = ""
    parameters: List[Dict[str, str]] = field(default_factory=list)
    return_type: str = ""
    examples: List[str] = field(default_factory=list)


@dataclass
class FeatureItem(KnowledgeItem):
    category: str = ""
    related_components: List[str] = field(default_factory=list)


@dataclass
class LimitationItem(KnowledgeItem):
    scope: str = ""
    workaround: str = ""


@dataclass
class MigrationItem(KnowledgeItem):
    source_platform: str = ""
    target_platform: str = ""
    steps: List[str] = field(default_factory=list)
    considerations: List[str] = field(default_factory=list)


@dataclass
class ProductKnowledge:
    """Structured knowledge graph for a single product."""

    product: str
    display_name: str
    language: Language
    commands: List[CommandItem] = field(default_factory=list)
    errors: List[ErrorItem] = field(default_factory=list)
    configs: List[ConfigItem] = field(default_factory=list)
    apis: List[APIItem] = field(default_factory=list)
    features: List[FeatureItem] = field(default_factory=list)
    limitations: List[LimitationItem] = field(default_factory=list)
    migrations: List[MigrationItem] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        return (
            len(self.commands)
            + len(self.errors)
            + len(self.configs)
            + len(self.apis)
            + len(self.features)
            + len(self.limitations)
            + len(self.migrations)
        )

    def all_items(self) -> List[KnowledgeItem]:
        """Return all items in a flat list."""
        items: List[KnowledgeItem] = []
        items.extend(self.commands)
        items.extend(self.errors)
        items.extend(self.configs)
        items.extend(self.apis)
        items.extend(self.features)
        items.extend(self.limitations)
        items.extend(self.migrations)
        return items


# ── SFT / DPO Output Models ───────────────────────────────────────


@dataclass
class SFTRecord:
    """A single SFT training sample in messages format."""

    messages: List[Dict[str, str]]
    product: str
    language: Language
    category: SFTCategory
    item_type: ItemType
    source_file: str
    source_page: int = 0
    products_involved: List[str] = field(default_factory=list)

    def to_jsonl(self) -> dict:
        return {
            "messages": self.messages,
            "metadata": {
                "product": self.product,
                "language": self.language.value,
                "category": self.category.value,
                "item_type": self.item_type.value,
                "source_file": self.source_file,
                "source_page": self.source_page,
                "products_involved": self.products_involved,
            },
        }

    @property
    def user_text(self) -> str:
        for m in self.messages:
            if m["role"] == "user":
                return m["content"]
        return ""

    @property
    def assistant_text(self) -> str:
        for m in self.messages:
            if m["role"] == "assistant":
                return m["content"]
        return ""


@dataclass
class DPORecord:
    """A single DPO preference pair."""

    prompt: str
    chosen: str
    rejected: str
    product: str
    language: Language
    strategy: DPOStrategy
    source_file: str = ""
    products_involved: List[str] = field(default_factory=list)

    def to_jsonl(self) -> dict:
        return {
            "prompt": self.prompt,
            "chosen": self.chosen,
            "rejected": self.rejected,
            "metadata": {
                "product": self.product,
                "language": self.language.value,
                "strategy": self.strategy.value,
                "source_file": self.source_file,
                "products_involved": self.products_involved,
            },
        }


@dataclass
class CPTChunk:
    """A single CPT plain-text chunk."""

    text: str
    product: str
    language: Language
    source_file: str
    estimated_tokens: int = 0


# ── Statistics & Report Models ─────────────────────────────────────


@dataclass
class DatasetStats:
    """Pipeline output statistics."""

    sft_total: int = 0
    sft_by_category: Dict[str, int] = field(default_factory=dict)
    sft_by_product: Dict[str, int] = field(default_factory=dict)
    sft_by_language: Dict[str, int] = field(default_factory=dict)
    sft_by_type: Dict[str, int] = field(default_factory=dict)
    sft_train: int = 0
    sft_eval: int = 0

    dpo_total: int = 0
    dpo_by_strategy: Dict[str, int] = field(default_factory=dict)
    dpo_train: int = 0
    dpo_eval: int = 0

    cpt_chunks: int = 0
    cpt_total_tokens: int = 0

    dedup_removed: int = 0
    scaling_added: int = 0
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)

    token_length_p50: int = 0
    token_length_p95: int = 0
    token_length_p99: int = 0

    knowledge_items_total: int = 0
    knowledge_by_product: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}
