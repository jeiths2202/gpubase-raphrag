# Plan: OpenFrame RAG E2E 테스트

> **Feature**: openframe-rag-e2e-test
> **Created**: 2026-01-31
> **Status**: Plan Phase

## 1. 개요 (Overview)

### 목적
OpenFrame RAG 페이지(`/openframe-rag`)에서 E2E 테스트를 구현하여 Learning LLM 기반 Multi-Product RAG 시스템의 품질을 검증한다.

### 배경
- 기존 E2E 테스트(`e2e_sentence_test.js`)는 AI Agent 페이지(`/agent`)를 대상으로 함
- OpenFrame RAG 페이지는 별도의 UI/API 구조를 가지고 있음
- 8개 제품별 Learning LLM + Vector/Graph 검색 통합 테스트 필요

### 범위
| 포함 | 제외 |
|------|------|
| OpenFrame RAG 페이지 E2E 테스트 | 기존 AI Agent 테스트 수정 |
| 제품별 Hallucination 감지 | 백엔드 API 단위 테스트 |
| DeepSeek 통합 검색 테스트 | 성능/부하 테스트 |

## 2. 요구사항 (Requirements)

### 기능 요구사항 (FR)

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-01 | OpenFrame RAG 페이지 로그인 및 네비게이션 | High |
| FR-02 | 제품별 쿼리 테스트 (8개 제품) | High |
| FR-03 | Hallucination 감지 및 스크린샷 저장 | High |
| FR-04 | 테스트 결과 JSON 출력 | Medium |
| FR-05 | DeepSeek 통합 검색 테스트 | Medium |

### 비기능 요구사항 (NFR)

| ID | 요구사항 | 기준 |
|----|---------|------|
| NFR-01 | 테스트 실행 시간 | 45개 케이스 30분 이내 |
| NFR-02 | Hallucination 임계값 | 10% 미만 |
| NFR-03 | 안정성 | 연속 3회 실행 성공 |

## 3. 테스트 대상 (Test Scope)

### 대상 제품 (8개)
```
openframe_mvs   - OpenFrame MVS
msp_openframe   - MSP OpenFrame
vos3_openframe  - VOS3 OpenFrame
tibero7         - Tibero 7
ofasm           - OFASM (Assembler)
ofcobol         - OFCOBOL
xsp_openframe   - XSP OpenFrame
tmax            - Tmax
```

### 테스트 케이스 분류

| 카테고리 | 예시 쿼리 | 기대 결과 |
|---------|----------|----------|
| Manager 명령어 | "tjesmgr BOOT 사용법" | tjesmgr 관련 응답 |
| 에러코드 | "에러코드 -5212 원인" | 에러 정보 포함 |
| 설정 파일 | "tjes.conf 설정" | 설정 파라미터 설명 |
| 유틸리티 | "idcams DEFINE" | VSAM 관련 응답 |
| 제품 선택 | 자동 감지 vs 수동 선택 | 올바른 제품 매칭 |

## 4. 기술 스택

| 구성요소 | 기술 |
|---------|------|
| 테스트 프레임워크 | Playwright (Chromium) |
| 언어 | JavaScript (Node.js) |
| 대상 URL | https://localhost:3000/openframe-rag |
| 인증 | admin / SecureAdm1nP@ss2024! |

## 5. 파일 구조

```
e2e/
├── e2e_openframe_rag.js       # 메인 테스트 파일 (신규)
├── openframe_rag_results.json # 테스트 결과
├── hallucination_*.png        # 실패 스크린샷
└── e2e_sentence_test.js       # 기존 AI Agent 테스트 (참조)
```

## 6. 구현 계획

### Phase 1: 기본 테스트 구현
- [ ] 로그인 및 페이지 네비게이션
- [ ] 기본 쿼리 입력 및 응답 대기
- [ ] 제품 선택 모달 처리

### Phase 2: 테스트 케이스 확장
- [ ] 8개 제품별 테스트 케이스 정의
- [ ] Hallucination 감지 로직
- [ ] 결과 JSON 저장

### Phase 3: DeepSeek 테스트
- [ ] DeepSeek 모드 활성화 테스트
- [ ] 통합 검색 결과 검증

## 7. 성공 기준

| 지표 | 목표 |
|------|------|
| 테스트 통과율 | ≥ 80% |
| Hallucination 발생률 | ≤ 10% |
| 에러/크래시 | 0건 |

## 8. 리스크 및 대응

| 리스크 | 대응 방안 |
|--------|----------|
| 제품 선택 모달 타이밍 이슈 | waitForSelector + 재시도 로직 |
| SSE 스트리밍 응답 대기 | 적절한 timeout 설정 (30초) |
| LLM 서버 불안정 | health check 후 테스트 시작 |

## 9. 참조

- 기존 테스트: `e2e/e2e_sentence_test.js`
- OpenFrame RAG 페이지: `kms-portal-ui/src/pages/OpenFrameRAGPage.tsx`
- API 엔드포인트: `/api/v1/openframe-rag/stream`

---

## Next Steps

1. `/pdca design openframe-rag-e2e-test` - Design 문서 작성
2. 테스트 파일 구현
3. `/pdca analyze openframe-rag-e2e-test` - Gap 분석
