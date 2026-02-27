"""Single-product QA generation from ProductKnowledge."""
from __future__ import annotations

import logging
import random
from typing import Dict, List

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
    MigrationItem,
    ProductKnowledge,
    SFTCategory,
    SFTRecord,
)

logger = logging.getLogger(__name__)

# ── Question Templates ─────────────────────────────────────────────
# {name}, {product}, {description}, {syntax}, {cause}, {resolution}, etc.

QA_TEMPLATES: Dict[ItemType, Dict[Language, List[str]]] = {
    ItemType.COMMAND: {
        Language.JA: [
            "{name}コマンドについて説明してください。",
            "{name}コマンドの構文と使用方法を教えてください。",
            "{name}コマンドのパラメータを説明してください。",
            "{name}コマンドの使用例を教えてください。",
            "{product}で{name}コマンドをどのように使用しますか？",
        ],
        Language.KO: [
            "{name} 명령어에 대해 설명해주세요.",
            "{name} 명령어의 구문과 사용법을 알려주세요.",
            "{name} 명령어의 파라미터를 설명해주세요.",
            "{name} 명령어의 사용 예시를 알려주세요.",
            "{product}에서 {name} 명령어를 어떻게 사용하나요?",
        ],
        Language.EN: [
            "Explain the {name} command.",
            "What is the syntax and usage of the {name} command?",
            "Describe the parameters of the {name} command.",
            "Provide usage examples for the {name} command.",
            "How do you use the {name} command in {product}?",
        ],
    },
    ItemType.ERROR: {
        Language.JA: [
            "エラー{name}の原因と解決方法を教えてください。",
            "エラーコード{name}が発生した場合の対処方法は？",
            "{product}でエラー{name}が発生しました。原因は何ですか？",
        ],
        Language.KO: [
            "에러 {name}의 원인과 해결 방법을 알려주세요.",
            "에러코드 {name}이 발생했을 때 대처 방법은?",
            "{product}에서 에러 {name}이 발생했습니다. 원인이 뭔가요?",
        ],
        Language.EN: [
            "What causes error {name} and how do you resolve it?",
            "How do you handle error code {name}?",
            "Error {name} occurred in {product}. What is the cause?",
        ],
    },
    ItemType.CONFIG: {
        Language.JA: [
            "{name}の設定方法を説明してください。",
            "{name}パラメータのデフォルト値と有効な値は？",
            "{product}で{name}をどのように設定しますか？",
        ],
        Language.KO: [
            "{name} 설정 방법을 설명해주세요.",
            "{name} 파라미터의 기본값과 유효값은?",
            "{product}에서 {name}을 어떻게 설정하나요?",
        ],
        Language.EN: [
            "How do you configure {name}?",
            "What are the default and valid values for {name}?",
            "How do you set up {name} in {product}?",
        ],
    },
    ItemType.API: {
        Language.JA: [
            "{name} APIの使用方法を教えてください。",
            "{name}関数のパラメータと戻り値を説明してください。",
        ],
        Language.KO: [
            "{name} API 사용법을 알려주세요.",
            "{name} 함수의 파라미터와 반환값을 설명해주세요.",
        ],
        Language.EN: [
            "How do you use the {name} API?",
            "Describe the parameters and return value of {name}.",
        ],
    },
    ItemType.CONCEPT: {
        Language.JA: [
            "{name}とは何ですか？",
            "{name}の概要を説明してください。",
            "{product}における{name}の役割は何ですか？",
            "{name}はどのような場面で使用されますか？",
        ],
        Language.KO: [
            "{name}이란 무엇인가요?",
            "{name}의 개요를 설명해주세요.",
            "{product}에서 {name}의 역할은 무엇인가요?",
            "{name}은 어떤 상황에서 사용되나요?",
        ],
        Language.EN: [
            "What is {name}?",
            "Provide an overview of {name}.",
            "What role does {name} play in {product}?",
            "In what scenarios is {name} used?",
        ],
    },
    ItemType.PROCEDURE: {
        Language.JA: [
            "{name}の手順を教えてください。",
            "{product}で{name}を実行する方法は？",
        ],
        Language.KO: [
            "{name} 절차를 알려주세요.",
            "{product}에서 {name}을 실행하는 방법은?",
        ],
        Language.EN: [
            "What is the procedure for {name}?",
            "How do you perform {name} in {product}?",
        ],
    },
    ItemType.LIMITATION: {
        Language.JA: [
            "{name}の制限事項を教えてください。",
            "{product}の{name}に関する注意点は？",
        ],
        Language.KO: [
            "{name}의 제한 사항을 알려주세요.",
            "{product}의 {name}에 관한 주의사항은?",
        ],
        Language.EN: [
            "What are the limitations of {name}?",
            "What should you be aware of regarding {name} in {product}?",
        ],
    },
    ItemType.MIGRATION: {
        Language.JA: [
            "{name}の移行手順を教えてください。",
            "{product}への移行で{name}に関する注意点は？",
        ],
        Language.KO: [
            "{name} 마이그레이션 절차를 알려주세요.",
            "{product}로의 마이그레이션에서 {name} 관련 주의사항은?",
        ],
        Language.EN: [
            "What is the migration procedure for {name}?",
            "What should you consider about {name} when migrating to {product}?",
        ],
    },
}

