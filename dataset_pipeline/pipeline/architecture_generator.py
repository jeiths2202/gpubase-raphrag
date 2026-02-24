"""Enterprise architecture Q-A generation."""
from __future__ import annotations

import logging
import random
from typing import Dict, List

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

# ── Architecture Templates ─────────────────────────────────────────

ARCHITECTURE_TEMPLATES: Dict[str, Dict[Language, List[str]]] = {
    "ecosystem_overview": {
        Language.JA: [
            "TmaxSoft製品群の全体アーキテクチャを説明してください。",
            "OpenFrameエコシステムを構成するコンポーネントは何ですか？",
            "TmaxSoftの{cluster}関連製品を一覧で教えてください。",
            "OpenFrame製品ファミリーの概要を教えてください。",
        ],
        Language.KO: [
            "TmaxSoft 제품군의 전체 아키텍처를 설명해주세요.",
            "OpenFrame 에코시스템을 구성하는 컴포넌트는 무엇인가요?",
            "TmaxSoft의 {cluster} 관련 제품 목록을 알려주세요.",
            "OpenFrame 제품 패밀리의 개요를 알려주세요.",
        ],
        Language.EN: [
            "Describe the overall architecture of the TmaxSoft product suite.",
            "What components make up the OpenFrame ecosystem?",
            "List the TmaxSoft products related to {cluster}.",
            "Provide an overview of the OpenFrame product family.",
        ],
    },
    "shared_components": {
        Language.JA: [
            "{product_a}と{product_b}が共有するコンポーネントは？",
            "OpenFrameの共通設定ファイル(oframe.conf)の役割は？",
            "TmaxSoft製品間で共有されるライブラリやツールは？",
        ],
        Language.KO: [
            "{product_a}와 {product_b}가 공유하는 컴포넌트는?",
            "OpenFrame의 공통 설정 파일(oframe.conf)의 역할은?",
            "TmaxSoft 제품 간 공유되는 라이브러리와 도구는?",
        ],
        Language.EN: [
            "What components do {product_a} and {product_b} share?",
            "What is the role of the OpenFrame common configuration file (oframe.conf)?",
            "What libraries and tools are shared between TmaxSoft products?",
        ],
    },
    "security_model": {
        Language.JA: [
            "OpenFrame TACFのセキュリティモデルを説明してください。",
            "TmaxSoft製品群のユーザー認証方式を比較してください。",
            "{product}のアクセス制御方式について教えてください。",
        ],
        Language.KO: [
            "OpenFrame TACF의 보안 모델을 설명해주세요.",
            "TmaxSoft 제품군의 사용자 인증 방식을 비교해주세요.",
            "{product}의 접근 제어 방식을 알려주세요.",
        ],
        Language.EN: [
            "Describe the security model of OpenFrame TACF.",
            "Compare user authentication methods across TmaxSoft products.",
            "How does access control work in {product}?",
        ],
    },
    "integration_strategy": {
        Language.JA: [
            "JEUSとTibero 7の統合アーキテクチャを説明してください。",
            "OpenFrameとWebToBの連携構成を教えてください。",
            "{product_a}から{product_b}へのデータフローは？",
            "TmaxSoft製品間の連携アーキテクチャを説明してください。",
        ],
        Language.KO: [
            "JEUS와 Tibero 7의 통합 아키텍처를 설명해주세요.",
            "OpenFrame과 WebtoB의 연동 구성을 알려주세요.",
            "{product_a}에서 {product_b}로의 데이터 플로우는?",
            "TmaxSoft 제품 간의 연동 아키텍처를 설명해주세요.",
        ],
        Language.EN: [
            "Describe the integration architecture of JEUS and Tibero 7.",
            "How is OpenFrame integrated with WebtoB?",
            "What is the data flow from {product_a} to {product_b}?",
            "Describe the inter-product integration architecture of TmaxSoft.",
        ],
    },
    "deployment_architecture": {
        Language.JA: [
            "TmaxSoft製品のHA(高可用性)構成のベストプラクティスは？",
            "OpenFrameの本番環境デプロイ構成を教えてください。",
            "TmaxSoft製品群のクラスタ構成方法は？",
        ],
        Language.KO: [
            "TmaxSoft 제품의 HA(고가용성) 구성 모범 사례는?",
            "OpenFrame의 프로덕션 배포 구성을 알려주세요.",
            "TmaxSoft 제품군의 클러스터 구성 방법은?",
        ],
        Language.EN: [
            "What are the best practices for HA deployment of TmaxSoft products?",
            "Describe the production deployment architecture for OpenFrame.",
            "How do you configure clustering for TmaxSoft products?",
        ],
    },
    "performance_tuning": {
        Language.JA: [
            "OpenFrameバッチ処理のパフォーマンスチューニング方法は？",
            "TmaxSoft製品群全体のパフォーマンス最適化戦略は？",
            "{product}のパフォーマンスを改善する方法を教えてください。",
        ],
        Language.KO: [
            "OpenFrame 배치 처리의 성능 튜닝 방법은?",
            "TmaxSoft 제품군 전체의 성능 최적화 전략은?",
            "{product}의 성능을 개선하는 방법을 알려주세요.",
        ],
        Language.EN: [
            "How do you tune performance for OpenFrame batch processing?",
            "What is the overall performance optimization strategy for TmaxSoft products?",
            "How do you improve performance in {product}?",
        ],
    },
    "migration_strategy": {
        Language.JA: [
            "メインフレームからOpenFrameへの移行戦略を説明してください。",
            "IBM MVSからOpenFrameへの移行手順の概要は？",
            "Fujitsu XSPからOpenFrameへの移行で注意すべき点は？",
            "レガシーシステムからTmaxSoft製品群への移行ロードマップは？",
        ],
        Language.KO: [
            "메인프레임에서 OpenFrame으로의 마이그레이션 전략을 설명해주세요.",
            "IBM MVS에서 OpenFrame으로의 마이그레이션 절차 개요는?",
            "Fujitsu XSP에서 OpenFrame으로의 마이그레이션에서 주의할 점은?",
            "레거시 시스템에서 TmaxSoft 제품군으로의 마이그레이션 로드맵은?",
        ],
        Language.EN: [
            "Describe the migration strategy from mainframe to OpenFrame.",
            "What is the migration procedure from IBM MVS to OpenFrame?",
            "What should you consider when migrating from Fujitsu XSP to OpenFrame?",
            "What is the migration roadmap from legacy systems to TmaxSoft products?",
        ],
    },
}


