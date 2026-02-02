---
description: OpenFrame KMS RAG 쿼리를 실행합니다. 8개 제품(MVS, MSP, VOS3, Tibero7, OFASM, OFCOBOL, XSP, Tmax)에 대한 기술 질문을 처리합니다.
---

# KMS RAG Query Skill

OpenFrame KMS 시스템에 RAG 쿼리를 실행하는 스킬입니다.

## 사용법

```
/kms-query <질문>
/kms-query tjesmgr BOOT 에러 해결법
/kms-query -5212 에러 원인
```

## 실행 단계

1. **인증 토큰 획득**
```bash
TOKEN=$(curl -s -X POST http://localhost:9000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @scripts/login.json | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
```

2. **제품 자동 분류** (선택사항)
```bash
curl -s -X POST http://localhost:9000/api/v1/openframe-rag/classify \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "$ARGUMENTS"}'
```

3. **RAG 쿼리 실행**
```bash
curl -s -X POST http://localhost:9000/api/v1/openframe-rag/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "$ARGUMENTS", "stream": true}'
```

## 지원 제품

| ID | 제품명 | 주요 키워드 |
|----|--------|-------------|
| `openframe_mvs` | OpenFrame MVS | tjesmgr, jesinit, TJES |
| `msp_openframe` | MSP OpenFrame | MSP, JCL |
| `vos3_openframe` | VOS3 OpenFrame | VOS3 |
| `tibero7` | Tibero 7 | tbsql, Tibero |
| `ofasm` | OpenFrame ASM | OFASM, 어셈블러 |
| `ofcobol` | OpenFrame COBOL | OFCOBOL, COBOL |
| `xsp_openframe` | XSP OpenFrame | XSP |
| `tmax` | Tmax 6.0 | tmboot, tmdown, Tmax |

## DeepSeek 모드

전체 제품 통합 검색이 필요한 경우:
```bash
curl -s -X POST http://localhost:9000/api/v1/openframe-rag/deep-seek/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "$ARGUMENTS"}'
```

## 응답 형식

SSE 스트리밍으로 실시간 응답:
- `event: classification` - 제품 분류 결과
- `event: token` - 응답 토큰
- `event: sources` - 출처 정보
- `event: done` - 완료