# ── Answer section labels ──────────────────────────────────────────

_LABELS: Dict[str, Dict[Language, str]] = {
    "syntax": {Language.JA: "構文", Language.KO: "구문", Language.EN: "Syntax"},
    "parameters": {
        Language.JA: "パラメータ",
        Language.KO: "파라미터",
        Language.EN: "Parameters",
    },
    "examples": {Language.JA: "例", Language.KO: "예시", Language.EN: "Examples"},
    "cause": {Language.JA: "原因", Language.KO: "원인", Language.EN: "Cause"},
    "resolution": {
        Language.JA: "対処方法",
        Language.KO: "해결 방법",
        Language.EN: "Resolution",
    },
    "default": {
        Language.JA: "デフォルト値",
        Language.KO: "기본값",
        Language.EN: "Default Value",
    },
    "return_type": {
        Language.JA: "戻り値",
        Language.KO: "반환값",
        Language.EN: "Return Type",
    },
    "workaround": {
        Language.JA: "回避策",
        Language.KO: "대안",
        Language.EN: "Workaround",
    },
    "steps": {Language.JA: "手順", Language.KO: "절차", Language.EN: "Steps"},
    "source": {
        Language.JA: "移行元",
        Language.KO: "마이그레이션 소스",
        Language.EN: "Source Platform",
    },
    "target": {
        Language.JA: "移行先",
        Language.KO: "마이그레이션 대상",
        Language.EN: "Target Platform",
    },
}


