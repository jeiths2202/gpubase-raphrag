#!/usr/bin/env python3
"""
LLM 파서 종합 검증 테스트

다양한 패턴으로 추출 품질을 종합 검증합니다.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """테스트 케이스"""
    name: str
    category: str
    patterns: List[str]
    expected_min_count: int = 5
    description: str = ""
    priority: str = "medium"  # critical, high, medium, low
    examples: List[str] = field(default_factory=list)


@dataclass
class TestResult:
    """테스트 결과"""
    test_case: TestCase
    found_items: List[Dict[str, Any]] = field(default_factory=list)
    passed: bool = False
    message: str = ""


class ComprehensivePatternTester:
    """종합 패턴 테스터"""

    # ========================================
    # 테스트 케이스 정의 (카테고리별)
    # ========================================

    TEST_CASES = [
        # ============ CONFIG 패턴 ============
        TestCase(
            name="대문자_언더스코어 설정",
            category="config",
            patterns=[r"^[A-Z][A-Z0-9_]{3,}(?:_[A-Z0-9]+)+$"],
            expected_min_count=50,
            priority="critical",
            description="TJES_SPOOL_DIR, CHECK_DSAUTH_V2 형식",
            examples=["TJES_SPOOL_DIR", "CHECK_DSAUTH_V2", "OSC_REGION_NAME"]
        ),
        TestCase(
            name="단일 대문자 설정",
            category="config",
            patterns=[r"^[A-Z]{4,}$"],
            expected_min_count=20,
            priority="high",
            description="EDITOR, SETUID 형식",
            examples=["EDITOR", "SETUID", "ALIAS"]
        ),
        TestCase(
            name="디렉토리/경로 설정",
            category="config",
            patterns=[r"^[A-Z][A-Z0-9_]*(?:_DIR|_PATH|_HOME|_ROOT)$"],
            expected_min_count=20,
            priority="high",
            description="_DIR, _PATH 접미사 설정",
            examples=["OPENFRAME_HOME", "SPOOL_DIR", "LOG_PATH"]
        ),
        TestCase(
            name="크기/카운트 설정",
            category="config",
            patterns=[r"^[A-Z][A-Z0-9_]*(?:_SIZE|_COUNT|_MAX|_MIN|_LIMIT)$"],
            expected_min_count=15,
            priority="medium",
            description="크기/개수 관련 설정",
            examples=["BUF_SIZE", "MAX_COUNT", "RETRY_LIMIT"]
        ),
        TestCase(
            name="타임아웃/인터벌 설정",
            category="config",
            patterns=[r"^[A-Z][A-Z0-9_]*(?:_TIMEOUT|_INTERVAL|_WAIT|_DELAY)$"],
            expected_min_count=10,
            priority="medium",
            description="시간 관련 설정",
            examples=["CONN_TIMEOUT", "RETRY_INTERVAL", "POLL_WAIT"]
        ),
        TestCase(
            name="모드/타입 설정",
            category="config",
            patterns=[r"^[A-Z][A-Z0-9_]*(?:_MODE|_TYPE|_LEVEL|_FLAG)$"],
            expected_min_count=15,
            priority="medium",
            description="모드/타입 설정",
            examples=["LOG_LEVEL", "DEBUG_MODE", "AUTH_TYPE"]
        ),
        TestCase(
            name="포트/호스트 설정",
            category="config",
            patterns=[r"^[A-Z][A-Z0-9_]*(?:_PORT|_HOST|_ADDR|_IP)$"],
            expected_min_count=5,
            priority="medium",
            description="네트워크 설정",
            examples=["LISTEN_PORT", "DB_HOST", "SERVER_ADDR"]
        ),
        TestCase(
            name="인증/보안 설정",
            category="config",
            patterns=[r"^[A-Z][A-Z0-9_]*(?:_AUTH|_PASS|_KEY|_CERT|_SEC)"],
            expected_min_count=5,
            priority="medium",
            description="보안 관련 설정",
            examples=["TACF_AUTH", "DB_PASS", "SSL_CERT"]
        ),

        # ============ CONCEPT 패턴 ============
        TestCase(
            name="약어 (2-6자)",
            category="concept",
            patterns=[r"^[A-Z]{2,6}$"],
            expected_min_count=50,
            priority="critical",
            description="VSAM, PDS, JCL 같은 약어",
            examples=["VSAM", "PDS", "JCL", "CICS", "TACF"]
        ),
        TestCase(
            name="데이터 타입",
            category="concept",
            patterns=[r"(?i)^(BLOB|CLOB|VARCHAR|BINARY|COMP-\d|DECIMAL|INTEGER|CHAR|NUMERIC|FLOAT|DOUBLE|DATE|TIME|TIMESTAMP)$"],
            expected_min_count=5,
            priority="high",
            description="데이터베이스/COBOL 데이터 타입",
            examples=["BLOB", "VARCHAR", "COMP-3", "DECIMAL"]
        ),
        TestCase(
            name="SQL DDL 명령어",
            category="concept",
            patterns=[r"(?i)^(CREATE|ALTER|DROP|TRUNCATE)\s+(TABLE|INDEX|VIEW|SEQUENCE|TABLESPACE|DATABASE|USER|ROLE)"],
            expected_min_count=10,
            priority="high",
            description="DDL 명령어",
            examples=["CREATE TABLE", "ALTER INDEX", "DROP VIEW"]
        ),
        TestCase(
            name="SQL DML 명령어",
            category="concept",
            patterns=[r"(?i)^(SELECT|INSERT|UPDATE|DELETE|MERGE)\s"],
            expected_min_count=5,
            priority="medium",
            description="DML 명령어",
            examples=["SELECT", "INSERT INTO", "UPDATE"]
        ),
        TestCase(
            name="동작 모드",
            category="concept",
            patterns=[r"(?i)(Mode|Region|Phase|State|Status)$"],
            expected_min_count=10,
            priority="medium",
            description="시스템 동작 모드",
            examples=["Batch Mode", "Online Region", "Recovery Phase"]
        ),
        TestCase(
            name="아키텍처 컴포넌트",
            category="concept",
            patterns=[r"(?i)(Node|Cluster|Instance|Server|Client|Manager|Handler|Listener|Worker)$"],
            expected_min_count=10,
            priority="medium",
            description="시스템 아키텍처 컴포넌트",
            examples=["Master Node", "DB Cluster", "Connection Handler"]
        ),
        TestCase(
            name="데이터셋/파일 유형",
            category="concept",
            patterns=[r"(?i)^(PDS|PDSE|VSAM|KSDS|ESDS|RRDS|LDS|QSAM|BSAM|PS|PO)$"],
            expected_min_count=5,
            priority="high",
            description="메인프레임 데이터셋 유형",
            examples=["PDS", "VSAM", "KSDS", "QSAM"]
        ),
        TestCase(
            name="JCL 키워드",
            category="concept",
            patterns=[r"(?i)^(DD|JOB|EXEC|PROC|PEND|SET|IF|THEN|ELSE|ENDIF|INCLUDE|JCLLIB)$"],
            expected_min_count=5,
            priority="high",
            description="JCL 문장 키워드",
            examples=["DD", "JOB", "EXEC", "PROC"]
        ),
        TestCase(
            name="시스템 프로세스",
            category="concept",
            patterns=[
                r"(?i)^(DBWR|LGWR|PMON|SMON|CKPT|ARCH|RECO)",
                r"(?i)_(?:writer|reader|manager|scheduler|handler|daemon)$"
            ],
            expected_min_count=5,
            priority="medium",
            description="DB/시스템 백그라운드 프로세스",
            examples=["DBWR", "LGWR", "Log Writer"]
        ),
        TestCase(
            name="트랜잭션/락 개념",
            category="concept",
            patterns=[r"(?i)(Transaction|Commit|Rollback|Savepoint|Lock|Deadlock|Isolation|Concurrency)"],
            expected_min_count=5,
            priority="medium",
            description="트랜잭션 관련 개념",
            examples=["Transaction", "Commit", "Deadlock"]
        ),

        # ============ COMMAND 패턴 ============
        TestCase(
            name="초기화/부팅 명령어",
            category="command",
            patterns=[r"^[a-z]+(?:init|boot|start|up)$"],
            expected_min_count=15,
            priority="critical",
            description="시스템 시작 명령어",
            examples=["tjesinit", "oscboot", "tmboot"]
        ),
        TestCase(
            name="종료/다운 명령어",
            category="command",
            patterns=[r"^[a-z]+(?:down|stop|shutdown|kill)$"],
            expected_min_count=10,
            priority="critical",
            description="시스템 종료 명령어",
            examples=["oscdown", "tmdown", "shutdown"]
        ),
        TestCase(
            name="관리 도구",
            category="command",
            patterns=[r"^[a-z]+(?:mgr|adm|ctl|admin)$"],
            expected_min_count=15,
            priority="high",
            description="관리 유틸리티",
            examples=["tjesmgr", "tacfadm", "oscctl"]
        ),
        TestCase(
            name="데이터셋 유틸리티",
            category="command",
            patterns=[r"^(?:ds|idcams|iebgener|iebcopy|iefbr14|sort)[a-z]*$"],
            expected_min_count=10,
            priority="high",
            description="데이터셋 관리 유틸리티",
            examples=["dsmigin", "idcams", "iebcopy"]
        ),
        TestCase(
            name="컴파일러/번역기",
            category="command",
            patterns=[r"^(?:of|tb)?(?:cob|asm|pli|c\+\+|java)[a-z]*$"],
            expected_min_count=5,
            priority="medium",
            description="컴파일러/번역기",
            examples=["ofcob", "ofasm", "cobrun"]
        ),
        TestCase(
            name="마이그레이션 도구",
            category="command",
            patterns=[r"(?i)(migin|migout|convert|import|export|load|unload)"],
            expected_min_count=5,
            priority="medium",
            description="데이터 마이그레이션 도구",
            examples=["dsmigin", "tbimport", "tbexport"]
        ),
        TestCase(
            name="모니터링/진단 도구",
            category="command",
            patterns=[r"(?i)(monitor|stat|diag|trace|log|dump)"],
            expected_min_count=5,
            priority="medium",
            description="모니터링/진단 유틸리티",
            examples=["tjstat", "osctrace", "tbdiag"]
        ),

        # ============ API 패턴 ============
        TestCase(
            name="C 스타일 API",
            category="api",
            patterns=[r"^[a-z]{2,6}_[a-z_]+$"],
            expected_min_count=30,
            priority="critical",
            description="prefix_function 형식 API",
            examples=["tcfh_stow", "tfcd_read", "amsu_initialize"]
        ),
        TestCase(
            name="EXEC CICS 명령어",
            category="api",
            patterns=[r"(?i)^EXEC\s+CICS\s+[A-Z]+"],
            expected_min_count=10,
            priority="critical",
            description="CICS 트랜잭션 명령어",
            examples=["EXEC CICS READ", "EXEC CICS SEND", "EXEC CICS LINK"]
        ),
        TestCase(
            name="EXEC SQL 명령어",
            category="api",
            patterns=[r"(?i)^EXEC\s+SQL\s+[A-Z]+"],
            expected_min_count=5,
            priority="high",
            description="Embedded SQL 명령어",
            examples=["EXEC SQL SELECT", "EXEC SQL INSERT", "EXEC SQL FETCH"]
        ),
        TestCase(
            name="EXEC DLI 명령어",
            category="api",
            patterns=[r"(?i)^EXEC\s+DLI\s+[A-Z]+"],
            expected_min_count=3,
            priority="medium",
            description="IMS/DL/I 명령어",
            examples=["EXEC DLI GU", "EXEC DLI GN", "EXEC DLI ISRT"]
        ),
        TestCase(
            name="콜백/핸들러 함수",
            category="api",
            patterns=[r"(?i)(_callback|_handler|_hook|_listener)$"],
            expected_min_count=3,
            priority="low",
            description="이벤트 핸들러 함수",
            examples=["error_callback", "exit_handler"]
        ),

        # ============ ERROR_CODE 패턴 ============
        TestCase(
            name="음수 에러 코드 (4자리)",
            category="error_code",
            patterns=[r"^-\d{4}$"],
            expected_min_count=100,
            priority="critical",
            description="-5001, -5212 형식",
            examples=["-5001", "-5212", "-6001"]
        ),
        TestCase(
            name="음수 에러 코드 (5자리)",
            category="error_code",
            patterns=[r"^-\d{5}$"],
            expected_min_count=50,
            priority="critical",
            description="-21001, -63702 형식",
            examples=["-21001", "-26005", "-63702"]
        ),
        TestCase(
            name="시스템 ABEND (Sxxx)",
            category="error_code",
            patterns=[r"^S[0-9][0-9A-F]{2}$", r"^S[0-9]{3}$"],
            expected_min_count=10,
            priority="critical",
            description="S0C7, S322 형식",
            examples=["S0C7", "S0C4", "S322", "S806"]
        ),
        TestCase(
            name="사용자 ABEND (Uxxxx)",
            category="error_code",
            patterns=[r"^U[0-9]{4}$"],
            expected_min_count=5,
            priority="high",
            description="U4038, U0001 형식",
            examples=["U4038", "U0001", "U1001"]
        ),
        TestCase(
            name="모듈별 에러명",
            category="error_code",
            patterns=[r"^[A-Z]+_ERR_[A-Z_]+$"],
            expected_min_count=50,
            priority="high",
            description="DSALC_ERR_xxx 형식 에러명",
            examples=["DSALC_ERR_DATASET_NOT_FOUND", "TJES_ERR_INVALID_PARAM"]
        ),
        TestCase(
            name="SQL 에러 코드",
            category="error_code",
            patterns=[r"(?i)^SQLCODE\s*[-=]\s*\d+", r"^-[0-9]{3}$"],
            expected_min_count=5,
            priority="medium",
            description="SQLCODE 에러",
            examples=["SQLCODE -811", "SQLCODE -904"]
        ),

        # ============ JCL 패턴 ============
        TestCase(
            name="DD 파라미터",
            category="concept",
            patterns=[r"(?i)^(DSN|DISP|SPACE|DCB|UNIT|VOL|SYSOUT|DUMMY|RECFM|LRECL|BLKSIZE)$"],
            expected_min_count=10,
            priority="high",
            description="JCL DD 문 파라미터",
            examples=["DSN", "DISP", "SPACE", "DCB"]
        ),
        TestCase(
            name="JOB 파라미터",
            category="concept",
            patterns=[r"(?i)^(CLASS|MSGCLASS|MSGLEVEL|REGION|TIME|PRTY|NOTIFY|TYPRUN)$"],
            expected_min_count=5,
            priority="medium",
            description="JCL JOB 문 파라미터",
            examples=["CLASS", "MSGCLASS", "REGION", "TIME"]
        ),
        TestCase(
            name="EXEC 파라미터",
            category="concept",
            patterns=[r"(?i)^(PGM|PROC|PARM|COND|ACCT|ADDRSPC|DPRTY)$"],
            expected_min_count=5,
            priority="medium",
            description="JCL EXEC 문 파라미터",
            examples=["PGM", "PROC", "PARM", "COND"]
        ),

        # ============ 기타 패턴 ============
        TestCase(
            name="파일 확장자",
            category="concept",
            patterns=[r"(?i)\.(cob|cbl|asm|jcl|pli|cpy|mac|dat|ctl|cfg|conf|ini|xml|json)$"],
            expected_min_count=5,
            priority="low",
            description="OpenFrame 관련 파일 확장자",
            examples=[".cob", ".jcl", ".cpy", ".cfg"]
        ),
        TestCase(
            name="환경 변수",
            category="config",
            patterns=[r"^\$[A-Z][A-Z0-9_]+$", r"^\$\{[A-Z][A-Z0-9_]+\}$"],
            expected_min_count=5,
            priority="medium",
            description="환경 변수 참조",
            examples=["$OPENFRAME_HOME", "$TB_HOME", "${TJES_PATH}"]
        ),
        TestCase(
            name="시스템 메시지 ID",
            category="concept",
            patterns=[r"^[A-Z]{3,4}[0-9]{3,5}[A-Z]?$"],
            expected_min_count=10,
            priority="medium",
            description="시스템 메시지 ID",
            examples=["IEF142I", "IGD104I", "IKJ56220I"]
        ),
    ]

    def __init__(self, summaries_dir: Path):
        self.summaries_dir = summaries_dir
        self.index_path = summaries_dir / "index.json"
        self.items: List[Dict[str, Any]] = []

    def load_extracted_items(self) -> bool:
        """추출된 항목 로드 (모든 소스에서)"""
        try:
            # 1. index.json에서 로드
            if self.index_path.exists():
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                items_dict = data.get("items", {})
                for category, entries in items_dict.items():
                    if isinstance(entries, list):
                        for entry in entries:
                            if isinstance(entry, dict):
                                self.items.append(entry)

            # 2. error-codes 디렉토리에서 로드
            error_codes_dir = self.summaries_dir / "error-codes"
            if error_codes_dir.exists():
                for file in error_codes_dir.glob("*.md"):
                    if file.name == "index.md":
                        continue
                    content = file.read_text(encoding="utf-8")
                    # 에러 코드 추출
                    for match in re.finditer(r"###\s+([A-Z_]+)\s+\((-?\d{4,5})\)", content):
                        self.items.append({
                            "name": match.group(2),
                            "type": "error_code",
                            "description": match.group(1),
                        })
                    # ABEND 코드 추출
                    for match in re.finditer(r"###\s+([SU][0-9A-F]{2,4})\b", content):
                        self.items.append({
                            "name": match.group(1),
                            "type": "error_code",
                            "description": "ABEND",
                        })

            # 3. extracted_items.json에서 로드
            extracted_path = self.summaries_dir / "extracted_items.json"
            if extracted_path.exists():
                ext_data = json.loads(extracted_path.read_text(encoding="utf-8"))
                for item in ext_data.get("items", []):
                    if isinstance(item, dict):
                        self.items.append(item)

            # 4. commands 디렉토리에서 로드
            commands_dir = self.summaries_dir / "commands"
            if commands_dir.exists():
                for file in commands_dir.glob("*.md"):
                    if file.name == "index.md":
                        continue
                    content = file.read_text(encoding="utf-8")
                    for match in re.finditer(r"^## ([a-zA-Z][a-zA-Z0-9_-]+)", content, re.MULTILINE):
                        self.items.append({
                            "name": match.group(1),
                            "type": "command",
                        })

            # 5. glossary 디렉토리에서 로드
            glossary_dir = self.summaries_dir / "glossary"
            if glossary_dir.exists():
                for file in glossary_dir.glob("*.md"):
                    if file.name == "index.md":
                        continue
                    content = file.read_text(encoding="utf-8")
                    for match in re.finditer(r"^## ([A-Z][A-Z0-9_-]+)", content, re.MULTILINE):
                        self.items.append({
                            "name": match.group(1),
                            "type": "concept",
                        })

            logger.info(f"총 {len(self.items)}개 항목 로드됨")
            return True

        except Exception as e:
            logger.error(f"항목 로드 실패: {e}")
            return False

    def run_test_case(self, test_case: TestCase) -> TestResult:
        """단일 테스트 케이스 실행"""
        found_items = []

        for item in self.items:
            name = item.get("name", "")
            item_type = item.get("type", "")

            # 카테고리 매칭 (유연하게)
            category_match = (
                test_case.category == item_type or
                (test_case.category == "config" and item_type in ("config", "concept")) or
                (test_case.category == "concept" and item_type in ("concept", "term")) or
                (test_case.category == "error_code" and item_type in ("error_code", "error"))
            )

            if not category_match:
                continue

            # 패턴 매칭
            for pattern in test_case.patterns:
                try:
                    if re.search(pattern, name):
                        found_items.append({
                            "name": name,
                            "type": item_type,
                            "description": item.get("description", "")[:80],
                        })
                        break
                except re.error:
                    pass

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
        logger.info("LLM 파서 종합 검증 테스트")
        logger.info(f"테스트 시간: {datetime.now().isoformat()}")
        logger.info("=" * 70)

        if not self.load_extracted_items():
            return {"error": "항목 로드 실패"}

        results = []
        category_summary = defaultdict(lambda: {"total": 0, "passed": 0, "critical_passed": 0, "critical_total": 0})
        priority_summary = defaultdict(lambda: {"total": 0, "passed": 0})

        for test_case in self.TEST_CASES:
            result = self.run_test_case(test_case)
            results.append(result)

            # 카테고리별 집계
            category_summary[test_case.category]["total"] += 1
            if result.passed:
                category_summary[test_case.category]["passed"] += 1

            # 우선순위별 집계
            priority_summary[test_case.priority]["total"] += 1
            if result.passed:
                priority_summary[test_case.priority]["passed"] += 1

            # critical 항목 별도 집계
            if test_case.priority == "critical":
                category_summary[test_case.category]["critical_total"] += 1
                if result.passed:
                    category_summary[test_case.category]["critical_passed"] += 1

            # 결과 출력
            status = "✓" if result.passed else "✗"
            priority_mark = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(test_case.priority, "")
            logger.info(f"\n[{status}] {priority_mark} {test_case.name}")
            logger.info(f"    {result.message}")
            if result.found_items:
                samples = ", ".join([i["name"] for i in result.found_items[:5]])
                logger.info(f"    샘플: {samples}")

        # 종합 결과
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.passed)
        critical_tests = [r for r in results if r.test_case.priority == "critical"]
        critical_passed = sum(1 for r in critical_tests if r.passed)

        logger.info("\n" + "=" * 70)
        logger.info("종합 결과")
        logger.info("=" * 70)

        logger.info(f"\n📊 전체: {passed_tests}/{total_tests} 통과 ({passed_tests/total_tests*100:.1f}%)")
        logger.info(f"🔴 Critical: {critical_passed}/{len(critical_tests)} 통과 ({critical_passed/len(critical_tests)*100:.1f}%)")

        logger.info(f"\n📁 카테고리별:")
        for category in ["config", "concept", "command", "api", "error_code"]:
            stats = category_summary[category]
            if stats["total"] > 0:
                rate = stats["passed"] / stats["total"] * 100
                critical_info = ""
                if stats["critical_total"] > 0:
                    critical_rate = stats["critical_passed"] / stats["critical_total"] * 100
                    critical_info = f" (Critical: {stats['critical_passed']}/{stats['critical_total']})"
                logger.info(f"    {category}: {stats['passed']}/{stats['total']} ({rate:.0f}%){critical_info}")

        logger.info(f"\n⚡ 우선순위별:")
        for priority in ["critical", "high", "medium", "low"]:
            stats = priority_summary[priority]
            if stats["total"] > 0:
                rate = stats["passed"] / stats["total"] * 100
                mark = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(priority, "")
                logger.info(f"    {mark} {priority}: {stats['passed']}/{stats['total']} ({rate:.0f}%)")

        # 실패한 테스트
        failed_tests = [r for r in results if not r.passed]
        if failed_tests:
            logger.info(f"\n❌ 실패한 테스트 ({len(failed_tests)}개):")
            # 우선순위순 정렬
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            failed_tests.sort(key=lambda r: priority_order.get(r.test_case.priority, 4))
            for r in failed_tests:
                mark = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(r.test_case.priority, "")
                logger.info(f"    {mark} [{r.test_case.category}] {r.test_case.name}: {r.message}")
                if r.test_case.examples:
                    logger.info(f"       예시: {', '.join(r.test_case.examples[:3])}")

        return {
            "timestamp": datetime.now().isoformat(),
            "total_items_loaded": len(self.items),
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "pass_rate": passed_tests / total_tests * 100 if total_tests > 0 else 0,
            "critical_tests": len(critical_tests),
            "critical_passed": critical_passed,
            "critical_rate": critical_passed / len(critical_tests) * 100 if critical_tests else 0,
            "category_summary": {k: dict(v) for k, v in category_summary.items()},
            "priority_summary": {k: dict(v) for k, v in priority_summary.items()},
            "failed_tests": [
                {
                    "name": r.test_case.name,
                    "category": r.test_case.category,
                    "priority": r.test_case.priority,
                    "message": r.message,
                    "found_count": len(r.found_items),
                    "expected_min": r.test_case.expected_min_count,
                    "examples": r.test_case.examples,
                }
                for r in failed_tests
            ],
            "test_details": [
                {
                    "name": r.test_case.name,
                    "category": r.test_case.category,
                    "priority": r.test_case.priority,
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

    parser = argparse.ArgumentParser(description="종합 패턴 검증 테스트")
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
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="특정 카테고리만 테스트 (config, concept, command, api, error_code)"
    )

    args = parser.parse_args()

    tester = ComprehensivePatternTester(args.summaries_dir)

    # 특정 카테고리만 테스트
    if args.category:
        tester.TEST_CASES = [tc for tc in tester.TEST_CASES if tc.category == args.category]
        logger.info(f"카테고리 필터: {args.category} ({len(tester.TEST_CASES)}개 테스트)")

    results = tester.run_all_tests()

    if args.output:
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"\n결과 저장: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
