"""DPO preference pair generation."""
from __future__ import annotations

import logging
import random
import re
from typing import Dict, List

from .config import GenerationConfig
from .manual_loader import PRODUCT_DISPLAY_NAMES
from .models import (
    DPORecord,
    DPOStrategy,
    Language,
    ProductKnowledge,
    SFTRecord,
)

logger = logging.getLogger(__name__)

# ── Fact Mutation Patterns ────────────────────────────────────────

_NUMBER_RE = re.compile(r"(\d{4,5})")
_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")
_PORT_RE = re.compile(
    r"(?:port|ポート|포트)\s*[:：]?\s*(\d{4,5})", re.IGNORECASE
)

# ── Over-claiming Templates ──────────────────────────────────────

FAKE_FEATURES: Dict[Language, List[str]] = {
    Language.JA: [
        "さらに、{product}はリアルタイムAI分析機能を内蔵しています。",
        "また、{product}はクラウドネイティブなマイクロサービスアーキテクチャに完全対応しています。",
        "{product}にはGraphQLエンドポイントが標準で搭載されています。",
        "加えて、{product}はKubernetesオートスケーリングをネイティブサポートしています。",
        "{product}はBlockchainベースの監査ログ機能を提供しています。",
        "{product}にはAIを活用した自動障害予測機能が含まれています。",
    ],
    Language.KO: [
        "또한 {product}는 실시간 AI 분석 기능을 내장하고 있습니다.",
        "{product}는 클라우드 네이티브 마이크로서비스 아키텍처를 완벽히 지원합니다.",
        "{product}에는 GraphQL 엔드포인트가 기본 탑재되어 있습니다.",
        "{product}는 Kubernetes 오토스케일링을 네이티브 지원합니다.",
    ],
    Language.EN: [
        "Additionally, {product} includes built-in real-time AI analytics.",
        "{product} fully supports cloud-native microservice architectures.",
        "{product} comes with built-in GraphQL endpoints.",
        "{product} natively supports Kubernetes auto-scaling.",
        "{product} provides blockchain-based audit logging capabilities.",
    ],
}

# ── Speculative Templates ────────────────────────────────────────

SPECULATIVE_ADDITIONS: Dict[Language, List[str]] = {
    Language.JA: [
        "これはおそらく、内部的に{speculation}を使用しているためです。",
        "一般的に、{product}は{speculation}と組み合わせて使用されることが多いです。",
        "将来のバージョンでは、{speculation}機能が追加される予定です。",
        "業界の専門家によると、{product}は{speculation}の分野でリーダー的存在です。",
    ],
    Language.KO: [
        "이것은 아마도 내부적으로 {speculation}을 사용하기 때문입니다.",
        "일반적으로 {product}는 {speculation}와 함께 사용되는 경우가 많습니다.",
        "향후 버전에서는 {speculation} 기능이 추가될 예정입니다.",
    ],
    Language.EN: [
        "This is likely because it internally uses {speculation}.",
        "Generally, {product} is often combined with {speculation}.",
        "Future versions are expected to include {speculation} capabilities.",
        "Industry experts consider {product} a leader in {speculation}.",
    ],
}

_SPECULATION_TOPICS = [
    "machine learning",
    "distributed consensus",
    "quantum computing",
    "neural networks",
    "blockchain technology",
    "edge computing",
    "serverless architecture",
    "zero-trust security",
]


