"""통합 LoRA용 DPO 데이터 생성기

4가지 전략으로 preference 쌍 생성:
1. unified_vs_biased (45%): 통합 답변 vs 단일 제품 편향 답변
2. complete_vs_partial (25%): 완전한 관계 설명 vs 불완전한 설명
3. correct_order_vs_wrong (20%): 올바른 순서/관계 vs 잘못된 순서/관계
4. platform_confusion (10%): 올바른 플랫폼 정보 vs 다른 플랫폼 정보 혼동
"""

import logging
import random
import re
from collections import Counter
from typing import List

from ..config import PRODUCT_DISPLAY_NAMES, UNIFIED_SYSTEM_PROMPTS
from ..models.training import DataLanguage, UnifiedDPORecord, UnifiedSFTRecord

logger = logging.getLogger(__name__)


class UnifiedDPOGenerator:
    """통합 LoRA용 DPO 데이터 생성기"""

    def __init__(self, unified_sft_records: List[UnifiedSFTRecord]):
        self.sft_records = unified_sft_records

    def generate_all(self, target_count: int = 500) -> List[UnifiedDPORecord]:
        """통합 DPO 데이터 생성"""
        logger.info(f"=== 통합 DPO 데이터 생성 시작 (목표: {target_count}쌍) ===")

        n_unified = int(target_count * 0.45)
        n_complete = int(target_count * 0.25)
        n_platform = int(target_count * 0.10)
        n_correct = target_count - n_unified - n_complete - n_platform

        records: List[UnifiedDPORecord] = []

        # Strategy 1: unified_vs_biased (45%)
        s1 = self._generate_unified_vs_biased(n_unified)
        logger.info(f"[Strategy 1] unified_vs_biased: {len(s1)}쌍")
        records.extend(s1)

        # Strategy 2: complete_vs_partial (25%)
        s2 = self._generate_complete_vs_partial(n_complete)
        logger.info(f"[Strategy 2] complete_vs_partial: {len(s2)}쌍")
        records.extend(s2)

        # Strategy 3: correct_order_vs_wrong (20%)
        s3 = self._generate_correct_order_vs_wrong(n_correct)
        logger.info(f"[Strategy 3] correct_order_vs_wrong: {len(s3)}쌍")
        records.extend(s3)

        # Strategy 4: platform_confusion (10%)
        s4 = self._generate_platform_confusion(n_platform)
        logger.info(f"[Strategy 4] platform_confusion: {len(s4)}쌍")
        records.extend(s4)

        random.shuffle(records)
        logger.info(f"통합 DPO 총: {len(records)}쌍")
        return records

    def _generate_unified_vs_biased(self, count: int) -> List[UnifiedDPORecord]:
        """통합 답변(chosen) vs 단일 제품 편향 답변(rejected)

        SFT 레코드에서 2+ 제품 관련 레코드를 선택하고,
        chosen = 원래 통합 응답, rejected = 1개 제품만 언급하는 편향 응답
        """
        records = []
        # 2개 이상 제품 관련 SFT 레코드만 필터
        multi_product = [r for r in self.sft_records if len(r.products_involved) >= 2]

        if not multi_product:
            logger.warning("multi-product SFT 레코드가 없어 unified_vs_biased 생성 불가")
            return records

        candidates = random.sample(multi_product, min(count, len(multi_product)))

        for sft in candidates:
            # chosen: 원래 통합 응답
            chosen = sft.response

            # rejected: 첫 번째 제품만 남기고 나머지 제품 관련 문장 제거
            rejected = self._create_biased_response(sft)

            if rejected and rejected != chosen and len(rejected) >= 20:
                records.append(
                    UnifiedDPORecord(
                        prompt=sft.instruction,
                        chosen=chosen,
                        rejected=rejected,
                        products_involved=sft.products_involved,
                        relation_type=sft.relation_type,
                        language=sft.language,
                        strategy="unified_vs_biased",
                    )
                )

        return records

    def _create_biased_response(self, sft: UnifiedSFTRecord) -> str:
        """통합 응답에서 첫 번째 제품만 남기는 편향 응답 생성"""
        if len(sft.products_involved) < 2:
            return ""

        # 첫 번째 제품 이외의 제품명을 응답에서 제거
        response = sft.response
        keep_product = sft.products_involved[0]

        for product_id in sft.products_involved[1:]:
            display_name = PRODUCT_DISPLAY_NAMES.get(product_id, "")
            if display_name:
                # 해당 제품 언급이 포함된 문장을 제거
                sentences = response.split("\n")
                filtered = []
                for s in sentences:
                    if display_name not in s:
                        filtered.append(s)
                response = "\n".join(filtered)

        # 너무 짧아지면 첫 번째 제품에 대한 일반적 설명으로 대체
        if len(response.strip()) < 20:
            keep_name = PRODUCT_DISPLAY_NAMES.get(keep_product, keep_product)
            if sft.language == DataLanguage.JA:
                response = f"{keep_name}は、TmaxSoftの製品の一つです。詳細についてはマニュアルを参照してください。"
            else:
                response = f"{keep_name}은(는) TmaxSoft의 제품 중 하나입니다. 자세한 내용은 매뉴얼을 참조해주세요."

        return response.strip()

    def _generate_complete_vs_partial(self, count: int) -> List[UnifiedDPORecord]:
        """완전한 관계 설명(chosen) vs 불완전한 설명(rejected)

        R-04(기동순서), R-01(의존관계) 등 여러 구성요소가 나열되는 레코드에서,
        chosen = 전체 포함, rejected = 일부 무작위 삭제
        """
        records = []
        # 3개 이상 제품 관련 레코드가 가장 적합
        rich_records = [r for r in self.sft_records if len(r.products_involved) >= 3]

        if not rich_records:
            # 2개 이상이라도 사용
            rich_records = [r for r in self.sft_records if len(r.products_involved) >= 2]

        if not rich_records:
            return records

        candidates = random.choices(rich_records, k=min(count, len(rich_records) * 2))

        for sft in candidates:
            if len(records) >= count:
                break

            chosen = sft.response
            rejected = self._create_partial_response(sft)

            if rejected and rejected != chosen and len(rejected) >= 20:
                records.append(
                    UnifiedDPORecord(
                        prompt=sft.instruction,
                        chosen=chosen,
                        rejected=rejected,
                        products_involved=sft.products_involved,
                        relation_type=sft.relation_type,
                        language=sft.language,
                        strategy="complete_vs_partial",
                    )
                )

        return records

    def _create_partial_response(self, sft: UnifiedSFTRecord) -> str:
        """응답에서 일부 항목을 무작위로 삭제하여 불완전한 응답 생성"""
        lines = sft.response.split("\n")

        if len(lines) < 4:
            # 줄 수가 적으면 문장 단위로 삭제 시도
            sentences = re.split(r"[。\.\n]", sft.response)
            if len(sentences) >= 3:
                # 30~50% 문장 제거
                n_remove = max(1, len(sentences) // 3)
                indices = random.sample(range(len(sentences)), n_remove)
                partial = [s for i, s in enumerate(sentences) if i not in indices and s.strip()]
                return "。".join(partial) + "。" if partial else ""
            return ""

        # 번호 붙은 리스트 항목 중 일부 제거
        numbered_indices = [i for i, line in enumerate(lines) if re.match(r"^\d+\.", line.strip())]

        if len(numbered_indices) >= 3:
            # 30~50% 항목 제거
            n_remove = max(1, len(numbered_indices) // 3)
            remove_indices = set(random.sample(numbered_indices, n_remove))
            partial_lines = [line for i, line in enumerate(lines) if i not in remove_indices]
            return "\n".join(partial_lines).strip()

        # 번호 없는 경우: 줄 30% 제거
        n_remove = max(1, len(lines) // 3)
        remove_indices = set(random.sample(range(len(lines)), n_remove))
        partial_lines = [line for i, line in enumerate(lines) if i not in remove_indices]
        return "\n".join(partial_lines).strip()

    def _generate_correct_order_vs_wrong(self, count: int) -> List[UnifiedDPORecord]:
        """올바른 순서(chosen) vs 잘못된 순서(rejected)

        R-04(기동순서), R-01(의존관계) 레코드에서 순서를 뒤집어서 rejected 생성
        """
        records = []
        # R-04 레코드가 가장 적합
        order_records = [r for r in self.sft_records if r.relation_type in ("R-04", "R-01")]

        if not order_records:
            return records

        candidates = random.choices(order_records, k=min(count, len(order_records) * 3))

        for sft in candidates:
            if len(records) >= count:
                break

            chosen = sft.response
            rejected = self._create_wrong_order_response(sft)

            if rejected and rejected != chosen and len(rejected) >= 20:
                records.append(
                    UnifiedDPORecord(
                        prompt=sft.instruction,
                        chosen=chosen,
                        rejected=rejected,
                        products_involved=sft.products_involved,
                        relation_type=sft.relation_type,
                        language=sft.language,
                        strategy="correct_order_vs_wrong",
                    )
                )

        return records

    def _create_wrong_order_response(self, sft: UnifiedSFTRecord) -> str:
        """기동 순서나 의존 관계를 뒤집어서 잘못된 응답 생성"""
        lines = sft.response.split("\n")

        # 번호 붙은 리스트 항목을 찾아서 순서 뒤집기
        numbered = []
        other = []
        for i, line in enumerate(lines):
            if re.match(r"^\d+\.", line.strip()):
                numbered.append(line)
            else:
                other.append((i, line))

        if len(numbered) >= 3:
            # 번호 항목 순서를 뒤집거나 셔플
            content_parts = [re.sub(r"^\d+\.", "", line).strip() for line in numbered]
            random.shuffle(content_parts)

            # 새 번호 부여
            shuffled = [f"{i + 1}. {part}" for i, part in enumerate(content_parts)]

            # 원래 위치에 삽입
            result_lines = list(lines)
            num_idx = 0
            for i, line in enumerate(result_lines):
                if re.match(r"^\d+\.", line.strip()) and num_idx < len(shuffled):
                    result_lines[i] = shuffled[num_idx]
                    num_idx += 1

            return "\n".join(result_lines).strip()

        # 의존 관계: A→B를 B→A로 뒤집기
        response = sft.response
        if len(sft.products_involved) >= 2:
            name_a = PRODUCT_DISPLAY_NAMES.get(sft.products_involved[0], "")
            name_b = PRODUCT_DISPLAY_NAMES.get(sft.products_involved[1], "")
            if name_a and name_b:
                # 단순 이름 스왑
                placeholder = "___TEMP___"
                response = response.replace(name_a, placeholder)
                response = response.replace(name_b, name_a)
                response = response.replace(placeholder, name_b)
                return response

        return ""

    def _generate_platform_confusion(self, count: int) -> List[UnifiedDPORecord]:
        """올바른 플랫폼 정보(chosen) vs 다른 플랫폼 정보 혼동(rejected)

        R-08(플랫폼 차이), R-03(비교) 레코드에서 MVS/MSP/XSP 정보를 뒤섞어서
        잘못된 플랫폼 정보를 rejected로 사용
        """
        records = []
        # R-08(플랫폼 차이) + R-03(비교)에서 플랫폼 키워드가 있는 레코드
        platform_keywords = {"MVS", "MSP", "XSP", "PSAM", "BMS", "MFS",
                             "JES2", "JES3", "AIMPED", "AIM/DC", "AIM/DB",
                             "HiDB", "NDB", "RDBII", "JEF", "EBCDIC"}
        platform_records = [
            r for r in self.sft_records
            if r.relation_type in ("R-08", "R-03")
            and any(kw in r.response for kw in platform_keywords)
        ]

        if not platform_records:
            # R-08이 없으면 R-06(마이그레이션)에서도 시도
            platform_records = [
                r for r in self.sft_records
                if r.relation_type == "R-06"
                and any(kw in r.response for kw in platform_keywords)
            ]

        if not platform_records:
            logger.warning("플랫폼 관련 SFT 레코드가 없어 platform_confusion 생성 불가")
            return records

        candidates = random.choices(platform_records, k=min(count * 2, len(platform_records) * 3))

        for sft in candidates:
            if len(records) >= count:
                break

            chosen = sft.response
            rejected = self._swap_platform_info(sft.response)

            if rejected and rejected != chosen and len(rejected) >= 20:
                records.append(
                    UnifiedDPORecord(
                        prompt=sft.instruction,
                        chosen=chosen,
                        rejected=rejected,
                        products_involved=sft.products_involved,
                        relation_type=sft.relation_type,
                        language=sft.language,
                        strategy="platform_confusion",
                    )
                )

        return records

    def _swap_platform_info(self, response: str) -> str:
        """응답에서 플랫폼 관련 키워드를 교환하여 잘못된 정보 생성"""
        # 교환 쌍 정의 (혼동하기 쉬운 플랫폼 정보)
        swap_pairs = [
            ("MVS", "XSP"),
            ("BMS", "PSAM"),
            ("BMS", "MFS"),
            ("HiDB", "NDB"),
            ("HiDB", "RDBII"),
            ("OSC", "AIM/DC"),
            ("OSI", "AIM/DC"),
            ("JES2", "AIMPED"),
            ("DL/I", "DML"),
        ]

        # 무작위로 1-2개 쌍 선택하여 교환
        applicable = [
            (a, b) for a, b in swap_pairs
            if a in response or b in response
        ]

        if not applicable:
            return ""

        n_swaps = min(random.randint(1, 2), len(applicable))
        selected = random.sample(applicable, n_swaps)

        result = response
        for term_a, term_b in selected:
            placeholder = f"__SWAP_{term_a}__"
            result = result.replace(term_a, placeholder)
            result = result.replace(term_b, term_a)
            result = result.replace(placeholder, term_b)

        return result.strip()
