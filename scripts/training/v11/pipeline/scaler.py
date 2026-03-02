"""Auto-scaling logic to meet target counts."""
from __future__ import annotations

import logging
import random
import re
from typing import Dict, List, Tuple

from .config import GenerationConfig
from .models import DPORecord, Language, SFTCategory, SFTRecord
from .manual_loader import PRODUCT_DISPLAY_NAMES

logger = logging.getLogger(__name__)

# ── Paraphrase mappings (rule-based) ──────────────────────────────

_PARAPHRASE_JA: List[Tuple[str, str]] = [
    ("について説明してください", "とは何ですか"),
    ("を教えてください", "は何ですか"),
    ("の構文と使用方法を教えてください", "はどのように使いますか"),
    ("のパラメータを説明してください", "にはどのようなパラメータがありますか"),
    ("の使用例を教えてください", "の具体例を示してください"),
    ("の原因と解決方法を教えてください", "はなぜ発生しますか？また解決方法は？"),
    ("の設定方法を説明してください", "はどう設定しますか"),
    ("の制限事項を教えてください", "の注意点は何ですか"),
    ("の移行手順を教えてください", "の移行方法を教えてください"),
]

_PARAPHRASE_KO: List[Tuple[str, str]] = [
    ("에 대해 설명해주세요", "이란 무엇인가요"),
    ("을 알려주세요", "은 무엇인가요"),
    ("의 구문과 사용법을 알려주세요", "을 어떻게 사용하나요"),
    ("의 파라미터를 설명해주세요", "에는 어떤 파라미터가 있나요"),
    ("의 원인과 해결 방법을 알려주세요", "은 왜 발생하나요? 해결 방법은?"),
]

_PARAPHRASE_EN: List[Tuple[str, str]] = [
    ("Explain the ", "What is "),
    ("What is the syntax and usage of ", "How do you use "),
    ("Describe the parameters of ", "What parameters does "),
    ("Provide usage examples for ", "Show examples of "),
    ("What causes error ", "Why does error "),
    ("How do you configure ", "What is the configuration procedure for "),
    ("What are the limitations of ", "What restrictions apply to "),
]

_PARAPHRASE_MAP: Dict[Language, List[Tuple[str, str]]] = {
    Language.JA: _PARAPHRASE_JA,
    Language.KO: _PARAPHRASE_KO,
    Language.EN: _PARAPHRASE_EN,
}


