---
description: KMS E2E 테스트를 실행합니다. Hallucination 감지, 키워드 테스트, 개별 명령어 테스트를 수행합니다.
---

# KMS E2E Test Skill

KMS RAG 시스템의 품질을 검증하는 E2E 테스트 스킬입니다.

## 사용법

```
/kms-test              # 전체 테스트 실행
/kms-test sentence     # 문장 기반 Hallucination 테스트 (45개 케이스)
/kms-test keyword      # 키워드 기반 검색 테스트
/kms-test tjesmgr      # tjesmgr 명령어 테스트
/kms-test tacfmgr      # tacfmgr 명령어 테스트
/kms-test hidbmgr      # hidbmgr 명령어 테스트
```

## 테스트 실행

### 1. 문장 기반 Hallucination 테스트 (권장)
```bash
cd e2e && node e2e_sentence_test.js
```

**테스트 대상:**
- OpenFrame 컴포넌트: tjesmgr, tacfmgr, hidbmgr, oscmgr 등
- 유틸리티: idcams, iebgener, dfsort 등
- 설정 파일: tjes.conf, osc.conf, tacf.conf 등

### 2. 키워드 기반 테스트
```bash
cd e2e && node e2e_keyword_test.js
```

### 3. 개별 명령어 테스트
```bash
cd e2e && node e2e_tjesmgr.js   # tjesmgr 전용
cd e2e && node e2e_tacfmgr.js   # tacfmgr 전용
cd e2e && node e2e_hidbmgr.js   # hidbmgr 전용
```

## 테스트 결과 확인

### 결과 파일
| 파일 | 내용 |
|------|------|
| `e2e/sentence_test_results.json` | 문장 테스트 결과 |
| `e2e/test_results.json` | 키워드 테스트 결과 |
| `e2e/hallucination_*.png` | Hallucination 발생 시 스크린샷 |

### 결과 형식
```json
{
  "total": 45,
  "passed": 40,
  "failed": 5,
  "hallucinations": [...],
  "noResults": [...],
  "errors": []
}
```

## Hallucination 감지 로직

```javascript
// 예: "tjesmgr"를 질문했는데 "oscmgr"가 응답에 포함되면 Hallucination
{
  keyword: 'tjesmgr',
  expected: ['tjesmgr', 'TJES'],      // 기대 키워드
  notExpected: ['oscmgr', 'osimgr']   // Hallucination 감지 키워드
}
```

## 테스트 개선 워크플로

1. E2E 테스트 실행 → Hallucination 케이스 확인
2. `hallucination_*.png` 스크린샷 분석
3. RAG 검색 로직 또는 Summary 데이터 개선
4. 재테스트로 검증

## 사전 요구사항

- Node.js 설치
- Playwright 설치: `npm install playwright`
- KMS 서버 실행 중 (localhost:9000, localhost:3000)
