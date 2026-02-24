"""Cross-product comparison Q-A generation."""
from __future__ import annotations

import logging
import random
from itertools import combinations
from typing import Dict, List, Set, Tuple

from .config import GenerationConfig
from .manual_loader import PRODUCT_CLUSTERS, PRODUCT_DISPLAY_NAMES
from .models import (
    ItemType,
    Language,
    ProductKnowledge,
    SFTCategory,
    SFTRecord,
)

logger = logging.getLogger(__name__)

# ── Comparison Templates ───────────────────────────────────────────

COMPARISON_TEMPLATES: Dict[str, Dict[Language, List[str]]] = {
    "feature_comparison": {
        Language.JA: [
            "{display_a}と{display_b}の主な機能の違いは何ですか？",
            "{display_a}と{display_b}の{feature}機能を比較してください。",
            "{display_a}にあって{display_b}にない機能は何ですか？",
        ],
        Language.KO: [
            "{display_a}와 {display_b}의 주요 기능 차이는 무엇인가요?",
            "{display_a}와 {display_b}의 {feature} 기능을 비교해주세요.",
            "{display_a}에는 있고 {display_b}에는 없는 기능은?",
        ],
        Language.EN: [
            "What are the main differences between {display_a} and {display_b}?",
            "Compare the {feature} capabilities of {display_a} and {display_b}.",
            "What features does {display_a} have that {display_b} does not?",
        ],
    },
    "use_case": {
        Language.JA: [
            "{display_a}と{display_b}はどのような場面で使い分けますか？",
            "{display_a}を選ぶべき場面と{display_b}を選ぶべき場面を教えてください。",
        ],
        Language.KO: [
            "{display_a}와 {display_b}는 어떤 상황에서 구분하여 사용하나요?",
            "{display_a}를 선택해야 하는 경우와 {display_b}를 선택해야 하는 경우를 알려주세요.",
        ],
        Language.EN: [
            "When should you use {display_a} versus {display_b}?",
            "In what scenarios should you choose {display_a} over {display_b}?",
        ],
    },
    "integration": {
        Language.JA: [
            "{display_a}と{display_b}の連携方法を教えてください。",
            "{display_a}から{display_b}にデータを連携する方法は？",
        ],
        Language.KO: [
            "{display_a}와 {display_b}의 연동 방법을 알려주세요.",
            "{display_a}에서 {display_b}로 데이터를 연동하는 방법은?",
        ],
        Language.EN: [
            "How do you integrate {display_a} with {display_b}?",
            "How do you transfer data from {display_a} to {display_b}?",
        ],
    },
    "migration": {
        Language.JA: [
            "{display_a}から{display_b}への移行手順を教えてください。",
            "{display_a}と{display_b}間の移行で注意すべき点は？",
        ],
        Language.KO: [
            "{display_a}에서 {display_b}로의 마이그레이션 절차를 알려주세요.",
            "{display_a}와 {display_b} 간 마이그레이션에서 주의할 점은?",
        ],
        Language.EN: [
            "What is the migration procedure from {display_a} to {display_b}?",
            "What should you be aware of when migrating between {display_a} and {display_b}?",
        ],
    },
    "config_comparison": {
        Language.JA: [
            "{display_a}と{display_b}の設定方法の違いを教えてください。",
        ],
        Language.KO: [
            "{display_a}와 {display_b}의 설정 방법 차이를 알려주세요.",
        ],
        Language.EN: [
            "What are the configuration differences between {display_a} and {display_b}?",
        ],
    },
    "error_handling": {
        Language.JA: [
            "{display_a}と{display_b}のエラーハンドリングの違いは？",
        ],
        Language.KO: [
            "{display_a}와 {display_b}의 에러 핸들링 차이는?",
        ],
        Language.EN: [
            "How does error handling differ between {display_a} and {display_b}?",
        ],
    },
}


