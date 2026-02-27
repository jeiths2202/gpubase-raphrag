---
description: KMS 문서 처리 및 요약본 관리를 수행합니다. PDF 분석, 에러코드/용어 추출, 인덱스 재생성을 처리합니다.
---

# KMS Document Processing Skill

KMS 문서 처리 및 요약본 시스템을 관리하는 스킬입니다.

## 사용법

```
/kms-docs process      # 전체 요약본 생성
/kms-docs errors       # 에러 코드만 추출
/kms-docs glossary     # 용어 사전 추출
/kms-docs commands     # 명령어 추출
/kms-docs index        # 인덱스 재생성
```

## Two-Stage Retrieval 시스템

```
사용자 질문: "-5212 에러 원인이 뭐야?"
    │
    ▼
요약본 검색 (파일 시스템 기반, <10ms)
├── error-codes/BASE-5000.md → 에러 정보 추출
└── glossary/T.md → 용어 정보 추출
    │
    ▼
보강된 쿼리: "질문 + [에러 -5212: DSALC_ERR_DATASET_NOT_FOUND]"
    │
    ▼
Vector/Graph DB 검색 (정확도 향상)
```

## 요약본 디렉토리 구조

```
uploads/summaries/
├── index.md                 # 마스터 인덱스
├── index.json               # JSON 인덱스
├── error-codes/             # 에러 코드 사전 (46개 파일)
│   ├── BASE-5000.md
│   ├── AIM-21000.md
│   └── ...
├── glossary/                # 용어 사전 (A-Z)
│   ├── T.md                 # TJES, TACF, TSO 등
│   └── ...
├── commands/                # OpenFrame 명령어
│   ├── OpenFrame_TJES_MVS.md
│   └── ...
├── configs/                 # 설정 파라미터
├── apis/                    # API 함수
└── terms/                   # 기술 용어
```

## 명령어

### 전체 요약본 생성
```bash
python -m scripts.manual_processor.main process-all
```

### 에러 코드 추출
```bash
python -m scripts.manual_processor.main extract-errors
```

### 포괄적 정보 추출 (Commands, Configs, APIs, Terms)
```bash
python -m scripts.manual_processor.main extract-comprehensive
```

### 인덱스 재생성
```bash
python -m scripts.manual_processor.main rebuild-index
```

## 요약본 콘텐츠 타입

| 폴더 | 내용 | 예시 |
|------|------|------|
| error-codes/ | 에러 코드, 원인, 해결방법 | `-5212: DATASET_NOT_FOUND` |
| glossary/ | 약어, 전문용어 정의 | `TJES: Tmax Job Entry Subsystem` |
| commands/ | OpenFrame 관리 명령어 | `tjesmgr BOOT`, `hidbmgr START` |
| configs/ | 설정 파라미터 상세 | `oframe.conf 옵션` |
| apis/ | 프로그래밍 API 함수 | `DSALC_*` 함수 목록 |
| terms/ | 도메인 전문 용어 | `Batch Processing`, `JCL` |

## 서비스 API 사용

```python
from app.api.services.summary_search_service import get_summary_search_service

service = get_summary_search_service()

# 에러 코드 검색
error = await service.search_error_code("-5212")

# 용어 검색
term = await service.search_glossary("TJES")

# 쿼리 보강 (RAG Agent 연동)
enriched = await service.enrich_query("-5212 에러 원인")
```

## Graph DB Entity 연동

요약본 → Entity 변환:
```bash
python scripts/populate_entities_from_summaries.py
```

요약본의 명령어/용어를 Graph DB Entity로 변환하여 검색 정확도 향상.
