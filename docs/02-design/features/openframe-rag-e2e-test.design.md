# Design: OpenFrame RAG E2E 테스트

> **Feature**: openframe-rag-e2e-test
> **Plan Reference**: `docs/01-plan/features/openframe-rag-e2e-test.plan.md`
> **Created**: 2026-01-31
> **Status**: Design Phase

## 1. 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│                    E2E Test Runner                          │
│                  (e2e_openframe_rag.js)                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Login     │→ │  Navigate   │→ │   Test Executor     │  │
│  │   Module    │  │  Module     │  │   (Loop)            │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│                                            │                │
│                    ┌───────────────────────┼───────────────┐│
│                    ▼                       ▼               ▼│
│            ┌─────────────┐      ┌─────────────┐  ┌────────┐│
│            │ Query Input │      │  Response   │  │ Result ││
│            │ + Product   │      │  Analyzer   │  │ Writer ││
│            │   Select    │      │ (Halluc.)   │  │ (JSON) ││
│            └─────────────┘      └─────────────┘  └────────┘│
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              OpenFrame RAG Page                             │
│           https://localhost:3000/openframe-rag              │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Product      │  │  Chat        │  │  Response        │   │
│  │ Selector     │  │  Input       │  │  Display         │   │
│  │ (Dropdown)   │  │  (Textarea)  │  │  (Markdown)      │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│  ┌──────────────┐  ┌──────────────────────────────────────┐ │
│  │ DeepSeek     │  │  Product Selection Modal             │ │
│  │ Toggle       │  │  (8 products + other)                │ │
│  └──────────────┘  └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 2. 테스트 케이스 정의

### 2.1 TEST_CASES 배열 구조

```javascript
const TEST_CASES = [
  {
    id: 'TC-001',
    keyword: 'tjesmgr',
    query: 'tjesmgrについて説明してください。',
    lang: 'ja',
    product: 'openframe_mvs',      // 기대되는 제품
    expected: ['tjesmgr', 'TJES'], // 응답에 포함되어야 할 키워드
    notExpected: ['tibero', 'tmax'], // Hallucination 감지용
    category: 'command'
  },
  // ... more test cases
];
```

### 2.2 전체 테스트 케이스 (45개)

#### OpenFrame MVS (15개)
| ID | 키워드 | 쿼리 | 언어 | 기대 키워드 | 금지 키워드 |
|----|--------|------|------|------------|------------|
| TC-001 | tjesmgr | tjesmgrについて説明してください | ja | tjesmgr, TJES | tibero, tmax |
| TC-002 | tacfmgr | tacfmgrの使用方法を教えてください | ja | tacfmgr, TACF | hidbmgr |
| TC-003 | hidbmgr | hidbmgrコマンドの機能について | ja | hidbmgr, HiDB | ndbmgr |
| TC-004 | oscmgr | oscmgrコマンドについて | ja | oscmgr, OSC | tjesmgr |
| TC-005 | osimgr | osimgrの機能と使い方 | ja | osimgr, OSI | oscmgr |
| TC-006 | idcams | idcamsユーティリティについて | ja | idcams, VSAM | - |
| TC-007 | iebgener | iebgenerの使用方法 | ja | iebgener | iebcopy |
| TC-008 | iebcopy | iebcopyユーティリティの機能 | ja | iebcopy, PDS | iebgener |
| TC-009 | ABEND S0C7 | ABEND S0C7エラーの原因 | ja | S0C7, data | S0C4 |
| TC-010 | ABEND S0C4 | ABEND S0C4エラーについて | ja | S0C4, protection | S0C7 |
| TC-011 | tjes.conf | tjes.confの設定項目 | ja | tjes.conf, TJES | osc.conf |
| TC-012 | osc.conf | osc.confの設定方法 | ja | osc.conf, OSC | tjes.conf |
| TC-013 | JCL | JCLの基本構文について | ja | JCL, JOB, EXEC | - |
| TC-014 | VSAM KSDS | VSAM KSDSについて | ja | KSDS, key | ESDS |
| TC-015 | GDG | GDG世代データグループについて | ja | GDG, generation | - |