class ComparisonGenerator:
    """Generate cross-product comparison Q-A pairs."""

    def __init__(self, config: GenerationConfig):
        self.config = config

    def generate(
        self,
        knowledge: Dict[str, ProductKnowledge],
    ) -> List[SFTRecord]:
        """Generate comparison Q-A for all meaningful product pairs."""
        products = list(knowledge.keys())
        pairs = self._get_meaningful_pairs(products)
        all_records: List[SFTRecord] = []

        for product_a, product_b, weight in pairs:
            if product_a not in knowledge or product_b not in knowledge:
                continue

            budget = max(
                5,
                int(self.config.comparison_questions_per_pair * weight),
            )
            lang = knowledge[product_a].language

            records = self._generate_pair_qa(
                product_a,
                product_b,
                knowledge[product_a],
                knowledge[product_b],
                budget,
                lang,
            )
            all_records.extend(records)

        logger.info(
            "Comparison generation: %d pairs → %d records",
            len(pairs),
            len(all_records),
        )
        return all_records

    def _get_meaningful_pairs(
        self, products: List[str]
    ) -> List[Tuple[str, str, float]]:
        """Generate product pairs with relevance weight."""
        pairs: List[Tuple[str, str, float]] = []

        for a, b in combinations(products, 2):
            cluster_a = self._find_cluster(a)
            cluster_b = self._find_cluster(b)

            if cluster_a == cluster_b and cluster_a:
                weight = self.config.comparison_cluster_boost
            elif cluster_a and cluster_b:
                weight = 0.5
            else:
                weight = 0.2

            pairs.append((a, b, weight))

        return pairs

    def _find_cluster(self, product: str) -> str:
        """Find which cluster a product belongs to."""
        for cluster_name, members in PRODUCT_CLUSTERS.items():
            if product in members:
                return cluster_name
        return ""

    def _generate_pair_qa(
        self,
        product_a: str,
        product_b: str,
        knowledge_a: ProductKnowledge,
        knowledge_b: ProductKnowledge,
        questions_budget: int,
        lang: Language,
    ) -> List[SFTRecord]:
        """Generate comparison Q-A for a single product pair."""
        records: List[SFTRecord] = []
        display_a = PRODUCT_DISPLAY_NAMES.get(product_a, product_a)
        display_b = PRODUCT_DISPLAY_NAMES.get(product_b, product_b)

        # Find shared knowledge types
        shared_features = self._find_shared_features(knowledge_a, knowledge_b)
        system_prompt = self.config.system_prompt_template

        remaining = questions_budget
        template_types = list(COMPARISON_TEMPLATES.keys())
        random.shuffle(template_types)

        for ttype in template_types:
            if remaining <= 0:
                break

            templates = COMPARISON_TEMPLATES[ttype].get(lang, [])
            if not templates:
                continue

            for template in templates:
                if remaining <= 0:
                    break

                # Pick a shared feature for templates that need it
                feature = random.choice(shared_features) if shared_features else ""

                question = template.format(
                    display_a=display_a,
                    display_b=display_b,
                    feature=feature,
                )

                answer = self._build_comparison_answer(
                    ttype,
                    product_a,
                    product_b,
                    knowledge_a,
                    knowledge_b,
                    feature,
                    lang,
                )

                if len(answer) < self.config.qa_min_answer_length:
                    continue

                records.append(
                    SFTRecord(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": question},
                            {"role": "assistant", "content": answer},
                        ],
                        product=product_a,
                        language=lang,
                        category=SFTCategory.CROSS_PRODUCT,
                        item_type=ItemType.CONCEPT,
                        source_file=f"{product_a}+{product_b}",
                        products_involved=[product_a, product_b],
                    )
                )
                remaining -= 1

        return records

    def _find_shared_features(
        self,
        knowledge_a: ProductKnowledge,
        knowledge_b: ProductKnowledge,
    ) -> List[str]:
        """Find feature/command names shared between two products."""
        names_a: Set[str] = set()
        names_b: Set[str] = set()

        for item in knowledge_a.all_items():
            names_a.add(item.name.lower())
        for item in knowledge_b.all_items():
            names_b.add(item.name.lower())

        shared = names_a & names_b
        if not shared:
            # Use item type categories as features
            types_a = {type(i).__name__ for i in knowledge_a.all_items()}
            types_b = {type(i).__name__ for i in knowledge_b.all_items()}
            shared = types_a & types_b

        return list(shared) if shared else ["general"]

    def _build_comparison_answer(
        self,
        template_type: str,
        product_a: str,
        product_b: str,
        knowledge_a: ProductKnowledge,
        knowledge_b: ProductKnowledge,
        shared_feature: str,
        lang: Language,
    ) -> str:
        """Build a balanced comparison answer."""
        display_a = knowledge_a.display_name
        display_b = knowledge_b.display_name

        parts: List[str] = []

        if template_type == "feature_comparison":
            parts.append(f"**{display_a}**:")
            desc_a = self._summarize_product(knowledge_a, shared_feature)
            parts.append(desc_a)
            parts.append(f"\n**{display_b}**:")
            desc_b = self._summarize_product(knowledge_b, shared_feature)
            parts.append(desc_b)

            diffs = self._extract_differences(knowledge_a, knowledge_b)
            if diffs:
                diff_label = {"ja": "主な違い", "ko": "주요 차이점", "en": "Key Differences"}
                parts.append(f"\n**{diff_label.get(lang.value, 'Key Differences')}**:")
                for d in diffs[:5]:
                    parts.append(f"- {d}")

        elif template_type == "use_case":
            label_a = {"ja": "を選ぶべき場面", "ko": "를 선택해야 하는 경우", "en": " use cases"}
            label_b = label_a
            parts.append(f"**{display_a}{label_a.get(lang.value, '')}**:")
            parts.append(self._describe_use_cases(knowledge_a, lang))
            parts.append(f"\n**{display_b}{label_b.get(lang.value, '')}**:")
            parts.append(self._describe_use_cases(knowledge_b, lang))

        elif template_type in ("integration", "migration"):
            parts.append(
                self._describe_relationship(
                    knowledge_a, knowledge_b, template_type, lang
                )
            )

        elif template_type == "config_comparison":
            configs_a = [c.name for c in knowledge_a.configs[:5]]
            configs_b = [c.name for c in knowledge_b.configs[:5]]
            parts.append(f"**{display_a}** configs: {', '.join(configs_a) if configs_a else 'N/A'}")
            parts.append(f"**{display_b}** configs: {', '.join(configs_b) if configs_b else 'N/A'}")

        elif template_type == "error_handling":
            err_a = len(knowledge_a.errors)
            err_b = len(knowledge_b.errors)
            parts.append(
                f"**{display_a}**: {err_a} error codes defined"
            )
            if knowledge_a.errors:
                sample = knowledge_a.errors[0]
                parts.append(f"  Example: {sample.name} - {sample.description[:100]}")
            parts.append(
                f"\n**{display_b}**: {err_b} error codes defined"
            )
            if knowledge_b.errors:
                sample = knowledge_b.errors[0]
                parts.append(f"  Example: {sample.name} - {sample.description[:100]}")

        answer = "\n".join(parts)
        if len(answer) > self.config.qa_max_answer_length:
            answer = answer[: self.config.qa_max_answer_length - 3] + "..."

        return answer

    # ── Answer helpers ────────────────────────────────────────────

    @staticmethod
    def _summarize_product(pk: ProductKnowledge, feature: str) -> str:
        """Short summary of product's capabilities related to feature."""
        parts: List[str] = []
        if pk.commands:
            parts.append(f"  Commands: {len(pk.commands)} ({', '.join(c.name for c in pk.commands[:3])}...)")
        if pk.configs:
            parts.append(f"  Config parameters: {len(pk.configs)}")
        if pk.errors:
            parts.append(f"  Error codes: {len(pk.errors)}")
        if pk.features:
            parts.append(f"  Features: {', '.join(f.name for f in pk.features[:3])}")
        return "\n".join(parts) if parts else f"  {pk.display_name} product documentation"

    @staticmethod
    def _extract_differences(
        ka: ProductKnowledge, kb: ProductKnowledge
    ) -> List[str]:
        """Extract notable differences between two products."""
        diffs: List[str] = []
        cmds_a = {c.name for c in ka.commands}
        cmds_b = {c.name for c in kb.commands}
        only_a = cmds_a - cmds_b
        only_b = cmds_b - cmds_a
        if only_a:
            diffs.append(
                f"{ka.display_name} only: {', '.join(list(only_a)[:3])}"
            )
        if only_b:
            diffs.append(
                f"{kb.display_name} only: {', '.join(list(only_b)[:3])}"
            )
        if len(ka.errors) != len(kb.errors):
            diffs.append(
                f"Error codes: {ka.display_name}={len(ka.errors)}, {kb.display_name}={len(kb.errors)}"
            )
        return diffs

    @staticmethod
    def _describe_use_cases(pk: ProductKnowledge, lang: Language) -> str:
        """Describe typical use cases from features."""
        if pk.features:
            return "\n".join(
                f"  - {f.name}: {f.description[:100]}" for f in pk.features[:3]
            )
        if pk.commands:
            return f"  Management via {len(pk.commands)} commands"
        return f"  {pk.display_name} product"

    @staticmethod
    def _describe_relationship(
        ka: ProductKnowledge,
        kb: ProductKnowledge,
        rel_type: str,
        lang: Language,
    ) -> str:
        """Describe integration/migration relationship."""
        if rel_type == "integration":
            return (
                f"{ka.display_name} and {kb.display_name} can be integrated "
                f"within the TmaxSoft product ecosystem. "
                f"{ka.display_name} provides {ka.total_items} documented items, "
                f"while {kb.display_name} provides {kb.total_items} documented items."
            )
        # migration
        migrations_a = [m for m in ka.migrations if kb.product in m.target_platform.lower()]
        if migrations_a:
            m = migrations_a[0]
            return f"Migration from {ka.display_name} to {kb.display_name}:\n{m.description[:300]}"
        return (
            f"Migration between {ka.display_name} and {kb.display_name} "
            f"should be planned based on official documentation."
        )