class DPOGenerator:
    """Generate DPO preference pairs from knowledge + SFT records."""

    def __init__(self, config: GenerationConfig):
        self.config = config

    def generate(
        self,
        knowledge: Dict[str, ProductKnowledge],
        sft_records: List[SFTRecord],
    ) -> List[DPORecord]:
        """Generate DPO preference pairs."""
        target = self.config.target_dpo_size
        all_records: List[DPORecord] = []

        # Compute strategy budgets
        budget_cross = int(target * self.config.dpo_cross_product_ratio)
        budget_fact = int(target * self.config.dpo_fact_mutation_ratio)
        budget_over = int(target * self.config.dpo_over_claiming_ratio)
        budget_spec = target - budget_cross - budget_fact - budget_over

        logger.info(
            "DPO budgets: cross=%d, fact=%d, over=%d, spec=%d",
            budget_cross, budget_fact, budget_over, budget_spec,
        )

        all_records.extend(self._generate_cross_product(sft_records, budget_cross))
        all_records.extend(self._generate_fact_mutation(sft_records, budget_fact))
        all_records.extend(self._generate_over_claiming(sft_records, budget_over))
        all_records.extend(self._generate_speculative(sft_records, budget_spec))

        random.shuffle(all_records)
        logger.info("DPO generation total: %d records", len(all_records))
        return all_records

    # ── Strategy: Cross-Product ───────────────────────────────────

    def _generate_cross_product(
        self, sft_records: List[SFTRecord], budget: int
    ) -> List[DPORecord]:
        """Use answer from product B as rejected for product A's question."""
        records: List[DPORecord] = []

        # Group SFT by (language, item_type)
        groups: Dict[tuple, List[SFTRecord]] = {}
        for r in sft_records:
            key = (r.language.value, r.item_type.value)
            groups.setdefault(key, []).append(r)

        for (lang, itype), group in groups.items():
            if len(records) >= budget:
                break
            # Need at least 2 different products
            by_product: Dict[str, List[SFTRecord]] = {}
            for r in group:
                by_product.setdefault(r.product, []).append(r)

            products = list(by_product.keys())
            if len(products) < 2:
                continue

            for i, prod_a in enumerate(products):
                if len(records) >= budget:
                    break
                for prod_b in products[i + 1 :]:
                    if len(records) >= budget:
                        break

                    rec_a = random.choice(by_product[prod_a])
                    rec_b = random.choice(by_product[prod_b])

                    records.append(
                        DPORecord(
                            prompt=self._build_prompt(rec_a),
                            chosen=rec_a.assistant_text,
                            rejected=rec_b.assistant_text,
                            product=rec_a.product,
                            language=rec_a.language,
                            strategy=DPOStrategy.CROSS_PRODUCT,
                            source_file=rec_a.source_file,
                            products_involved=[rec_a.product, rec_b.product],
                        )
                    )

        logger.info("  Cross-product: %d records", len(records))
        return records[:budget]

    # ── Strategy: Fact Mutation ────────────────────────────────────

    def _generate_fact_mutation(
        self, sft_records: List[SFTRecord], budget: int
    ) -> List[DPORecord]:
        """Mutate facts in correct answers to create rejected."""
        records: List[DPORecord] = []
        candidates = [r for r in sft_records if len(r.assistant_text) > 50]
        random.shuffle(candidates)

        for rec in candidates:
            if len(records) >= budget:
                break

            mutated = self._mutate_answer(rec.assistant_text, rec.product)
            if mutated == rec.assistant_text:
                continue

            records.append(
                DPORecord(
                    prompt=self._build_prompt(rec),
                    chosen=rec.assistant_text,
                    rejected=mutated,
                    product=rec.product,
                    language=rec.language,
                    strategy=DPOStrategy.FACT_MUTATION,
                    source_file=rec.source_file,
                )
            )

        logger.info("  Fact mutation: %d records", len(records))
        return records[:budget]

    # ── Strategy: Over-claiming ───────────────────────────────────

    def _generate_over_claiming(
        self, sft_records: List[SFTRecord], budget: int
    ) -> List[DPORecord]:
        """Append fake feature claims to correct answers."""
        records: List[DPORecord] = []
        candidates = [r for r in sft_records if len(r.assistant_text) > 50]
        random.shuffle(candidates)

        for rec in candidates:
            if len(records) >= budget:
                break

            display = PRODUCT_DISPLAY_NAMES.get(rec.product, rec.product)
            fake_templates = FAKE_FEATURES.get(rec.language, FAKE_FEATURES[Language.EN])
            n_fake = random.randint(1, 2)
            fake_sentences = [
                t.format(product=display)
                for t in random.sample(fake_templates, min(n_fake, len(fake_templates)))
            ]

            rejected = rec.assistant_text + "\n\n" + " ".join(fake_sentences)

            records.append(
                DPORecord(
                    prompt=self._build_prompt(rec),
                    chosen=rec.assistant_text,
                    rejected=rejected,
                    product=rec.product,
                    language=rec.language,
                    strategy=DPOStrategy.OVER_CLAIMING,
                    source_file=rec.source_file,
                )
            )

        logger.info("  Over-claiming: %d records", len(records))
        return records[:budget]

    # ── Strategy: Speculative ─────────────────────────────────────

    def _generate_speculative(
        self, sft_records: List[SFTRecord], budget: int
    ) -> List[DPORecord]:
        """Add speculative reasoning not grounded in manuals."""
        records: List[DPORecord] = []
        candidates = [r for r in sft_records if len(r.assistant_text) > 50]
        random.shuffle(candidates)

        for rec in candidates:
            if len(records) >= budget:
                break

            display = PRODUCT_DISPLAY_NAMES.get(rec.product, rec.product)
            spec_templates = SPECULATIVE_ADDITIONS.get(
                rec.language, SPECULATIVE_ADDITIONS[Language.EN]
            )
            speculation = random.choice(_SPECULATION_TOPICS)
            spec_sentence = random.choice(spec_templates).format(
                product=display, speculation=speculation
            )

            # Insert speculation into the middle of the answer
            lines = rec.assistant_text.split("\n")
            insert_pos = max(1, len(lines) // 2)
            lines.insert(insert_pos, spec_sentence)
            rejected = "\n".join(lines)

            records.append(
                DPORecord(
                    prompt=self._build_prompt(rec),
                    chosen=rec.assistant_text,
                    rejected=rejected,
                    product=rec.product,
                    language=rec.language,
                    strategy=DPOStrategy.SPECULATIVE,
                    source_file=rec.source_file,
                )
            )

        logger.info("  Speculative: %d records", len(records))
        return records[:budget]

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(record: SFTRecord) -> str:
        """Build DPO prompt from SFT record (user question only).

        The system prompt is excluded because DPO training frameworks
        inject it separately.  Including it in the prompt field would
        cause the model to see it twice during training.
        """
        for msg in record.messages:
            if msg["role"] == "user":
                return msg["content"]
        return ""

    @staticmethod
    def _mutate_answer(text: str, product: str) -> str:
        """Apply fact mutations to an answer.

        Multiple mutation strategies ensure meaningful length differences
        between chosen and rejected, preventing length-shortcut learning.
        """
        mutated = text
        mutations_applied = 0

        # Strategy 1: Mutate error codes
        m = _NUMBER_RE.search(mutated)
        if m:
            original = int(m.group(1))
            delta = random.choice([-1, 1]) * random.randint(100, 999)
            new_val = str(abs(original + delta))
            mutated = mutated[: m.start(1)] + new_val + mutated[m.end(1) :]
            mutations_applied += 1

        # Strategy 2: Mutate version numbers
        m = _VERSION_RE.search(mutated)
        if m:
            parts = m.group(1).split(".")
            idx = random.randrange(len(parts))
            parts[idx] = str(int(parts[idx]) + random.choice([-1, 1]))
            if int(parts[idx]) < 0:
                parts[idx] = "0"
            new_ver = ".".join(parts)
            mutated = mutated[: m.start(1)] + new_ver + mutated[m.end(1) :]
            mutations_applied += 1

        # Strategy 3: Swap product names
        all_products = list(PRODUCT_DISPLAY_NAMES.values())
        display = PRODUCT_DISPLAY_NAMES.get(product, product)
        if display in mutated:
            other = random.choice([p for p in all_products if p != display] or all_products)
            mutated = mutated.replace(display, other, 1)
            mutations_applied += 1

        # Strategy 4: Sentence reordering (swap two lines to break logical flow)
        lines = mutated.split("\n")
        if len(lines) >= 4:
            i, j = random.sample(range(1, len(lines)), 2)
            lines[i], lines[j] = lines[j], lines[i]
            mutated = "\n".join(lines)
            mutations_applied += 1

        # Strategy 5: Remove a key sentence (creates length difference)
        if mutations_applied < 2:
            lines = mutated.split("\n")
            content_lines = [
                k for k, line in enumerate(lines)
                if line.strip() and not line.startswith("#") and len(line.strip()) > 10
            ]
            if len(content_lines) >= 3:
                remove_idx = random.choice(content_lines[1:])
                lines.pop(remove_idx)
                mutated = "\n".join(lines)
                mutations_applied += 1

        if mutated == text:
            return text

        return mutated
