"""
LLM 기반 매뉴얼 파서

패턴 기반이 아닌 LLM을 사용하여 PDF 내용을 이해하고 구조화된 정보를 추출합니다.
"""

import json
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

import pymupdf
import httpx

logger = logging.getLogger(__name__)


@dataclass
class ExtractedItem:
    """추출된 항목"""
    name: str
    item_type: str  # command, config, api, concept, error_code
    description: str
    syntax: Optional[str] = None
    parameters: List[Dict[str, str]] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    source_file: str = ""
    source_page: int = 0
    product: str = ""


class LLMParser:
    """LLM 기반 매뉴얼 파서"""

    # 매뉴얼 유형 감지 패턴
    MANUAL_TYPE_PATTERNS = {
        "Configuration": "config",
        "Error": "error",
        "Command": "command",
        "Reference": "command",
        "Tool": "command",
        "Utility": "command",
        "Developer": "api",
        "Administrator": "concept",
        "User": "concept",
        "Guide": "concept",
    }

    # Configuration Guide 전용 프롬프트
    CONFIG_EXTRACTION_PROMPT = """당신은 OpenFrame/Tibero 설정 문서 분석 전문가입니다.
아래 PDF 페이지에서 **설정 파라미터(config)**를 중점적으로 추출해주세요.

## 설정 파라미터 패턴

1. **대문자_언더스코어 형식** (가장 흔함)
   - 예: TJES_SPOOL_DIR, OSC_REGION_NAME, TACF_AUTH
   - 예: CHECK_DSAUTH_V2, OVERRIDE_DSATTR, BUF_SIZE
   - 예: ACCOUNT_LOCK_PERIOD, ALIAS_LEVEL

2. **섹션 내 KEY=VALUE 형식**
   - [SECTION_NAME] 아래의 파라미터들
   - 예: [DATASET], [TJES], [BATCH] 섹션의 설정값

3. **환경변수 형식**
   - $OPENFRAME_HOME, $TB_HOME 등

4. **파라미터 테이블 형식**
   | 파라미터 | 설명 | 기본값 |
   위 형식의 테이블에서 파라미터 이름 추출

## 추출 형식

각 설정 파라미터에 대해:
- name: 파라미터 이름 (정확히)
- type: "config"
- description: 파라미터 설명
- syntax: 기본값이나 예시 값 (있으면)

## 중요

- 실제 페이지에 있는 설정 파라미터만 추출
- 설명이 있는 항목만 추출
- Copyright, 목차, 페이지 번호 등 제외

JSON 배열로 응답:

---
페이지 내용:
{page_content}
---

JSON 응답:"""

    # Concept/용어 전용 프롬프트
    CONCEPT_EXTRACTION_PROMPT = """당신은 OpenFrame/Tibero 기술 용어 분석 전문가입니다.
아래 PDF 페이지에서 **기술 용어/개념(concept)**을 중점적으로 추출해주세요.

## 추출 대상 개념 유형

1. **약어/기술용어**
   - VSAM, PDS, JCL, COBOL, TACF, TJES, CICS
   - TAC (Tibero Active Cluster), RAC, ASM

2. **데이터 타입/구조**
   - BLOB, CLOB, VARCHAR, COMP-3, BINARY
   - Tablespace, Index, Partition

3. **SQL/명령어 개념**
   - ALTER SESSION, DROP DISKSPACE, CREATE INDEX
   - COMMIT, ROLLBACK, SAVEPOINT

4. **동작 모드/아키텍처**
   - Local Mode, Remote Mode, Batch Mode
   - Online Region, Batch Region
   - Master Node, Slave Node

5. **시스템 내부 개념**
   - DBWR (Database Writer), LGWR (Log Writer)
   - Buffer Cache, Redo Log, Archive Log
   - Recovery, Checkpoint, Backup

6. **프로세스/서비스명**
   - osc_ofconfig, hidb_manager, tjes_scheduler

## 추출 형식

각 개념에 대해:
- name: 용어/개념 이름
- type: "concept"
- description: 개념 설명 (문서에서 추출)
- syntax: 관련 문법이나 사용법 (있으면)

## 중요

- 실제 설명이 있는 용어만 추출
- 단순 언급이나 목차 항목 제외
- Copyright, Note, Figure 등 메타 정보 제외

JSON 배열로 응답:

---
페이지 내용:
{page_content}
---

JSON 응답:"""

    # Error Reference Guide 전용 프롬프트
    ERROR_EXTRACTION_PROMPT = """당신은 OpenFrame/Tibero 에러 코드 분석 전문가입니다.
아래 PDF 페이지에서 **에러 코드(error_code)**를 추출해주세요.

## 에러 코드 유형

### 1. 음수 에러 코드 (가장 흔함)
- 형식: -XXXXX (4~5자리 음수)
- 예: -5001, -5212, -21001, -63702
- 보통 모듈명_ERR_설명 형태의 이름과 함께 나옴
- 예: DSALC_ERR_DATASET_NOT_FOUND (-5212)

### 2. ABEND 코드 (시스템 장애) - 매우 중요!
**반드시 추출해야 함:**
- **Sxxx 형식 (시스템 ABEND)**:
  - S001: I/O 오류
  - S013: 데이터셋 열기 오류
  - S0C1: Operation exception
  - S0C4: Protection exception (메모리 접근 위반)
  - S0C7: Data exception (숫자 변환 오류)
  - S222: 작업 취소
  - S322: 시간 초과
  - S806: 모듈 로드 실패
  - S913: 보안 오류
  - S0CB: 나눗셈 오류
- **Uxxxx 형식 (사용자 ABEND)**:
  - U0001, U0016, U1001, U4038, U4093
  - 애플리케이션에서 발생시킨 오류

### 3. 리턴 코드
- 형식: RC=XX, RETURN CODE XX
- 예: RC=4, RC=8, RC=12, RC=16

## 추출 형식

각 에러 코드에 대해:
- name: 에러 코드 (예: "-5212", "S0C7", "U4038")
- type: "error_code"
- description: 에러 설명/원인
- syntax: 대처 방법 (있으면)

## 중요

- 문서에 실제로 있는 에러 코드만 추출
- 설명이나 원인이 있는 항목만 추출
- Copyright, 목차 등 메타 정보 제외

JSON 배열로 응답:

---
페이지 내용:
{page_content}
---

JSON 응답:"""

    # Developer Guide 전용 프롬프트 (EXEC 명령어 중점)
    DEVELOPER_EXTRACTION_PROMPT = """당신은 OpenFrame/COBOL/CICS 프로그래밍 전문가입니다.
아래 PDF 페이지에서 **API 함수와 EXEC 명령어(api)**를 추출해주세요.

## 추출 대상

### 1. EXEC CICS 명령어 - 매우 중요!
CICS 트랜잭션 처리 명령어:
- **데이터 통신**: EXEC CICS SEND, EXEC CICS RECEIVE
- **파일 처리**: EXEC CICS READ, EXEC CICS WRITE, EXEC CICS REWRITE, EXEC CICS DELETE
- **브라우징**: EXEC CICS STARTBR, EXEC CICS READNEXT, EXEC CICS READPREV, EXEC CICS ENDBR
- **프로그램 제어**: EXEC CICS LINK, EXEC CICS XCTL, EXEC CICS RETURN
- **동기화**: EXEC CICS SYNCPOINT, EXEC CICS SYNCPOINT ROLLBACK
- **에러 처리**: EXEC CICS HANDLE CONDITION, EXEC CICS HANDLE ABEND
- **터미널**: EXEC CICS SEND MAP, EXEC CICS RECEIVE MAP
- **큐 처리**: EXEC CICS WRITEQ TD, EXEC CICS READQ TD, EXEC CICS WRITEQ TS, EXEC CICS READQ TS
- **기타**: EXEC CICS GETMAIN, EXEC CICS FREEMAIN, EXEC CICS ASKTIME

### 2. EXEC SQL 명령어
Embedded SQL 명령어:
- EXEC SQL SELECT, EXEC SQL INSERT, EXEC SQL UPDATE, EXEC SQL DELETE
- EXEC SQL FETCH, EXEC SQL OPEN, EXEC SQL CLOSE
- EXEC SQL DECLARE, EXEC SQL INCLUDE
- EXEC SQL COMMIT, EXEC SQL ROLLBACK

### 3. EXEC DLI 명령어
IMS/DL/I 데이터베이스 명령어:
- EXEC DLI GU, EXEC DLI GN, EXEC DLI GNP
- EXEC DLI ISRT, EXEC DLI DLET, EXEC DLI REPL

### 4. C/COBOL API 함수
- 형식: 함수명()
- 예: tcfh_stow(), tfcd_read(), tpalloc(), tpfree()

## 추출 형식

각 항목에 대해:
- name: 명령어/함수명 (예: "EXEC CICS READ", "tcfh_stow")
- type: "api"
- description: 기능 설명
- syntax: 전체 구문 (있으면)

## 중요

- 문서에 실제로 있는 내용만 추출
- EXEC 명령어는 "EXEC CICS READ" 형태로 전체 이름 사용
- Copyright, 목차 등 메타 정보 제외

JSON 배열로 응답:

---
페이지 내용:
{page_content}
---

JSON 응답:"""

    EXTRACTION_PROMPT = """당신은 OpenFrame/Tibero 기술 문서 분석 전문가입니다.
아래 PDF 페이지 내용에서 다음 항목들을 추출해주세요:

## 추출 대상 항목

### 1. 명령어/유틸리티 (command)
실행 가능한 CLI 도구, 쉘 명령어, 유틸리티 프로그램
- 예: tjesinit, oscboot, tjesmgr, tacfmgr, dsmigin, cobrun
- 예: hidb_init, ofcob, ofasm, OFManager, spfedit
- 예: INITLIST, INITRANS (JCL 문장/DD 파라미터도 포함)

### 2. API 함수 (api)
프로그래밍 인터페이스 함수 (C/COBOL/Java)
- 예: tcfh_stow(), tfcd_read(), tpalloc(), OSC_GET_MQ_HANDLE()
- **EXEC 명령어 (COBOL/CICS/SQL)**: 반드시 추출!
  - EXEC CICS SEND, EXEC CICS RECEIVE, EXEC CICS READ
  - EXEC CICS WRITE, EXEC CICS REWRITE, EXEC CICS DELETE
  - EXEC CICS LINK, EXEC CICS XCTL, EXEC CICS RETURN
  - EXEC CICS SYNCPOINT, EXEC CICS HANDLE
  - EXEC SQL SELECT, EXEC SQL INSERT, EXEC SQL UPDATE
  - EXEC SQL DELETE, EXEC SQL FETCH, EXEC SQL OPEN
  - EXEC DLI GU, EXEC DLI GN, EXEC DLI ISRT

### 3. 설정 파라미터 (config)
환경설정 변수, .conf 파일 파라미터, 시스템 설정값
**대문자+언더스코어 형식이 많음**
- 예: TJES_SPOOL_DIR, OSC_REGION_NAME, TACF_AUTH
- 예: DSNUTILB_EXIT, EDITOR, SETUID, SPARM_TIME
- 예: CHECK_DSAUTH_V2, OVERRIDE_DSATTR, BUF_SIZE
- 예: Q_NAME, SPOOL_VOLUME_SER, LIB_DIR, PGM_NAME
- 예: ACCOUNT_LOCK_PERIOD, ALIAS_LEVEL, ALIVE_INTERVAL
- .conf 파일의 [SECTION] 아래 KEY=VALUE 형식의 KEY들

### 4. 에러 코드 (error_code)
에러 번호와 설명 (음수 또는 양수)
- 예: -5212 (DSALC_ERR_DATASET_NOT_FOUND)
- 예: 21000, 63702 (모듈별 에러 코드)
- **ABEND 코드 (시스템 장애)**: 반드시 추출!
  - Sxxx 형식: S001, S013, S0C1, S0C4, S0C7, S222, S322, S806, S913
  - Uxxxx 형식: U0001, U0016, U1001, U4038, U4093
  - 시스템 ABEND: SOC7, S0C7, S0C4, S0C1, S322, S806
  - 사용자 ABEND: U0001, U4038

### 5. 개념/용어 (concept)
기술 용어, 아키텍처 개념, 동작 모드, 데이터 타입
**다양한 형태가 있음:**
- 약어/기술용어: VSAM, PDS, JCL, COBOL, TACF, TJES
- 데이터 타입: BLOB, CLOB, VARCHAR, COMP-3
- SQL/명령어: ALTER SESSION, DROP DISKSPACE, CREATE INDEX
- 동작 모드: Local Mode, Remote Mode, Batch Mode
- 아키텍처: Region, Node, Cluster, Tablespace
- 시스템 개념: DBWR_CNT, LOG_ON_MEMORY_SIZE, AUTO_COALESCE_INTERVAL
- 프로세스/서비스: icfspchk, osc_ofconfig, hidb_init

## 추출 형식

각 항목에 대해 다음 JSON 필드를 포함:
- name: 항목 이름 (정확히 문서에 나온 대로)
- type: command/api/config/error_code/concept
- description: 설명 (문서에서 추출, 1-2문장)
- syntax: 사용법이나 구문 (있는 경우만)

## 중요 규칙

1. **해당 페이지에 실제로 있는 내용만 추출** - 추측 금지
2. **설명이 있는 항목만 추출** - 단순 나열/목차 제외
3. **Copyright, Note, Example, Figure 등 메타 정보 제외**
4. **대문자_언더스코어 패턴은 config로 분류** (SOME_PARAM_NAME)
5. **함수() 형태는 api로 분류** (some_func())
6. **실행 도구/유틸리티는 command로 분류**

JSON 배열로 응답. 추출할 항목이 없으면 빈 배열 [] 반환.

---
페이지 내용:
{page_content}
---

JSON 응답:"""

    def __init__(
        self,
        manuals_dir: Path,
        llm_base_url: str = "http://qwen-graphrag:8000/v1",
        llm_model: str = "Qwen/Qwen2.5-7B-Instruct",
        batch_size: int = 5,
    ):
        self.manuals_dir = manuals_dir
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.batch_size = batch_size
        self.extracted_items: List[ExtractedItem] = []

    async def _call_llm(self, prompt: str) -> str:
        """LLM API 호출"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.llm_base_url}/chat/completions",
                    json={
                        "model": self.llm_model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 2000,
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"LLM 호출 실패: {e}")
                return "[]"

    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """LLM 응답 파싱"""
        try:
            # JSON 배열 추출
            start = response.find('[')
            end = response.rfind(']') + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.debug(f"JSON 파싱 실패: {e}")
        return []

    def _extract_platform_from_path(self, pdf_path: Path) -> str:
        """폴더 경로에서 플랫폼 추출 (MSP/MVS/VOS3/XSP)"""
        path_str = str(pdf_path)
        if "MSP_" in path_str or "/MSP/" in path_str:
            return "MSP"
        elif "MVS_" in path_str or "/MVS/" in path_str:
            return "MVS"
        elif "VOS3_" in path_str or "/VOS3/" in path_str:
            return "VOS3"
        elif "XSP_" in path_str or "/XSP/" in path_str:
            return "XSP"
        return ""

    def _extract_product_from_content(self, text: str, filename: str, pdf_path: Path = None) -> str:
        """PDF 내용에서 제품명 추출 (플랫폼 포함)"""
        import re

        # 플랫폼 추출
        platform = ""
        if pdf_path:
            platform = self._extract_platform_from_path(pdf_path)

        # 제품명 패턴
        product_patterns = [
            ("OpenFrame Common", r"OpenFrame\s+Common"),
            ("OpenFrame Batch", r"OpenFrame\s+Batch"),
            ("OpenFrame Base", r"OpenFrame\s+Base"),
            ("OpenFrame TACF", r"OpenFrame\s+TACF"),
            ("OpenFrame OSC", r"OpenFrame\s+OSC"),
            ("OpenFrame OSI", r"OpenFrame\s+OSI"),
            ("OpenFrame HiDB", r"OpenFrame\s+HiDB"),
            ("OpenFrame AIM", r"OpenFrame\s+AIM"),
            ("OpenFrame TJES", r"OpenFrame\s+TJES"),
            ("Tibero", r"Tibero\s+\d"),
            ("Tmax", r"Tmax\s+\d"),
        ]

        product = "OpenFrame"
        for prod_name, pattern in product_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                product = prod_name
                break
        else:
            # 파일명에서 추출 (폴백)
            if "Common" in filename:
                product = "OpenFrame Common"
            elif "Batch" in filename:
                product = "OpenFrame Batch"
            elif "Base" in filename:
                product = "OpenFrame Base"
            elif "TACF" in filename:
                product = "OpenFrame TACF"
            elif "OSC" in filename:
                product = "OpenFrame OSC"
            elif "TJES" in filename:
                product = "OpenFrame TJES"
            elif "Tibero" in filename:
                product = "Tibero"
            elif "Tmax" in filename:
                product = "Tmax"

        # 플랫폼이 있으면 제품명에 추가
        if platform:
            return f"{product} ({platform})"
        return product

    def _detect_manual_type(self, filename: str) -> str:
        """파일명에서 매뉴얼 유형 감지"""
        for pattern, manual_type in self.MANUAL_TYPE_PATTERNS.items():
            if pattern.lower() in filename.lower():
                return manual_type
        return "concept"

    def _has_config_pattern(self, text: str) -> bool:
        """텍스트에 설정 파라미터 패턴이 있는지 확인"""
        import re
        # 대문자_언더스코어 패턴이 3개 이상 있으면 config 페이지로 판단
        config_pattern = r'\b[A-Z][A-Z0-9_]{3,}(?:_[A-Z0-9]+)+\b'
        matches = re.findall(config_pattern, text)
        # 일반적인 단어 제외
        skip_words = {'COPYRIGHT', 'OPENFRAME', 'TMAX_SOFT', 'ALL_RIGHTS', 'RESERVED'}
        valid_matches = [m for m in matches if m not in skip_words]
        return len(valid_matches) >= 3

    def _has_exec_pattern(self, text: str) -> bool:
        """텍스트에 EXEC CICS/SQL/DLI 패턴이 있는지 확인"""
        import re
        # EXEC CICS, EXEC SQL, EXEC DLI 패턴
        exec_pattern = r'\bEXEC\s+(CICS|SQL|DLI)\s+[A-Z]+'
        matches = re.findall(exec_pattern, text, re.IGNORECASE)
        return len(matches) >= 2

    def _has_abend_pattern(self, text: str) -> bool:
        """텍스트에 ABEND 코드 패턴이 있는지 확인"""
        import re
        # Sxxx, S0Cx, Uxxxx 패턴
        abend_patterns = [
            r'\bS[0-9][0-9A-F]{2}\b',   # S001, S0C7, S013
            r'\bS[0-9]{3}\b',           # S222, S322, S806
            r'\bU[0-9]{4}\b',           # U0001, U4038
            r'\bABEND\s*[SU][0-9]',     # ABEND S0C7, ABEND U4038
        ]
        total_matches = 0
        for pattern in abend_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            total_matches += len(matches)
        return total_matches >= 2

    def _get_prompt_for_type(self, manual_type: str) -> str:
        """매뉴얼 유형에 맞는 프롬프트 반환"""
        if manual_type == "config":
            return self.CONFIG_EXTRACTION_PROMPT
        elif manual_type == "concept":
            return self.CONCEPT_EXTRACTION_PROMPT
        elif manual_type == "error":
            return self.ERROR_EXTRACTION_PROMPT
        elif manual_type == "api":
            return self.DEVELOPER_EXTRACTION_PROMPT
        else:
            return self.EXTRACTION_PROMPT

    async def parse_pdf(self, pdf_path: Path) -> List[ExtractedItem]:
        """PDF에서 LLM을 사용하여 정보 추출"""
        items = []
        filename = pdf_path.name

        # 매뉴얼 유형 감지
        manual_type = self._detect_manual_type(filename)
        logger.info(f"Parsing: {filename} (type={manual_type})")

        try:
            doc = pymupdf.open(pdf_path)

            # 첫 3페이지에서 제품명 추출
            first_pages = ""
            for i in range(min(3, len(doc))):
                first_pages += doc[i].get_text()
            product = self._extract_product_from_content(first_pages, filename, pdf_path)

            # 페이지별 처리 (배치로 묶어서)
            pages_text = []
            for page_num, page in enumerate(doc, 1):
                text = page.get_text()
                if text.strip() and len(text) > 100:  # 의미있는 내용이 있는 페이지만
                    pages_text.append((page_num, text))

            # 매뉴얼 유형에 맞는 프롬프트 선택
            primary_prompt = self._get_prompt_for_type(manual_type)

            # 배치 처리
            for i in range(0, len(pages_text), self.batch_size):
                batch = pages_text[i:i + self.batch_size]

                for page_num, text in batch:
                    # 텍스트 길이 제한 (토큰 제한)
                    truncated_text = text[:4000] if len(text) > 4000 else text

                    # 주 프롬프트로 추출
                    prompt = primary_prompt.format(page_content=truncated_text)
                    response = await self._call_llm(prompt)
                    extracted = self._parse_llm_response(response)

                    # Configuration Guide가 아닌 경우에도 config 패턴 감지하여 추가 추출
                    if manual_type != "config" and self._has_config_pattern(truncated_text):
                        config_prompt = self.CONFIG_EXTRACTION_PROMPT.format(page_content=truncated_text)
                        config_response = await self._call_llm(config_prompt)
                        config_extracted = self._parse_llm_response(config_response)
                        extracted.extend(config_extracted)

                    # EXEC CICS/SQL 패턴 감지하여 추가 추출
                    if manual_type != "api" and self._has_exec_pattern(truncated_text):
                        exec_prompt = self.DEVELOPER_EXTRACTION_PROMPT.format(page_content=truncated_text)
                        exec_response = await self._call_llm(exec_prompt)
                        exec_extracted = self._parse_llm_response(exec_response)
                        extracted.extend(exec_extracted)

                    # ABEND 코드 패턴 감지하여 추가 추출
                    if manual_type != "error" and self._has_abend_pattern(truncated_text):
                        abend_prompt = self.ERROR_EXTRACTION_PROMPT.format(page_content=truncated_text)
                        abend_response = await self._call_llm(abend_prompt)
                        abend_extracted = self._parse_llm_response(abend_response)
                        extracted.extend(abend_extracted)

                    for item_data in extracted:
                        # LLM이 중첩 배열을 반환하는 경우 처리
                        if isinstance(item_data, list):
                            for nested_item in item_data:
                                if isinstance(nested_item, dict) and nested_item.get("name"):
                                    items.append(ExtractedItem(
                                        name=nested_item.get("name", ""),
                                        item_type=nested_item.get("type", "concept"),
                                        description=nested_item.get("description", "")[:500],
                                        syntax=nested_item.get("syntax"),
                                        source_file=filename,
                                        source_page=page_num,
                                        product=product,
                                    ))
                            continue

                        if not isinstance(item_data, dict) or not item_data.get("name"):
                            continue

                        item = ExtractedItem(
                            name=item_data.get("name", ""),
                            item_type=item_data.get("type", "concept"),
                            description=item_data.get("description", "")[:500],
                            syntax=item_data.get("syntax"),
                            source_file=filename,
                            source_page=page_num,
                            product=product,
                        )
                        items.append(item)

                # 배치 간 딜레이
                await asyncio.sleep(0.5)

            doc.close()
            logger.info(f"  {filename}: {len(items)} items extracted")

        except Exception as e:
            logger.error(f"Failed to parse {filename}: {e}")

        return items

    async def process_all_manuals(self) -> List[ExtractedItem]:
        """모든 매뉴얼 처리"""
        all_items = []
        pdf_files = list(self.manuals_dir.rglob("*.pdf"))

        logger.info(f"Processing {len(pdf_files)} PDF files with LLM...")

        for pdf_path in pdf_files:
            items = await self.parse_pdf(pdf_path)
            all_items.extend(items)

        # 중복 제거 (같은 이름+타입+제품)
        unique_items = self._deduplicate_items(all_items)

        logger.info(f"Total: {len(unique_items)} unique items extracted")
        return unique_items

    def _deduplicate_items(self, items: List[ExtractedItem]) -> List[ExtractedItem]:
        """중복 항목 제거 (가장 긴 설명 유지)"""
        seen = {}
        for item in items:
            key = (item.name.lower(), item.item_type, item.product)
            if key not in seen or len(item.description) > len(seen[key].description):
                seen[key] = item
        return list(seen.values())


async def main():
    """테스트 실행"""
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    manuals_dir = Path("/opt/kms/uploads/manuals")
    parser = LLMParser(manuals_dir)

    # 단일 파일 테스트
    test_file = list(manuals_dir.rglob("*Dataset*Guide*.pdf"))
    if test_file:
        items = await parser.parse_pdf(test_file[0])
        print(f"\n추출된 항목 ({len(items)}개):")
        for item in items[:20]:
            print(f"  [{item.item_type}] {item.name}: {item.description[:80]}...")


if __name__ == "__main__":
    asyncio.run(main())
