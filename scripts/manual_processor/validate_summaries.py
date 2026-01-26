"""
요약 시스템 검증 스크립트

전체 매뉴얼에서 무작위로 키워드를 추출하고 검색 테스트를 수행합니다.
"""

import asyncio
import json
import random
import re
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.api.services.summary_search_service import SummarySearchService

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """테스트 결과"""
    keyword: str
    keyword_type: str  # command, error_code, term, concept
    found: bool
    products: List[str]
    has_description: bool
    description_preview: str


class SummaryValidator:
    """요약 시스템 검증기"""

    def __init__(self, summaries_dir: Path = None):
        self.summaries_dir = summaries_dir or Path("/opt/kms/uploads/summaries")
        self.service = SummarySearchService(self.summaries_dir)
        self.index_path = self.summaries_dir / "index.json"

    def load_all_keywords(self) -> Dict[str, List[str]]:
        """인덱스에서 모든 키워드 로드"""
        keywords = {
            "commands": [],
            "error_codes": [],
            "terms": [],
            "concepts": [],
            "configs": [],
        }

        # JSON 인덱스에서 로드
        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                items = data.get("items", {})

                # 모든 아이템에서 키워드 추출
                for category, entries in items.items():
                    if isinstance(entries, list):
                        for entry in entries:
                            if isinstance(entry, dict):
                                name = entry.get("name", "")
                                item_type = entry.get("type", "")

                                if item_type == "command" or "init" in name.lower() or "boot" in name.lower():
                                    keywords["commands"].append(name)
                                elif item_type == "config":
                                    keywords["configs"].append(name)
                                else:
                                    keywords["concepts"].append(name)
            except Exception as e:
                logger.warning(f"인덱스 로드 실패: {e}")

        # 에러 코드 파일에서 추출 (### NAME (-XXXXX) 형식)
        error_codes_dir = self.summaries_dir / "error-codes"
        if error_codes_dir.exists():
            for file in error_codes_dir.glob("*.md"):
                if file.name == "index.md":
                    continue
                content = file.read_text(encoding="utf-8")
                # ### PSAM_ERR_xxx (-21001) 형식
                codes = re.findall(r"\(-(\d{4,5})\)", content)
                keywords["error_codes"].extend(codes)

        # 용어 파일에서 추출
        glossary_dir = self.summaries_dir / "glossary"
        if glossary_dir.exists():
            for file in glossary_dir.glob("*.md"):
                if file.name == "index.md":
                    continue
                content = file.read_text(encoding="utf-8")
                terms = re.findall(r"## ([A-Z][A-Z0-9_]+)", content)
                keywords["terms"].extend(terms)

        # 명령어 파일에서 추출
        commands_dir = self.summaries_dir / "commands"
        if commands_dir.exists():
            for file in commands_dir.glob("*.md"):
                if file.name == "index.md":
                    continue
                content = file.read_text(encoding="utf-8")
                cmds = re.findall(r"## ([a-zA-Z][a-zA-Z0-9_-]+)", content)
                keywords["commands"].extend(cmds)

        # 중복 제거
        for key in keywords:
            keywords[key] = list(set(keywords[key]))

        return keywords

    def sample_keywords(self, keywords: Dict[str, List[str]], total: int = 500) -> List[Tuple[str, str]]:
        """키워드 무작위 샘플링 (타입별 균등 분배)"""
        samples = []

        # 타입별 비율 설정
        ratios = {
            "commands": 0.30,      # 30%
            "error_codes": 0.25,   # 25%
            "terms": 0.20,         # 20%
            "concepts": 0.15,      # 15%
            "configs": 0.10,       # 10%
        }

        for kw_type, ratio in ratios.items():
            count = int(total * ratio)
            available = keywords.get(kw_type, [])
            if available:
                sampled = random.sample(available, min(count, len(available)))
                samples.extend([(kw, kw_type) for kw in sampled])

        # 부족분은 가장 많은 타입에서 추가
        while len(samples) < total:
            all_remaining = []
            for kw_type, kws in keywords.items():
                used = [s[0] for s in samples if s[1] == kw_type]
                remaining = [kw for kw in kws if kw not in used]
                all_remaining.extend([(kw, kw_type) for kw in remaining])

            if not all_remaining:
                break

            additional = random.sample(all_remaining, min(total - len(samples), len(all_remaining)))
            samples.extend(additional)

        random.shuffle(samples)
        return samples[:total]

    async def test_keyword(self, keyword: str, kw_type: str) -> TestResult:
        """단일 키워드 테스트"""
        found = False
        products = []
        has_description = False
        description_preview = ""

        try:
            if kw_type == "commands":
                result = await self.service.search_command(keyword.lower())
                if result:
                    found = True
                    products = result.get("products", [])
                    if result.get("product_info"):
                        for info in result["product_info"]:
                            if info.get("description"):
                                has_description = True
                                description_preview = info["description"][:100]
                                break
                    elif result.get("description"):
                        has_description = True
                        description_preview = result["description"][:100]

            elif kw_type == "error_codes":
                result = await self.service.search_error_code(keyword)
                if result:
                    found = True
                    has_description = bool(result.get("description"))
                    description_preview = result.get("description", "")[:100]

            elif kw_type == "terms":
                result = await self.service.search_glossary(keyword)
                if result:
                    found = True
                    has_description = bool(result.get("description"))
                    description_preview = result.get("description", "")[:100]

            elif kw_type in ("concepts", "configs"):
                # 개념/설정은 명령어나 용어 검색 시도
                result = await self.service.search_command(keyword.lower())
                if not result:
                    result = await self.service.search_glossary(keyword)
                if result:
                    found = True
                    has_description = bool(result.get("description"))
                    description_preview = (result.get("description") or "")[:100]

        except Exception as e:
            logger.debug(f"테스트 오류 ({keyword}): {e}")

        return TestResult(
            keyword=keyword,
            keyword_type=kw_type,
            found=found,
            products=products,
            has_description=has_description,
            description_preview=description_preview
        )

    async def run_validation(self, sample_size: int = 500) -> Dict[str, Any]:
        """검증 실행"""
        logger.info("=" * 60)
        logger.info("요약 시스템 검증 시작")
        logger.info("=" * 60)

        # 1. 키워드 로드
        logger.info("\n[1/4] 키워드 로드 중...")
        keywords = self.load_all_keywords()

        for kw_type, kws in keywords.items():
            logger.info(f"  - {kw_type}: {len(kws)}개")

        total_keywords = sum(len(kws) for kws in keywords.values())
        logger.info(f"  총 키워드: {total_keywords}개")

        # 2. 샘플링
        logger.info(f"\n[2/4] {sample_size}개 키워드 무작위 샘플링...")
        samples = self.sample_keywords(keywords, sample_size)

        sample_counts = defaultdict(int)
        for _, kw_type in samples:
            sample_counts[kw_type] += 1

        for kw_type, count in sample_counts.items():
            logger.info(f"  - {kw_type}: {count}개")

        # 3. 테스트 실행
        logger.info(f"\n[3/4] 검색 테스트 실행 중...")
        results = []
        for i, (keyword, kw_type) in enumerate(samples):
            if (i + 1) % 100 == 0:
                logger.info(f"  진행: {i + 1}/{len(samples)}")
            result = await self.test_keyword(keyword, kw_type)
            results.append(result)

        # 4. 결과 분석
        logger.info("\n[4/4] 결과 분석...")

        # 전체 통계
        total = len(results)
        found = sum(1 for r in results if r.found)
        with_desc = sum(1 for r in results if r.has_description)
        multi_product = sum(1 for r in results if len(r.products) > 1)

        # 타입별 통계
        type_stats = defaultdict(lambda: {"total": 0, "found": 0, "with_desc": 0})
        for r in results:
            type_stats[r.keyword_type]["total"] += 1
            if r.found:
                type_stats[r.keyword_type]["found"] += 1
            if r.has_description:
                type_stats[r.keyword_type]["with_desc"] += 1

        # 결과 출력
        logger.info("\n" + "=" * 60)
        logger.info("검증 결과")
        logger.info("=" * 60)

        logger.info(f"\n### 전체 통계")
        logger.info(f"  - 테스트 키워드: {total}개")
        logger.info(f"  - 검색 성공: {found}개 ({found/total*100:.1f}%)")
        logger.info(f"  - 설명 포함: {with_desc}개 ({with_desc/total*100:.1f}%)")
        logger.info(f"  - 멀티 제품: {multi_product}개")

        logger.info(f"\n### 타입별 검색 성공률")
        logger.info(f"  {'타입':<15} {'총계':>8} {'성공':>8} {'성공률':>10} {'설명포함':>10}")
        logger.info(f"  {'-'*15} {'-'*8} {'-'*8} {'-'*10} {'-'*10}")

        for kw_type in ["commands", "error_codes", "terms", "concepts", "configs"]:
            stats = type_stats[kw_type]
            if stats["total"] > 0:
                success_rate = stats["found"] / stats["total"] * 100
                desc_rate = stats["with_desc"] / stats["total"] * 100
                logger.info(f"  {kw_type:<15} {stats['total']:>8} {stats['found']:>8} {success_rate:>9.1f}% {desc_rate:>9.1f}%")

        # 실패 샘플 출력
        failed = [r for r in results if not r.found]
        if failed:
            logger.info(f"\n### 검색 실패 샘플 (상위 20개)")
            for r in failed[:20]:
                logger.info(f"  - [{r.keyword_type}] {r.keyword}")

        # 성공 샘플 출력
        success_samples = [r for r in results if r.found and r.has_description]
        if success_samples:
            logger.info(f"\n### 검색 성공 샘플 (상위 10개)")
            for r in random.sample(success_samples, min(10, len(success_samples))):
                products_str = f" ({', '.join(r.products)})" if r.products else ""
                logger.info(f"  - [{r.keyword_type}] {r.keyword}{products_str}")
                logger.info(f"    → {r.description_preview}...")

        return {
            "total": total,
            "found": found,
            "with_description": with_desc,
            "multi_product": multi_product,
            "success_rate": found / total * 100 if total > 0 else 0,
            "description_rate": with_desc / total * 100 if total > 0 else 0,
            "type_stats": dict(type_stats),
            "failed_samples": [{"keyword": r.keyword, "type": r.keyword_type} for r in failed[:50]],
        }


async def main():
    validator = SummaryValidator()
    results = await validator.run_validation(sample_size=500)

    # JSON 결과 저장
    output_path = Path("/opt/kms/uploads/summaries/validation_results.json")
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"\n결과 저장: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