#### Tibero (8개)
| ID | 키워드 | 쿼리 | 언어 | 기대 키워드 | 금지 키워드 |
|----|--------|------|------|------------|------------|
| TC-016 | tbboot | tbbootコマンドについて | ja | tbboot, Tibero | tmboot |
| TC-017 | tbdown | tbdownの使用方法 | ja | tbdown, shutdown | tmdown |
| TC-018 | tbsql | tbsqlの機能について | ja | tbsql, SQL | - |
| TC-019 | tablespace | Tibero tablespace 생성 | ko | tablespace, CREATE | - |
| TC-020 | TAC | Tibero TAC 클러스터 | ko | TAC, cluster | - |
| TC-021 | TAS | Tibero TAS 구성 | ko | TAS, Active | - |
| TC-022 | TSC | Tibero TSC 백업 | ko | TSC, backup | - |
| TC-023 | tbrmgr | tbrmgr 사용법 | ko | tbrmgr, recovery | - |

#### Tmax (7개)
| ID | 키워드 | 쿼리 | 언어 | 기대 키워드 | 금지 키워드 |
|----|--------|------|------|------------|------------|
| TC-024 | tmboot | tmbootコマンドについて | ja | tmboot, boot | tbboot |
| TC-025 | tmdown | tmdownの使用方法 | ja | tmdown, shutdown | tbdown |
| TC-026 | tmadmin | tmadminの機能 | ja | tmadmin, admin | - |
| TC-027 | tuxedo | Tuxedo互換性について | ja | tuxedo, Tmax | - |
| TC-028 | UCS | Tmax UCS設定 | ja | UCS, Unicode | - |
| TC-029 | RQ | Tmax RQ 구성 | ko | RQ, queue | - |
| TC-030 | CLH | Tmax CLH 설정 | ko | CLH, handler | - |

#### OFASM (5개)
| ID | 키워드 | 쿼리 | 언어 | 기대 키워드 | 금지 키워드 |
|----|--------|------|------|------------|------------|
| TC-031 | ofasm | OFASMについて | ja | OFASM, assembler | OFCOBOL |
| TC-032 | asmmgr | asmmgrの使用方法 | ja | asmmgr, macro | - |
| TC-033 | MACRO | OFASMマクロについて | ja | MACRO, macro | - |
| TC-034 | CSECT | CSECT정의 방법 | ko | CSECT, section | - |
| TC-035 | DSECT | DSECT 사용법 | ko | DSECT, dummy | - |

#### OFCOBOL (5개)
| ID | 키워드 | 쿼리 | 언어 | 기대 키워드 | 금지 키워드 |
|----|--------|------|------|------------|------------|
| TC-036 | ofcobol | OFCOBOLについて | ja | OFCOBOL, COBOL | OFASM |
| TC-037 | cobmgr | cobmgrの機能 | ja | cobmgr, compile | - |
| TC-038 | COPYBOOK | COPYBOOK使用方法 | ja | COPYBOOK, copy | - |
| TC-039 | CICS | OFCOBOL CICS연동 | ko | CICS, online | - |
| TC-040 | DB2 | OFCOBOL DB2연동 | ko | DB2, database | - |

#### 기타 제품 (5개)
| ID | 키워드 | 쿼리 | 언어 | 기대 키워드 | 금지 키워드 |
|----|--------|------|------|------------|------------|
| TC-041 | MSP | MSP OpenFrameについて | ja | MSP, OpenFrame | VOS3 |
| TC-042 | VOS3 | VOS3 OpenFrameについて | ja | VOS3, OpenFrame | MSP |
| TC-043 | XSP | XSP OpenFrameについて | ja | XSP, OpenFrame | - |
| TC-044 | ofboot | ofbootコマンドについて | ja | ofboot, OpenFrame | ofdown |
| TC-045 | ofdown | ofdownについて | ja | ofdown, shutdown | ofboot |

## 3. 핵심 함수 설계

### 3.1 analyzeResponse()