class Scaler:
    """Scale dataset up if below target thresholds."""

    def __init__(self, config: GenerationConfig):
        self.config = config
        # Track seen user questions to prevent exact duplicates
        self._seen_questions: set = set()

    def scale_sft(
        self, records: List[SFTRecord], target: int
    ) -> Tuple[List[SFTRecord], int]:
        """
        Scale SFT records up to target count using multi-round augmentation.

        Returns:
            (scaled records, number of new records added)
        """
        current = len(records)
        if current >= target:
            logger.info("SFT scaling: already at %d (target %d)", current, target)
            return records, 0

        # Seed the seen set with existing questions
        self._seen_questions = {r.user_text for r in records}

        total_added = 0
        all_records = list(records)
        max_rounds = 10

        for round_num in range(1, max_rounds + 1):
            deficit = target - len(all_records)
            if deficit <= 0:
                break

            logger.info(
                "SFT scaling round %d: need %d more (%d / %d)",
                round_num, deficit, len(all_records), target,
            )

            new_records: List[SFTRecord] = []

            # Method 1: Paraphrase existing questions (~40%)
            paraphrase_budget = int(deficit * 0.4)
            new_records.extend(self._paraphrase_batch(all_records, paraphrase_budget))

            # Method 2: Multi-turn chaining (~30%)
            chain_budget = int(deficit * 0.3)
            new_records.extend(self._chain_batch(all_records, chain_budget))

            # Method 3: Scenario expansion (~30%)
            scenario_budget = deficit - len(new_records)
            new_records.extend(self._scenario_batch(all_records, scenario_budget))

            # Method 4: Answer-variant augmentation (fallback for remaining deficit)
            if len(new_records) < deficit:
                variant_budget = deficit - len(new_records)
                new_records.extend(self._answer_variant_batch(all_records, variant_budget))

            if not new_records:
                logger.info("SFT scaling: no new records generated in round %d, stopping", round_num)
                break

            added_this_round = min(len(new_records), deficit)
            all_records.extend(new_records[:added_this_round])
            total_added += added_this_round

        logger.info("SFT scaling: added %d records → %d total", total_added, len(all_records))
        return all_records, total_added

    def scale_dpo(
        self, records: List[DPORecord], target: int
    ) -> Tuple[List[DPORecord], int]:
        """Scale DPO records up to target count with multi-round augmentation."""
        current = len(records)
        if current >= target:
            return records, 0

        # Track seen DPO prompts to prevent duplicates
        seen_prompts: set = {r.prompt for r in records}

        total_added = 0
        all_records = list(records)
        max_rounds = 10

        for round_num in range(1, max_rounds + 1):
            deficit = target - len(all_records)
            if deficit <= 0:
                break

            logger.info(
                "DPO scaling round %d: need %d more (%d / %d)",
                round_num, deficit, len(all_records), target,
            )

            new_records: List[DPORecord] = []
            candidates = list(all_records)
            random.shuffle(candidates)

            # Method 1: Paraphrase prompt
            for rec in candidates:
                if len(new_records) >= deficit:
                    break
                paraphrased = self._paraphrase_question(rec.prompt, rec.language)
                if paraphrased != rec.prompt and paraphrased not in seen_prompts:
                    seen_prompts.add(paraphrased)
                    new_records.append(
                        DPORecord(
                            prompt=paraphrased,
                            chosen=rec.chosen,
                            rejected=rec.rejected,
                            product=rec.product,
                            language=rec.language,
                            strategy=rec.strategy,
                            source_file=rec.source_file,
                            products_involved=rec.products_involved,
                        )
                    )

            # Method 2: Scenario prefix on prompt
            if len(new_records) < deficit:
                scenario_prefixes = {
                    Language.JA: [
                        "本番環境で", "障害時に", "初回設定時、", "パフォーマンス問題で",
                        "移行作業中に", "テスト環境で", "監視システムから",
                    ],
                    Language.KO: [
                        "운영 환경에서", "장애 시", "초기 설정 시,", "성능 이슈로",
                        "마이그레이션 중에", "테스트 환경에서", "모니터링 시스템에서",
                    ],
                    Language.EN: [
                        "In production, ", "During an outage, ", "During initial setup, ",
                        "For performance issues, ", "During migration, ",
                        "In a test environment, ", "From the monitoring system, ",
                    ],
                }
                random.shuffle(candidates)
                for rec in candidates:
                    if len(new_records) >= deficit:
                        break
                    prefixes = scenario_prefixes.get(rec.language, scenario_prefixes[Language.EN])
                    prefix = random.choice(prefixes)
                    new_prompt = prefix + rec.prompt
                    if new_prompt not in seen_prompts:
                        seen_prompts.add(new_prompt)
                        new_records.append(
                            DPORecord(
                                prompt=new_prompt,
                                chosen=rec.chosen,
                                rejected=rec.rejected,
                                product=rec.product,
                                language=rec.language,
                                strategy=rec.strategy,
                                source_file=rec.source_file,
                                products_involved=rec.products_involved,
                            )
                        )

            if not new_records:
                break

            added = min(len(new_records), deficit)
            all_records.extend(new_records[:added])
            total_added += added

        logger.info("DPO scaling: added %d records → %d total", total_added, len(all_records))
        return all_records, total_added

    # ── Scaling Methods ───────────────────────────────────────────

    def _paraphrase_batch(
        self, records: List[SFTRecord], budget: int
    ) -> List[SFTRecord]:
        """Generate paraphrased variants of existing questions."""
        new_records: List[SFTRecord] = []
        candidates = list(records)
        random.shuffle(candidates)

        for rec in candidates:
            if len(new_records) >= budget:
                break
            question = rec.user_text
            paraphrased = self._paraphrase_question(question, rec.language)
            if paraphrased != question and paraphrased not in self._seen_questions:
                self._seen_questions.add(paraphrased)
                new_records.append(
                    SFTRecord(
                        messages=[
                            rec.messages[0],  # system
                            {"role": "user", "content": paraphrased},
                            rec.messages[2],  # assistant
                        ],
                        product=rec.product,
                        language=rec.language,
                        category=rec.category,
                        item_type=rec.item_type,
                        source_file=rec.source_file,
                        source_page=rec.source_page,
                        products_involved=rec.products_involved,
                    )
                )

        return new_records

    def _chain_batch(
        self, records: List[SFTRecord], budget: int
    ) -> List[SFTRecord]:
        """Combine pairs of Q-A into multi-turn conversations."""
        new_records: List[SFTRecord] = []

        # Group by product
        by_product: Dict[str, List[SFTRecord]] = {}
        for r in records:
            by_product.setdefault(r.product, []).append(r)

        for product, group in by_product.items():
            if len(new_records) >= budget:
                break
            if len(group) < 2:
                continue

            random.shuffle(group)
            for i in range(0, len(group) - 1, 2):
                if len(new_records) >= budget:
                    break
                chained = self._chain_multi_turn(group[i], group[i + 1])
                chain_key = chained.user_text
                if chain_key not in self._seen_questions:
                    self._seen_questions.add(chain_key)
                    new_records.append(chained)

        return new_records

    def _scenario_batch(
        self, records: List[SFTRecord], budget: int
    ) -> List[SFTRecord]:
        """Add troubleshooting scenario variants."""
        new_records: List[SFTRecord] = []
        candidates = [r for r in records if r.item_type.value in ("command", "config", "error")]
        random.shuffle(candidates)

        scenario_prefixes = {
            Language.JA: [
                "本番環境で",
                "トラブルシューティング時に",
                "初めて設定する場合、",
                "エラーが発生した場合、",
                "運用中のシステムで",
                "バッチ処理において",
                "クラスター構成で",
                "性能改善のために",
            ],
            Language.KO: [
                "프로덕션 환경에서",
                "트러블슈팅 시",
                "처음 설정하는 경우,",
                "에러가 발생한 경우,",
                "운영 중인 시스템에서",
                "배치 처리에서",
                "클러스터 구성에서",
                "성능 개선을 위해",
            ],
            Language.EN: [
                "In a production environment, ",
                "When troubleshooting, ",
                "When configuring for the first time, ",
                "When an error occurs, ",
                "In a running system, ",
                "During batch processing, ",
                "In a cluster setup, ",
                "For performance tuning, ",
            ],
        }

        for rec in candidates:
            if len(new_records) >= budget:
                break
            prefixes = scenario_prefixes.get(rec.language, scenario_prefixes[Language.EN])
            prefix = random.choice(prefixes)
            question = prefix + rec.user_text

            if question not in self._seen_questions:
                self._seen_questions.add(question)
                new_records.append(
                    SFTRecord(
                        messages=[
                            rec.messages[0],
                            {"role": "user", "content": question},
                            rec.messages[2],
                        ],
                        product=rec.product,
                        language=rec.language,
                        category=rec.category,
                        item_type=rec.item_type,
                        source_file=rec.source_file,
                        source_page=rec.source_page,
                        products_involved=rec.products_involved,
                    )
                )

        return new_records

    def _answer_variant_batch(
        self, records: List[SFTRecord], budget: int
    ) -> List[SFTRecord]:
        """Create variants by combining scenario prefix + paraphrase."""
        new_records: List[SFTRecord] = []
        candidates = list(records)
        random.shuffle(candidates)

        context_prefixes = {
            Language.JA: [
                "次の状況を考慮して、",
                "システム管理者として、",
                "開発チームから質問があります。",
                "移行プロジェクトにおいて、",
                "ベストプラクティスとして、",
                "セキュリティの観点から、",
                "監査対応のため、",
                "DR（災害復旧）計画において、",
                "新規メンバーへの説明として、",
                "バージョンアップ時に、",
            ],
            Language.KO: [
                "다음 상황을 고려하여,",
                "시스템 관리자로서,",
                "개발팀에서 질문이 있습니다.",
                "마이그레이션 프로젝트에서,",
                "모범 사례로서,",
                "보안 관점에서,",
                "감사 대응을 위해,",
                "DR(재해복구) 계획에서,",
                "신규 멤버 교육으로,",
                "버전 업그레이드 시,",
            ],
            Language.EN: [
                "Considering the following scenario, ",
                "As a system administrator, ",
                "The development team has a question. ",
                "In a migration project, ",
                "As a best practice, ",
                "From a security perspective, ",
                "For audit compliance, ",
                "In a disaster recovery plan, ",
                "When onboarding new team members, ",
                "During a version upgrade, ",
            ],
        }

        for rec in candidates:
            if len(new_records) >= budget:
                break
            prefixes = context_prefixes.get(rec.language, context_prefixes[Language.EN])
            prefix = random.choice(prefixes)
            question = prefix + rec.user_text

            if question not in self._seen_questions:
                self._seen_questions.add(question)
                new_records.append(
                    SFTRecord(
                        messages=[
                            rec.messages[0],
                            {"role": "user", "content": question},
                            rec.messages[2],
                        ],
                        product=rec.product,
                        language=rec.language,
                        category=rec.category,
                        item_type=rec.item_type,
                        source_file=rec.source_file,
                        source_page=rec.source_page,
                        products_involved=rec.products_involved,
                    )
                )

        return new_records

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _paraphrase_question(question: str, lang: Language) -> str:
        """Generate a paraphrase using rule-based transforms."""
        mappings = _PARAPHRASE_MAP.get(lang, [])
        for original, replacement in mappings:
            if original in question:
                return question.replace(original, replacement, 1)
        return question

    @staticmethod
    def _chain_multi_turn(
        record_a: SFTRecord, record_b: SFTRecord
    ) -> SFTRecord:
        """Combine two Q-A into a multi-turn conversation."""
        messages = [
            record_a.messages[0],  # system prompt (from first)
            {"role": "user", "content": record_a.user_text},
            {"role": "assistant", "content": record_a.assistant_text},
            {"role": "user", "content": record_b.user_text},
            {"role": "assistant", "content": record_b.assistant_text},
        ]
        return SFTRecord(
            messages=messages,
            product=record_a.product,
            language=record_a.language,
            category=record_a.category,
            item_type=record_a.item_type,
            source_file=record_a.source_file,
            source_page=record_a.source_page,
            products_involved=list(
                set(record_a.products_involved + record_b.products_involved)
            ),
        )
