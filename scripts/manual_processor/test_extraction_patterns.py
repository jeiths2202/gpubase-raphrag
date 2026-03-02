#!/usr/bin/env python3
"""
LLM 파서 추출 패턴 검증 테스트

개선된 프롬프트의 추출 품질을 다양한 패턴으로 검증합니다.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """테스트 케이스"""
    name: str
    category: str  # config, concept, command, api, error_code
    patterns: List[str]  # 검색할 패턴들
    expected_min_count: int = 5  # 최소 기대 추출 수
    description: str = ""


@dataclass
class TestResult:
    """테스트 결과"""
    test_case: TestCase
    found_items: List[Dict[str, Any]] = field(default_factory=list)
    passed: bool = False
    message: str = ""


class ExtractionPatternTester:
    """추출 패턴 테스터"""

    # 검증 테스트 케이스 정의
    TEST_CASES = [
        # === CONFIG 패턴 테스트 ===
        TestCase(
            name="대문자_언더스코어 설정 파라미터",
            category="config",
            patterns=[
                r"^[A-Z][A-Z0-9_]{3,}(?:_[A-Z0-9]+)+$",  # TJES_SPOOL_DIR 형식
            ],
            expected_min_count=50,
            description="TJES_SPOOL_DIR, CHECK_DSAUTH_V2 형식의 설정 파라미터"
        ),
        TestCase(
            name="단일 단어 대문자 설정",
            category="config",
            patterns=[
                r"^[A-Z]{4,}$",  # EDITOR, SETUID 형식
            ],
            expected_min_count=20,
            description="EDITOR, SETUID, ALIAS 같은 단일 단어 설정"
        ),
        TestCase(
            name="섹션 설정 파라미터",
            category="config",
            patterns=[
                r"^[A-Z][A-Z0-9_]*(?:_DIR|_PATH|_SIZE|_COUNT|_LEVEL|_MODE|_TYPE)$",
            ],
            expected_min_count=30,
            description="_DIR, _PATH, _SIZE 등 접미사가 있는 설정"
        ),

        # === CONCEPT 패턴 테스트 ===
        TestCase(
            name="약어/기술용어",
            category="concept",
            patterns=[
                r"^[A-Z]{2,6}$",  # VSAM, PDS, JCL, TAC
            ],
            expected_min_count=30,
            description="VSAM, PDS, JCL 같은 약어"
        ),
        TestCase(
            name="데이터 타입",
            category="concept",
            patterns=[
                r"(?i)^(BLOB|CLOB|VARCHAR|BINARY|COMP-\d|DECIMAL|INTEGER|CHAR)$",
            ],
            expected_min_count=5,
            description="BLOB, CLOB, VARCHAR 등 데이터 타입"
        ),
        TestCase(
            name="SQL 명령어/개념",
            category="concept",
            patterns=[
                r"(?i)^(ALTER|CREATE|DROP|SELECT|INSERT|UPDATE|DELETE)\s+[A-Z]+$",
            ],
            expected_min_count=10,
            description="ALTER SESSION, CREATE INDEX 등 SQL 명령어"
        ),
        TestCase(
            name="동작 모드",
            category="concept",
            patterns=[
                r"(?i)(Mode|Region|Node|Cluster|Phase)$",
            ],
            expected_min_count=10,
            description="Local Mode, Batch Region 등 동작 모드"
        ),
        TestCase(
            name="시스템 프로세스/컴포넌트",
            category="concept",
            patterns=[
                r"(?i)^(DBWR|LGWR|PMON|SMON|CKPT|ARCH)",  # Oracle/Tibero 프로세스
                r"(?i)_(?:writer|reader|manager|scheduler|handler)$",
            ],
            expected_min_count=5,
            description="DBWR, LGWR 같은 시스템 프로세스"
        ),

        # === COMMAND 패턴 테스트 ===
        TestCase(
            name="소문자 명령어 (init/boot/down)",
            category="command",
            patterns=[
                r"^[a-z]+(?:init|boot|down|start|stop|run)$",
            ],
            expected_min_count=20,
            description="tjesinit, oscboot 같은 명령어"
        ),
        TestCase(
            name="관리 명령어 (mgr/adm/ctl)",
            category="command",
            patterns=[
                r"^[a-z]+(?:mgr|adm|ctl|cmd)$",
            ],
            expected_min_count=15,
            description="tjesmgr, tacfadm 같은 관리 도구"
        ),
        TestCase(
            name="유틸리티 명령어",
            category="command",
            patterns=[
                r"^(?:ds|of|tb|tmax)[a-z]+$",  # dsmigin, ofcob, tbimport
            ],
            expected_min_count=20,
            description="dsmigin, ofcob 같은 유틸리티"
        ),

        # === API 패턴 테스트 ===
        TestCase(
            name="C 스타일 API 함수",
            category="api",
            patterns=[
                r"^[a-z]{2,6}_[a-z_]+$",  # tcfh_stow, tfcd_read
            ],
            expected_min_count=30,
            description="tcfh_stow, tfcd_read 형식의 API"
        ),
        TestCase(
            name="EXEC 명령어",
            category="api",
            patterns=[
                r"(?i)^EXEC\s+(CICS|SQL|DLI)",
            ],
            expected_min_count=5,
            description="EXEC CICS, EXEC SQL 명령어"
        ),

        # === ERROR_CODE 패턴 테스트 ===
        TestCase(
            name="음수 에러 코드",
            category="error_code",
            patterns=[
                r"^-\d{4,5}$",  # -5212, -21001
            ],
            expected_min_count=100,
            description="-5212, -21001 형식의 에러 코드"
        ),
        TestCase(
            name="ABEND 코드",
            category="error_code",
            patterns=[
                r"^[SU]\d{3,4}$",  # S0C7, U4038
                r"^S[0-9A-F]{2,3}$",  # S22, S0C7
            ],
            expected_min_count=10,
            description="S22, S0C7, U4038 같은 ABEND 코드"
        ),
    ]

    def __init__(self, summaries_dir: Path):
        self.summaries_dir = summaries_dir
        self.index_path = summaries_dir / "index.json"
        self.items: List[Dict[str, Any]] = []

    def load_extracted_items(self) -> bool:
        """추출된 항목 로드"""
        if not self.index_path.exists():
            logger.error(f"인덱스 파일 없음: {self.index_path}")
            return False

        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            items_dict = data.get("items", {})

            # 플랫 리스트로 변환
            for category, entries in items_dict.items():
                if isinstance(entries, list):
                    for entry in entries:
                        if isinstance(entry, dict):
                            self.items.append(entry)

            # 에러 코드 디렉토리에서 추가 로드
            error_codes_dir = self.summaries_dir / "error-codes"
            if error_codes_dir.exists():
                for file in error_codes_dir.glob("*.md"):
                    if file.name == "index.md":
                        continue
                    content = file.read_text(encoding="utf-8")
                    # ### NAME (-XXXXX) 형식 또는 ### NAME (XXXXX) 형식
                    for match in re.finditer(r"###\s+([A-Z_]+)\s+\((-?\d{4,5})\)", content):
                        name = match.group(1)
                        code = match.group(2)
                        self.items.append({
                            "name": code,
                            "type": "error_code",
                            "description": name,
                            "source": file.name,
                        })

            # extracted_items.json에서도 로드 (LLM 추출 결과)
            extracted_path = self.summaries_dir / "extracted_items.json"
            if extracted_path.exists():
                try:
                    ext_data = json.loads(extracted_path.read_text(encoding="utf-8"))
                    for item in ext_data.get("items", []):
                        if isinstance(item, dict):
                            self.items.append(item)
                except Exception:
                    pass

            logger.info(f"총 {len(self.items)}개 항목 로드됨")
            return True

        except Exception as e:
            logger.error(f"인덱스 로드 실패: {e}")
            return False

    def run_test_case(self, test_case: TestCase) -> TestResult:
        """단일 테스트 케이스 실행"""
        found_items = []

        for item in self.items:
            name = item.get("name", "")
            item_type = item.get("type", "")

            # 카테고리 매칭 (느슨한 매칭)
            category_match = (
                test_case.category == item_type or
                (test_case.category == "config" and item_type in ("config", "concept")) or
                (test_case.category == "concept" and item_type in ("concept", "term"))
            )

            if not category_match:
                continue

            # 패턴 매칭
            for pattern in test_case.patterns:
                if re.search(pattern, name):
                    found_items.append({
                        "name": name,
                        "type": item_type,
                        "description": item.get("description", "")[:100],
                        "product": item.get("product", ""),
                    })
                    break

        # 중복 제거
        seen = set()
        unique_items = []
        for item in found_items:
            if item["name"] not in seen:
                seen.add(item["name"])
                unique_items.append(item)

        passed = len(unique_items) >= test_case.expected_min_count
        message = f"발견: {len(unique_items)}개 (기대: {test_case.expected_min_count}+)"

        return TestResult(
            test_case=test_case,
            found_items=unique_items,
            passed=passed,
            message=message
        )

    def run_all_tests(self) -> Dict[str, Any]:
        """모든 테스트 실행"""
        logger.info("=" * 70)
        logger.info("LLM 파서 추출 패턴 검증 테스트")
        logger.info("=" * 70)

        if not self.load_extracted_items():
            return {"error": "항목 로드 실패"}

        results = []
        category_summary = defaultdict(lambda: {"total": 0, "passed": 0})

        for test_case in self.TEST_CASES:
            result = self.run_test_case(test_case)
            results.append(result)

            category_summary[test_case.category]["total"] += 1
            if result.passed:
                category_summary[test_case.category]["passed"] += 1

            status = "✓ PASS" if result.passed else "✗ FAIL"
            logger.info(f"\n[{status}] {test_case.name}")
            logger.info(f"  카테고리: {test_case.category}")
            logger.info(f"  {result.message}")

            if result.found_items:
                logger.info(f"  샘플: {', '.join([i['name'] for i in result.found_items[:5]])}")

        # 종합 결과
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.passed)

        logger.info("\n" + "=" * 70)
        logger.info("종합 결과")
        logger.info("=" * 70)

        logger.info(f"\n전체: {passed_tests}/{total_tests} 테스트 통과 ({passed_tests/total_tests*100:.1f}%)")

        logger.info(f"\n카테고리별 결과:")
        for category, stats in category_summary.items():
            rate = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
            logger.info(f"  {category}: {stats['passed']}/{stats['total']} ({rate:.0f}%)")

        # 실패한 테스트 상세
        failed_tests = [r for r in results if not r.passed]
        if failed_tests:
            logger.info(f"\n실패한 테스트 ({len(failed_tests)}개):")
            for r in failed_tests:
                logger.info(f"  - {r.test_case.name}: {r.message}")
                logger.info(f"    설명: {r.test_case.description}")

        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "pass_rate": passed_tests / total_tests * 100 if total_tests > 0 else 0,
            "category_summary": dict(category_summary),
            "failed_tests": [
                {
                    "name": r.test_case.name,
                    "category": r.test_case.category,
                    "message": r.message,
                    "found_count": len(r.found_items),
                    "expected_min": r.test_case.expected_min_count,
                }
                for r in failed_tests
            ],
            "details": [
                {
                    "name": r.test_case.name,
                    "category": r.test_case.category,
                    "passed": r.passed,
                    "found_count": len(r.found_items),
                    "expected_min": r.test_case.expected_min_count,
                    "samples": [i["name"] for i in r.found_items[:10]],
                }
                for r in results
            ]
        }


async def main():
    """메인 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="추출 패턴 검증 테스트")
    parser.add_argument(
        "--summaries-dir",
        type=Path,
        default=Path("/opt/kms/uploads/summaries"),
        help="요약 디렉토리"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="결과 JSON 출력 경로"
    )

    args = parser.parse_args()

    tester = ExtractionPatternTester(args.summaries_dir)
    results = tester.run_all_tests()

    if args.output:
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"\n결과 저장: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