class QAGenerator:
    """Generate single-product Q-A pairs."""

    def __init__(self, config: GenerationConfig):
        self.config = config

    def generate(
        self,
        knowledge: Dict[str, ProductKnowledge],
    ) -> List[SFTRecord]:
        """Generate SFT records for all products."""
        all_records: List[SFTRecord] = []

        for product, pk in knowledge.items():
            records = self._generate_for_product(pk)
            all_records.extend(records)
            logger.info("  QA %s: %d records", product, len(records))

        logger.info("QA generation total: %d records", len(all_records))
        return all_records

    def _generate_for_product(self, pk: ProductKnowledge) -> List[SFTRecord]:
        """Generate all Q-A pairs for one product."""
        records: List[SFTRecord] = []
        display = pk.display_name
        lang = pk.language

        for item in pk.commands:
            records.extend(
                self._generate_typed_qa(item, ItemType.COMMAND, pk.product, display, lang)
            )
        for item in pk.errors:
            records.extend(
                self._generate_typed_qa(item, ItemType.ERROR, pk.product, display, lang)
            )
        for item in pk.configs:
            records.extend(
                self._generate_typed_qa(item, ItemType.CONFIG, pk.product, display, lang)
            )
        for item in pk.apis:
            records.extend(
                self._generate_typed_qa(item, ItemType.API, pk.product, display, lang)
            )
        for item in pk.features:
            records.extend(
                self._generate_typed_qa(item, ItemType.CONCEPT, pk.product, display, lang)
            )
        for item in pk.limitations:
            records.extend(
                self._generate_typed_qa(
                    item, ItemType.LIMITATION, pk.product, display, lang
                )
            )
        for item in pk.migrations:
            records.extend(
                self._generate_typed_qa(
                    item, ItemType.MIGRATION, pk.product, display, lang
                )
            )

        return records

    def _generate_typed_qa(
        self,
        item: KnowledgeItem,
        item_type: ItemType,
        product: str,
        display_name: str,
        lang: Language,
    ) -> List[SFTRecord]:
        """Generate Q-A variants for a single knowledge item."""
        templates = QA_TEMPLATES.get(item_type, {}).get(lang, [])
        if not templates:
            return []

        # Limit variants per item
        n_variants = min(self.config.qa_variants_per_item, len(templates))
        selected = random.sample(templates, n_variants)

        answer = self._build_answer(item, item_type, lang)
        if len(answer) < self.config.qa_min_answer_length:
            return []

        system_prompt = self.config.system_prompt_template
        records: List[SFTRecord] = []

        for template in selected:
            question = template.format(
                name=item.name, product=display_name, description=item.description
            )
            records.append(
                _make_sft_record(
                    system_prompt=system_prompt,
                    question=question,
                    answer=answer,
                    product=product,
                    language=lang,
                    item_type=item_type,
                    source_file=item.source_file,
                    source_page=item.source_page,
                )
            )

        return records

    def _build_answer(
        self, item: KnowledgeItem, item_type: ItemType, lang: Language
    ) -> str:
        """Build a structured answer from knowledge item fields."""
        parts: List[str] = []

        # Description
        if item.description:
            parts.append(item.description)

        if item_type == ItemType.COMMAND and isinstance(item, CommandItem):
            if item.syntax:
                label = _LABELS["syntax"].get(lang, "Syntax")
                parts.append(f"\n**{label}**: `{item.syntax}`")
            if item.parameters:
                label = _LABELS["parameters"].get(lang, "Parameters")
                parts.append(f"\n**{label}**:")
                for p in item.parameters[:10]:
                    parts.append(f"- {p['name']}: {p.get('description', '')}")
            if item.examples:
                label = _LABELS["examples"].get(lang, "Examples")
                parts.append(f"\n**{label}**:")
                for ex in item.examples[:3]:
                    parts.append(f"```\n{ex}\n```")

        elif item_type == ItemType.ERROR and isinstance(item, ErrorItem):
            if item.cause:
                label = _LABELS["cause"].get(lang, "Cause")
                parts.append(f"\n**{label}**: {item.cause}")
            if item.resolution:
                label = _LABELS["resolution"].get(lang, "Resolution")
                parts.append(f"\n**{label}**: {item.resolution}")
            if item.severity:
                parts.append(f"\nSeverity: {item.severity}")

        elif item_type == ItemType.CONFIG and isinstance(item, ConfigItem):
            if item.default_value:
                label = _LABELS["default"].get(lang, "Default")
                parts.append(f"\n**{label}**: {item.default_value}")
            if item.valid_values:
                parts.append(f"\nValid values: {', '.join(item.valid_values)}")
            if item.config_file:
                parts.append(f"\nConfig file: `{item.config_file}`")

        elif item_type == ItemType.API and isinstance(item, APIItem):
            if item.signature:
                label = _LABELS["syntax"].get(lang, "Syntax")
                parts.append(f"\n**{label}**: `{item.signature}`")
            if item.parameters:
                label = _LABELS["parameters"].get(lang, "Parameters")
                parts.append(f"\n**{label}**:")
                for p in item.parameters[:10]:
                    parts.append(f"- {p['name']}: {p.get('description', '')}")
            if item.return_type:
                label = _LABELS["return_type"].get(lang, "Return Type")
                parts.append(f"\n**{label}**: {item.return_type}")
            if item.examples:
                label = _LABELS["examples"].get(lang, "Examples")
                parts.append(f"\n**{label}**:")
                for ex in item.examples[:3]:
                    parts.append(f"```\n{ex}\n```")

        elif item_type == ItemType.LIMITATION and isinstance(item, LimitationItem):
            if item.workaround:
                label = _LABELS["workaround"].get(lang, "Workaround")
                parts.append(f"\n**{label}**: {item.workaround}")

        elif item_type == ItemType.MIGRATION and isinstance(item, MigrationItem):
            if item.source_platform:
                label = _LABELS["source"].get(lang, "Source")
                parts.append(f"\n**{label}**: {item.source_platform}")
            if item.target_platform:
                label = _LABELS["target"].get(lang, "Target")
                parts.append(f"\n**{label}**: {item.target_platform}")
            if item.steps:
                label = _LABELS["steps"].get(lang, "Steps")
                parts.append(f"\n**{label}**:")
                for i, step in enumerate(item.steps[:10], 1):
                    parts.append(f"{i}. {step}")

        answer = "\n".join(parts)

        # Enforce length limits
        if len(answer) > self.config.qa_max_answer_length:
            answer = answer[: self.config.qa_max_answer_length - 3] + "..."

        return answer


def _make_sft_record(
    system_prompt: str,
    question: str,
    answer: str,
    product: str,
    language: Language,
    item_type: ItemType,
    source_file: str,
    source_page: int = 0,
    category: SFTCategory = SFTCategory.SINGLE_PRODUCT,
    products_involved: List[str] | None = None,
) -> SFTRecord:
    """Create an SFTRecord with messages format."""
    return SFTRecord(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
        product=product,
        language=language,
        category=category,
        item_type=item_type,
        source_file=source_file,
        source_page=source_page,
        products_involved=products_involved or [],
    )