```javascript
/**
 * 응답 분석 및 Hallucination 감지
 * @param {Object} testCase - 테스트 케이스
 * @param {string} responseText - AI 응답 텍스트
 * @returns {Object} 분석 결과
 */
function analyzeResponse(testCase, responseText) {
  const responseLower = responseText.toLowerCase();

  // 기대 키워드 확인
  const foundExpected = testCase.expected.filter(exp =>
    responseLower.includes(exp.toLowerCase())
  );

  // Hallucination 감지 (금지 키워드)
  const foundUnexpected = testCase.notExpected.filter(unexp =>
    responseLower.includes(unexp.toLowerCase())
  );

  // "정보 없음" 응답 감지
  const isNoResult = /見つかりません|情報がありません|찾을 수 없습니다/.test(responseText);

  return {
    foundExpected,
    foundUnexpected,
    isNoResult,
    hasHallucination: foundUnexpected.length > 0,
    hasRelevantContent: foundExpected.length > 0,
    isPass: foundUnexpected.length === 0 && (foundExpected.length > 0 || isNoResult)
  };
}
```

### 3.2 runTest()

```javascript
/**
 * 단일 테스트 케이스 실행
 * @param {Page} page - Playwright 페이지
 * @param {Object} testCase - 테스트 케이스
 * @param {number} index - 테스트 인덱스
 */
async function runTest(page, testCase, index) {
  console.log(`[${index}/${TEST_CASES.length}] Testing: "${testCase.keyword}"`);

  try {
    // 1. 새 대화 시작 (이전 컨텍스트 격리)
    await startNewChat(page);

    // 2. 제품 선택 (auto가 아닌 경우)
    if (testCase.product !== 'auto') {
      await selectProduct(page, testCase.product);
    }

    // 3. 쿼리 입력
    await page.locator('textarea').fill(testCase.query);
    await page.locator('textarea').press('Enter');

    // 4. 응답 대기 (SSE 스트리밍)
    await page.waitForTimeout(25000);

    // 5. 제품 선택 모달 처리
    await handleProductModal(page, testCase.product);

    // 6. 응답 텍스트 추출
    const responseText = await extractLatestResponse(page);

    // 7. 분석
    const analysis = analyzeResponse(testCase, responseText);

    // 8. 결과 기록
    recordResult(testCase, analysis, index);

  } catch (error) {
    recordError(testCase, error, index);
  }
}
```

### 3.3 handleProductModal()

```javascript
/**
 * 제품 선택 모달 처리
 * @param {Page} page - Playwright 페이지
 * @param {string} targetProduct - 선택할 제품
 */
async function handleProductModal(page, targetProduct) {
  const modal = page.locator('.openframe-modal');

  if (await modal.count() > 0) {
    // 모달이 표시된 경우
    const productBtn = page.locator(
      `.openframe-product-option:has-text("${getProductDisplayName(targetProduct)}")`
    );

    if (await productBtn.count() > 0) {
      await productBtn.click();
      await page.waitForTimeout(2000);
    }
  }
}
```

### 3.4 extractLatestResponse()

```javascript
/**
 * 최신 AI 응답만 추출 (Hallucination 오탐 방지)
 * @param {Page} page - Playwright 페이지
 * @returns {string} 응답 텍스트
 */
async function extractLatestResponse(page) {
  // 방법 1: assistant 클래스 메시지의 마지막 항목
  const assistantMessages = await page.locator(
    '.openagent-message.assistant .openagent-message-content'
  ).all();

  if (assistantMessages.length > 0) {
    return await assistantMessages[assistantMessages.length - 1].textContent();
  }

  // 방법 2: 폴백 - 전체 채팅 영역
  return await page.locator('.openagent-messages').textContent();
}
```

## 4. UI 셀렉터 매핑

| 요소 | CSS 셀렉터 | 용도 |
|------|-----------|------|
| 채팅 입력 | `textarea` | 쿼리 입력 |
| 전송 버튼 | `.openagent-btn-send` | 메시지 전송 |
| 제품 드롭다운 | `.openframe-product-selector select` | 제품 선택 |
| DeepSeek 버튼 | `.openframe-deepseek-btn` | DeepSeek 모드 |
| 제품 선택 모달 | `.openframe-modal` | 제품 확인 모달 |
| 제품 옵션 버튼 | `.openframe-product-option` | 모달 내 제품 버튼 |
| 응답 메시지 | `.openagent-message.assistant` | AI 응답 |
| 로딩 인디케이터 | `.openagent-message.loading` | 로딩 상태 |
| 에러 표시 | `.openagent-error` | 에러 메시지 |
| 새 채팅 버튼 | `button:has-text("新規"), button svg[class*="trash"]` | 대화 초기화 |