class ArchitectureGenerator:
    """Generate enterprise architecture Q-A pairs."""

    def __init__(self, config: GenerationConfig):
        self.config = config

    def generate(
        self,
        knowledge: Dict[str, ProductKnowledge],
    ) -> List[SFTRecord]:
        """Generate architecture-level Q-A."""
        all_records: List[SFTRecord] = []
        categories = self.config.architecture_categories
        langs = [Language(l) for l in self.config.all_languages]

        for lang in langs:
            budget_per_category = max(
                500, 5000 // max(len(categories), 1)
            )
            for category in categories:
                if category not in ARCHITECTURE_TEMPLATES:
                    continue
                records = self._generate_for_category(
                    category, knowledge, lang, budget_per_category
                )
                all_records.extend(records)

        logger.info("Architecture generation: %d records", len(all_records))
        return all_records

    def _generate_for_category(
        self,
        category: str,
        knowledge: Dict[str, ProductKnowledge],
        lang: Language,
        budget: int,
    ) -> List[SFTRecord]:
        """Generate Q-A for a specific architecture category."""
        templates = ARCHITECTURE_TEMPLATES.get(category, {}).get(lang, [])
        if not templates:
            return []

        records: List[SFTRecord] = []
        system_prompt = self.config.system_prompt_template
        products = list(knowledge.keys())
        remaining = budget

        for template in templates:
            if remaining <= 0:
                break

            # Fill template variables
            variations = self._expand_template(template, products, knowledge)

            for question, involved_products in variations:
                if remaining <= 0:
                    break

                answer = self._build_category_answer(
                    category, knowledge, involved_products, lang
                )

                if len(answer) < self.config.qa_min_answer_length:
                    continue

                primary_product = involved_products[0] if involved_products else "ecosystem"

                records.append(
                    SFTRecord(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": question},
                            {"role": "assistant", "content": answer},
                        ],
                        product=primary_product,
                        language=lang,
                        category=SFTCategory.ARCHITECTURE,
                        item_type=ItemType.CONCEPT,
                        source_file="architecture",
                        products_involved=involved_products,
                    )
                )
                remaining -= 1

        return records

    def _expand_template(
        self,
        template: str,
        products: List[str],
        knowledge: Dict[str, ProductKnowledge],
    ) -> List[tuple]:
        """Expand a template with product/cluster variables."""
        results: List[tuple] = []

        if "{cluster}" in template:
            for cluster_name in PRODUCT_CLUSTERS:
                q = template.format(cluster=cluster_name.replace("_", " "))
                involved = PRODUCT_CLUSTERS[cluster_name][:5]
                results.append((q, involved))

        elif "{product_a}" in template and "{product_b}" in template:
            sample_pairs = _sample_product_pairs(products, max_pairs=20)
            for a, b in sample_pairs:
                da = PRODUCT_DISPLAY_NAMES.get(a, a)
                db = PRODUCT_DISPLAY_NAMES.get(b, b)
                q = template.format(product_a=da, product_b=db)
                results.append((q, [a, b]))

        elif "{product}" in template:
            sample = random.sample(products, min(len(products), len(products)))
            for p in sample:
                dp = PRODUCT_DISPLAY_NAMES.get(p, p)
                q = template.format(product=dp)
                results.append((q, [p]))

        else:
            results.append((template, products[:5]))

        return results

    def _build_category_answer(
        self,
        category: str,
        knowledge: Dict[str, ProductKnowledge],
        involved_products: List[str],
        lang: Language,
    ) -> str:
        """Build an answer for an architecture category question."""
        if category == "ecosystem_overview":
            return self._build_ecosystem_answer(knowledge, lang)
        elif category == "shared_components":
            return self._build_shared_components_answer(knowledge, involved_products, lang)
        elif category == "security_model":
            return self._build_security_answer(knowledge, involved_products, lang)
        elif category == "integration_strategy":
            return self._build_integration_answer(knowledge, involved_products, lang)
        elif category == "deployment_architecture":
            return self._build_deployment_answer(knowledge, lang)
        elif category == "performance_tuning":
            return self._build_performance_answer(knowledge, involved_products, lang)
        elif category == "migration_strategy":
            return self._build_migration_answer(knowledge, involved_products, lang)
        else:
            return self._build_generic_answer(knowledge, involved_products, lang)

    def _build_ecosystem_answer(
        self, knowledge: Dict[str, ProductKnowledge], lang: Language
    ) -> str:
        """Build comprehensive product ecosystem overview."""
        parts: List[str] = []
        header = {
            "ja": "TmaxSoft製品エコシステム",
            "ko": "TmaxSoft 제품 에코시스템",
            "en": "TmaxSoft Product Ecosystem",
        }
        parts.append(f"**{header.get(lang.value, header['en'])}**\n")

        for cluster_name, members in PRODUCT_CLUSTERS.items():
            cluster_display = cluster_name.replace("_", " ").title()
            product_names = []
            for m in members:
                if m in knowledge:
                    pk = knowledge[m]
                    product_names.append(f"{pk.display_name} ({pk.total_items} items)")
                else:
                    dn = PRODUCT_DISPLAY_NAMES.get(m, m)
                    product_names.append(dn)

            parts.append(f"\n**{cluster_display}**:")
            for name in product_names:
                parts.append(f"  - {name}")

        total = sum(pk.total_items for pk in knowledge.values())
        parts.append(f"\nTotal: {len(knowledge)} products, {total} documented items")

        return "\n".join(parts)

    def _build_shared_components_answer(
        self,
        knowledge: Dict[str, ProductKnowledge],
        involved: List[str],
        lang: Language,
    ) -> str:
        """Describe shared components between products."""
        parts: List[str] = []
        for p in involved[:3]:
            if p in knowledge:
                pk = knowledge[p]
                parts.append(
                    f"**{pk.display_name}**: {pk.total_items} items "
                    f"({len(pk.commands)} commands, {len(pk.configs)} configs)"
                )
        # Find shared command names
        if len(involved) >= 2:
            all_cmd_sets = []
            for p in involved[:3]:
                if p in knowledge:
                    all_cmd_sets.append({c.name for c in knowledge[p].commands})
            if len(all_cmd_sets) >= 2:
                shared = all_cmd_sets[0]
                for s in all_cmd_sets[1:]:
                    shared &= s
                if shared:
                    parts.append(f"\nShared commands: {', '.join(list(shared)[:5])}")

        return "\n".join(parts)

    def _build_security_answer(
        self,
        knowledge: Dict[str, ProductKnowledge],
        involved: List[str],
        lang: Language,
    ) -> str:
        """Build security model answer."""
        parts: List[str] = []
        # Find TACF product
        tacf_key = "openframe_tacf_v2"
        if tacf_key in knowledge:
            pk = knowledge[tacf_key]
            parts.append(f"**{pk.display_name}** security model:")
            parts.append(f"  - Commands: {len(pk.commands)}")
            parts.append(f"  - Config parameters: {len(pk.configs)}")
            if pk.features:
                parts.append(f"  - Features: {', '.join(f.name for f in pk.features[:3])}")
        else:
            parts.append("OpenFrame TACF provides centralized security management.")

        for p in involved[:2]:
            if p in knowledge and p != tacf_key:
                pk = knowledge[p]
                parts.append(f"\n**{pk.display_name}** security aspects:")
                parts.append(f"  - {pk.total_items} documented items")

        return "\n".join(parts)

    def _build_integration_answer(
        self,
        knowledge: Dict[str, ProductKnowledge],
        involved: List[str],
        lang: Language,
    ) -> str:
        """Build integration architecture answer."""
        parts: List[str] = []
        for p in involved[:3]:
            if p in knowledge:
                pk = knowledge[p]
                parts.append(f"**{pk.display_name}**: {pk.total_items} documented items")
                if pk.apis:
                    parts.append(f"  APIs: {', '.join(a.name for a in pk.apis[:3])}")

        parts.append(
            "\nIntegration between these products follows the TmaxSoft "
            "enterprise architecture patterns documented in the official manuals."
        )
        return "\n".join(parts)

    def _build_deployment_answer(
        self,
        knowledge: Dict[str, ProductKnowledge],
        lang: Language,
    ) -> str:
        """Build deployment architecture answer."""
        parts: List[str] = []
        header = {
            "ja": "デプロイメントアーキテクチャ",
            "ko": "배포 아키텍처",
            "en": "Deployment Architecture",
        }
        parts.append(f"**{header.get(lang.value, header['en'])}**\n")

        for cluster_name, members in PRODUCT_CLUSTERS.items():
            cluster_display = cluster_name.replace("_", " ").title()
            items_count = sum(
                knowledge[m].total_items for m in members if m in knowledge
            )
            parts.append(f"- **{cluster_display}**: {len(members)} products, {items_count} items")

        return "\n".join(parts)

    def _build_performance_answer(
        self,
        knowledge: Dict[str, ProductKnowledge],
        involved: List[str],
        lang: Language,
    ) -> str:
        """Build performance tuning answer."""
        parts: List[str] = []
        for p in involved[:3]:
            if p in knowledge:
                pk = knowledge[p]
                parts.append(f"**{pk.display_name}** performance configuration:")
                perf_configs = [
                    c for c in pk.configs
                    if any(kw in c.name.lower() for kw in ("max", "min", "size", "timeout", "buffer", "cache", "thread", "pool"))
                ]
                if perf_configs:
                    for c in perf_configs[:5]:
                        val = f" = {c.default_value}" if c.default_value else ""
                        parts.append(f"  - {c.name}{val}")
                else:
                    parts.append(f"  - {len(pk.configs)} config parameters available")

        return "\n".join(parts)

    def _build_migration_answer(
        self,
        knowledge: Dict[str, ProductKnowledge],
        involved: List[str],
        lang: Language,
    ) -> str:
        """Build migration strategy answer."""
        parts: List[str] = []
        all_migrations = []
        for p in involved:
            if p in knowledge:
                all_migrations.extend(knowledge[p].migrations)

        if all_migrations:
            for m in all_migrations[:5]:
                parts.append(f"**{m.name}**:")
                parts.append(f"  {m.description[:200]}")
                if m.source_platform:
                    parts.append(f"  Source: {m.source_platform}")
                if m.target_platform:
                    parts.append(f"  Target: {m.target_platform}")
                if m.steps:
                    for i, step in enumerate(m.steps[:5], 1):
                        parts.append(f"  {i}. {step}")
        else:
            parts.append(
                "Migration planning should follow the official TmaxSoft "
                "migration documentation for each product component."
            )
            for p in involved[:3]:
                if p in knowledge:
                    pk = knowledge[p]
                    parts.append(f"- {pk.display_name}: {pk.total_items} documented items")

        return "\n".join(parts)

    def _build_generic_answer(
        self,
        knowledge: Dict[str, ProductKnowledge],
        involved: List[str],
        lang: Language,
    ) -> str:
        """Fallback generic answer builder."""
        parts: List[str] = []
        for p in involved[:5]:
            if p in knowledge:
                pk = knowledge[p]
                parts.append(f"**{pk.display_name}**: {pk.total_items} documented items")
        return "\n".join(parts)


def _sample_product_pairs(
    products: List[str], max_pairs: int = 20
) -> List[tuple]:
    """Sample diverse product pairs from different clusters."""
    pairs: List[tuple] = []
    cluster_products: Dict[str, List[str]] = {}
    for cluster_name, members in PRODUCT_CLUSTERS.items():
        available = [p for p in members if p in products]
        if available:
            cluster_products[cluster_name] = available

    clusters = list(cluster_products.keys())

    # Cross-cluster pairs first
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            if len(pairs) >= max_pairs:
                break
            a = random.choice(cluster_products[clusters[i]])
            b = random.choice(cluster_products[clusters[j]])
            pairs.append((a, b))

    # Intra-cluster pairs if budget remains
    for cluster_name, members in cluster_products.items():
        if len(pairs) >= max_pairs:
            break
        if len(members) >= 2:
            a, b = random.sample(members, 2)
            pairs.append((a, b))

    return pairs[:max_pairs]
