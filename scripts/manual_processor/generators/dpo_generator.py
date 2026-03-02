"""DPO (Direct Preference Optimization) 학습 데이터 생성기

SFT 레코드에서 3가지 전략으로 Preference Pair를 생성합니다:
- cross_product (40%): 다른 제품의 응답을 rejected로 사용 (RAFT Distractor)
- fact_mutation (35%): 사실 정보(숫자, 이름) 변형
- summary_cross (25%): 관련 없는 요약 내용으로 교체
"""

import re
import random
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict

from ..models.training import SFTRecord, DPORecord, DataLanguage, TrainingStats

logger = logging.getLogger(__name__)


class DPOGenerator:
    """DPO Preference Pairs 생성

    SFT 레코드를 입력받아 chosen/rejected 쌍을 생성합니다.
    RAFT 논문의 Distractor Document 개념을 활용하여
    모델이 무관한 정보를 무시하는 능력을 강화합니다.
    """

    STRATEGIES = {
        "cross_product": 0.40,     # 교차 제품
        "fact_mutation": 0.35,     # 사실 변이
        "summary_cross": 0.25,    # 요약 교차
    }

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def generate_all(
        self,
        sft_records: List[SFTRecord],
        target_count: int = 2000,
    ) -> TrainingStats:
        """SFT 레코드에서 DPO 쌍 생성

        Args:
            sft_records: SFT 학습 레코드 목록
            target_count: 목표 DPO 쌍 수

        Returns:
            TrainingStats with generation statistics
        """
        stats = TrainingStats()
        stats.by_format["dpo"] = 0

        if not sft_records:
            logger.warning("[DPO] No SFT records provided")
            return stats

        # 제품별 인덱스 구축
        by_product: Dict[str, List[SFTRecord]] = defaultdict(list)
        by_type: Dict[str, List[SFTRecord]] = defaultdict(list)
        for r in sft_records:
            by_product[r.product].append(r)
            by_type[r.item_type].append(r)

        dpo_records: List[DPORecord] = []

        for strategy, ratio in self.STRATEGIES.items():
            count = int(target_count * ratio)
            generated = 0

            # 충분한 소스 확보를 위해 셔플
            pool = list(sft_records)
            random.shuffle(pool)

            for record in pool:
                if generated >= count:
                    break

                rejected = None

                if strategy == "cross_product":
                    rejected = self._generate_cross_product(
                        record, by_product
                    )
                elif strategy == "fact_mutation":
                    rejected = self._mutate_facts(record)
                elif strategy == "summary_cross":
                    rejected = self._cross_summary(
                        record, by_type, sft_records
                    )

                if rejected and rejected != record.response:
                    dpo_records.append(DPORecord(
                        prompt=self._build_prompt(record),
                        chosen=record.response,
                        rejected=rejected,
                        product=record.product,
                        language=record.language,
                        strategy=strategy,
                    ))
                    generated += 1

            stats.by_type[strategy] = generated
            logger.info(f"[DPO] {strategy}: {generated} pairs generated")

        # 셔플 후 출력
        random.shuffle(dpo_records)

        dpo_dir = Path(self.output_dir) / "dpo"
        dpo_dir.mkdir(parents=True, exist_ok=True)

        # 전체 파일
        all_path = dpo_dir / "dpo_all.jsonl"
        self._write_jsonl(dpo_records, all_path)

        # Train/Eval 분할 (90:10)
        split_idx = int(len(dpo_records) * 0.9)
        train = dpo_records[:split_idx]
        eval_ = dpo_records[split_idx:]

        self._write_jsonl(train, dpo_dir / "train.jsonl")
        self._write_jsonl(eval_, dpo_dir / "eval.jsonl")

        # 통계 갱신
        stats.total_records = len(dpo_records)
        stats.train_count = len(train)
        stats.eval_count = len(eval_)
        stats.by_format["dpo"] = len(dpo_records)

        for r in dpo_records:
            lang = r.language.value if isinstance(r.language, DataLanguage) else r.language
            stats.by_language[lang] = stats.by_language.get(lang, 0) + 1
            stats.by_product[r.product] = stats.by_product.get(r.product, 0) + 1

        logger.info(
            f"[DPO] Total: {len(dpo_records)} pairs "
            f"(train={len(train)}, eval={len(eval_)})"
        )

        return stats

    def _build_prompt(self, record: SFTRecord) -> str:
        """SFT 레코드에서 DPO prompt 구성 (system + user)"""
        return (
            f"<|im_start|>system\n{record.system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{record.instruction}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    def _generate_cross_product(
        self,
        record: SFTRecord,
        by_product: Dict[str, List[SFTRecord]],
    ) -> Optional[str]:
        """다른 제품의 응답을 rejected로 사용 (RAFT Distractor)

        같은 item_type, 같은 언어의 다른 제품 응답을 선택하여
        모델이 제품 간 혼동을 학습하지 않도록 합니다.
        """
        candidates = []
        for product, records in by_product.items():
            if product == record.product:
                continue
            for r in records:
                if (r.item_type == record.item_type
                        and r.language == record.language):
                    candidates.append(r)

        if not candidates:
            return None

        return random.choice(candidates).response

    def _mutate_facts(self, record: SFTRecord) -> str:
        """응답의 사실 정보를 변형

        - 에러코드 번호 변경 (±100~999)
        - 포트번호 변경
        - 버전번호 변경
        - 제품명을 유사 제품으로 교체
        """
        mutated = record.response

        # 1. 에러코드/숫자 변형 (4-5자리 숫자)
        numbers = re.findall(r'-?\d{4,5}', mutated)
        for num in numbers[:2]:  # 최대 2개만 변형
            try:
                new_num = str(int(num) + random.choice([-1, 1]) * random.randint(100, 999))
                mutated = mutated.replace(num, new_num, 1)
            except ValueError:
                continue

        # 2. 포트번호 변형 (4자리)
        ports = re.findall(r'(?:port|ポート|포트)\s*[:：]?\s*(\d{4})', mutated, re.IGNORECASE)
        for port in ports[:1]:
            new_port = str(int(port) + random.randint(1, 100))
            mutated = mutated.replace(port, new_port, 1)

        # 3. 버전 변형
        versions = re.findall(r'(\d+\.\d+\.\d+)', mutated)
        for ver in versions[:1]:
            parts = ver.split('.')
            parts[-1] = str(int(parts[-1]) + random.randint(1, 5))
            new_ver = '.'.join(parts)
            mutated = mutated.replace(ver, new_ver, 1)

        return mutated

    def _cross_summary(
        self,
        record: SFTRecord,
        by_type: Dict[str, List[SFTRecord]],
        all_records: List[SFTRecord],
    ) -> Optional[str]:
        """관련 없는 요약 내용으로 rejected 생성

        같은 언어, 다른 item_type의 응답을 사용하여
        모델이 질문 유형과 무관한 정보를 구별하도록 합니다.
        """
        # 다른 유형의 레코드 수집
        other_types = [t for t in by_type.keys() if t != record.item_type]
        if not other_types:
            # 같은 유형이라도 다른 제품에서 선택
            candidates = [
                r for r in all_records
                if r.product != record.product
                and r.language == record.language
            ]
        else:
            target_type = random.choice(other_types)
            candidates = [
                r for r in by_type[target_type]
                if r.language == record.language
            ]

        if not candidates:
            return None

        return random.choice(candidates).response

    def _write_jsonl(self, records: List[DPORecord], output_path: Path):
        """DPO 레코드를 JSONL로 출력"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for record in records:
                line = json.dumps(record.to_jsonl(), ensure_ascii=False)
                f.write(line + "\n")

        logger.info(f"  Written {len(records)} DPO pairs → {output_path.name}")