## 5. 결과 데이터 구조

### 5.1 results 객체

```javascript
const results = {
  timestamp: "2026-01-31T10:00:00.000Z",
  total: 45,
  passed: 38,
  failed: 7,
  passRate: 84.4,

  hallucinations: [
    {
      index: 5,
      id: "TC-005",
      keyword: "osimgr",
      query: "osimgrの機能と使い方",
      foundUnexpected: ["oscmgr"],
      screenshot: "hallucination_5_osimgr.png"
    }
  ],

  noResults: [
    {
      index: 23,
      id: "TC-023",
      keyword: "tbrmgr",
      query: "tbrmgr 사용법"
    }
  ],

  errors: [
    {
      index: 30,
      id: "TC-030",
      keyword: "CLH",
      error: "Timeout waiting for response"
    }
  ],

  details: [
    {
      id: "TC-001",
      keyword: "tjesmgr",
      status: "passed",
      foundExpected: ["tjesmgr", "TJES"],
      responseTime: 12500
    }
  ]
};
```

### 5.2 출력 파일

| 파일 | 내용 |
|------|------|
| `openframe_rag_results.json` | 전체 테스트 결과 |
| `hallucination_*.png` | Hallucination 발생 시 스크린샷 |
| `test_summary.txt` | 콘솔 요약 (선택사항) |

## 6. 실행 흐름

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 브라우저 시작 (Chromium headless)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. 로그인                                                    │
│    - URL: https://localhost:3000/login                      │
│    - 계정: admin / SecureAdm1nP@ss2024!                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. OpenFrame RAG 페이지 네비게이션                           │
│    - URL: https://localhost:3000/openframe-rag              │
│    - Health 상태 확인                                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. 테스트 루프 (45개 케이스)                                 │
│    for (testCase in TEST_CASES) {                           │
│      - 새 대화 시작                                          │
│      - 쿼리 입력 → 응답 대기 → 분석                          │
│      - 10개마다 중간 결과 저장                               │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. 결과 저장 및 요약 출력                                    │
│    - openframe_rag_results.json                             │
│    - 콘솔 요약 (Pass/Fail/Hallucination 수)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. 브라우저 종료                                             │
└─────────────────────────────────────────────────────────────┘
```

## 7. 구현 순서

| 순서 | 작업 | 예상 시간 |
|------|------|----------|
| 1 | 파일 생성 및 기본 구조 | 10분 |
| 2 | TEST_CASES 배열 정의 (45개) | 20분 |
| 3 | 로그인 및 네비게이션 | 10분 |
| 4 | runTest() 함수 구현 | 30분 |
| 5 | handleProductModal() 구현 | 15분 |
| 6 | analyzeResponse() 구현 | 15분 |
| 7 | 결과 저장 및 요약 | 10분 |
| 8 | 테스트 및 디버깅 | 30분 |

**총 예상 시간**: 약 2시간 30분

## 8. 에러 처리

| 에러 상황 | 처리 방법 |
|----------|----------|
| 로그인 실패 | 3회 재시도 후 종료 |
| 페이지 로드 실패 | 스크린샷 저장 후 다음 테스트 |
| 응답 타임아웃 | 30초 후 타임아웃 기록 |
| 제품 모달 미표시 | 기본 제품으로 진행 |
| 네트워크 에러 | 1회 재시도 후 에러 기록 |

## 9. 성공 기준 (재확인)

| 지표 | 목표 | 측정 방법 |
|------|------|----------|
| 테스트 통과율 | ≥ 80% | passed / total * 100 |
| Hallucination 비율 | ≤ 10% | hallucinations.length / total * 100 |
| 에러 발생 | ≤ 5건 | errors.length |

---

## Next Steps

1. `/pdca do openframe-rag-e2e-test` - 구현 시작
2. `e2e/e2e_openframe_rag.js` 파일 생성
3. 테스트 실행 및 결과 확인
4. `/pdca analyze openframe-rag-e2e-test` - Gap 분석
