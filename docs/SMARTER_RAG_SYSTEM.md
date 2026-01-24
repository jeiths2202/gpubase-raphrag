# Smarter RAG System

## Overview

Smarter RAG는 사용자 피드백을 기반으로 지속적으로 학습하는 지능형 RAG 시스템입니다.

### 핵심 기능
- **피드백 기반 학습**: 👍 → 학습, 👎 → 망각
- **3단계 응답 우선순위**: Verified Knowledge → Learning LLM → Document RAG
- **QLoRA 파인튜닝**: 메모리 효율적인 도메인 특화 학습
- **자동 스케줄링**: 매일 00:00 자동 학습

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Query                             │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    RAG Service                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Step 0: Verified Knowledge Store (similarity ≥ 0.85)│   │
│  │         → Return stored answer directly             │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │ No match                          │
│  ┌──────────────────────▼──────────────────────────────┐   │
│  │ Step 0.5: Learning LLM (confidence ≥ 0.6)          │   │
│  │           → Generate from learned patterns          │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │ Not available                     │
│  ┌──────────────────────▼──────────────────────────────┐   │
│  │ Step 1-3: Session Docs → External → Global KB       │   │
│  │           → Traditional RAG pipeline                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   Feedback Loop                             │
│                                                             │
│  User 👍  ─────────►  Verified Knowledge Store              │
│                              │                              │
│                              ▼ (Daily 00:00)                │
│                       QLoRA Training                        │
│                              │                              │
│                              ▼                              │
│                        Learning LLM                         │
│                                                             │
│  User 👎  ─────────►  Mark as "unlearn_required"           │
│                              │                              │
│                              ▼ (Next training)              │
│                     Remove from model                       │
└─────────────────────────────────────────────────────────────┘
```

## Components

### 1. Verified Knowledge Store
- **위치**: PostgreSQL `verified_knowledge` 테이블
- **기능**: 👍 받은 Q&A 쌍 저장
- **검색**: 텍스트 유사도 기반 (similarity ≥ 0.85)

### 2. Learning LLM Service
- **모델**: Qwen2.5-7B + QLoRA (4-bit 양자화)
- **VRAM**: ~8GB
- **기능**: 학습된 패턴 기반 응답 생성

### 3. Training Pipeline
- **방식**: QLoRA (Quantized LoRA)
- **스케줄**: 매일 00:00 또는 수동 트리거
- **어댑터 저장**: `/opt/kms/models/qlora_adapters/`

### 4. Monitoring
- **메트릭**: VK 통계, LLM 상태, 학습 현황
- **대시보드**: Admin Dashboard > Learning 탭

## API Endpoints

### Verified Knowledge
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/verified-knowledge/stats/overview` | GET | VK 통계 |
| `/verified-knowledge/search` | GET | VK 검색 |
| `/verified-knowledge/training/trigger` | POST | 수동 학습 |
| `/verified-knowledge/training/batches` | GET | 학습 배치 목록 |
| `/verified-knowledge/training/schedule` | GET/PATCH | 스케줄 관리 |

### Learning LLM
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/verified-knowledge/learning-llm/status` | GET | LLM 상태 |
| `/verified-knowledge/learning-llm/generate` | POST | 응답 생성 |
| `/verified-knowledge/learning-llm/reload` | POST | 어댑터 리로드 |
| `/verified-knowledge/learning-llm/unload` | POST | 메모리 해제 |

### Monitoring
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/verified-knowledge/monitor/metrics` | GET | 전체 메트릭 |
| `/verified-knowledge/monitor/health` | GET | 헬스 상태 |
| `/verified-knowledge/monitor/dashboard` | GET | 대시보드 데이터 |

## Configuration

### Environment Variables

```bash
# Learning LLM
ENABLE_LEARNING_LLM=true          # 서비스 활성화
LEARNING_LLM_AUTO_LOAD=false      # 자동 모델 로드
LEARNING_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct

# Code LLM (경량 모델)
CODE_LLM_USE_OLLAMA_FALLBACK=true
CODE_LLM_OLLAMA_MODEL=qwen2.5-coder:3b
```

## Files Structure

```
/opt/kms/
├── app/api/
│   ├── services/
│   │   ├── verified_knowledge_service.py  # VK Store 서비스
│   │   ├── learning_llm_service.py        # Learning LLM 서비스
│   │   ├── code_llm_service.py            # Code LLM 서비스
│   │   ├── smarter_rag_monitor.py         # 모니터링 서비스
│   │   └── rag_service.py                 # RAG 파이프라인 (수정됨)
│   ├── routers/
│   │   └── verified_knowledge.py          # API 엔드포인트
│   ├── adapters/learning_llm/
│   │   └── adapter.py                     # QLoRA 어댑터
│   └── infrastructure/postgres/
│       └── verified_knowledge_repository.py
├── scripts/
│   ├── training/
│   │   ├── qlora_trainer.py               # QLoRA 학습 스크립트
│   │   └── scheduler.py                   # 스케줄러
│   └── testing/
│       ├── test_smarter_rag_e2e.py        # E2E 테스트
│       └── run_smarter_rag_tests.sh       # 테스트 실행
├── migrations/
│   └── 027_verified_knowledge.sql         # DB 스키마
├── models/
│   └── qlora_adapters/                    # 학습된 어댑터
├── kms-portal-ui/src/components/admin/learning/
│   ├── LearningManagementTab.tsx          # 관리 UI
│   └── LearningManagementTab.css          # 스타일
└── docs/
    ├── SMARTER_RAG_SYSTEM.md              # 이 문서
    └── SMARTER_RAG_GPU_SETUP.md           # GPU 설정 가이드
```

## Testing

### E2E Test Suite
```bash
# 전체 테스트 실행
./scripts/testing/run_smarter_rag_tests.sh

# 옵션 지정
./scripts/testing/run_smarter_rag_tests.sh \
    --url http://localhost:9000 \
    --username admin \
    --password "YourPassword"
```

### 테스트 항목
1. Authentication
2. System Health Check
3. Verified Knowledge Stats
4. Create Conversation & Query
5. Submit Thumbs Up Feedback
6. Verify Knowledge Registration
7. Query Verified Knowledge
8. Learning LLM Status
9. Training Schedule Check

## Workflow

### 1. 기본 플로우
```
1. 사용자 질문
2. VK Store 검색 (similarity ≥ 0.85)
3. 매칭 → 저장된 답변 반환
4. 미매칭 → Learning LLM 확인
5. LLM 가능 → 생성된 답변 반환
6. 불가 → 기존 RAG 파이프라인
```

### 2. 학습 플로우
```
1. 사용자 👍 클릭
2. VK Store에 Q&A 등록 (trigger)
3. 매일 00:00 학습 실행 (또는 수동)
4. QLoRA 파인튜닝
5. 새 어댑터 저장
6. Learning LLM에 로드
```

### 3. 망각 플로우
```
1. 사용자 👎 클릭
2. VK Store에서 "unlearn_required" 마킹
3. 다음 학습 시 제거 처리
4. 모델에서 해당 지식 제거
```

## Monitoring

### Admin Dashboard
1. Admin Dashboard 접속
2. "Learning" 탭 선택
3. 확인 가능한 정보:
   - Active/Trained/Pending 통계
   - Learning LLM 상태
   - 학습 스케줄
   - 최근 학습 배치
   - 일별 통계 차트

### API 모니터링
```bash
# 메트릭 조회
curl http://localhost:9000/api/v1/verified-knowledge/monitor/metrics

# 헬스 체크
curl http://localhost:9000/api/v1/verified-knowledge/monitor/health

# 대시보드 데이터
curl http://localhost:9000/api/v1/verified-knowledge/monitor/dashboard
```

## Troubleshooting

### Learning LLM이 로드되지 않음
```bash
# 어댑터 확인
ls -la /opt/kms/models/qlora_adapters/

# 수동 로드
curl -X POST http://localhost:9000/api/v1/verified-knowledge/learning-llm/reload
```

### VK Store에 등록되지 않음
1. 피드백 API 응답 확인
2. PostgreSQL 트리거 확인
3. `verified_knowledge` 테이블 직접 조회

### 학습이 실패함
```bash
# 로그 확인
tail -f /opt/kms/logs/training_*.log

# GPU 메모리 확인
nvidia-smi
```

## Performance

| Component | Memory | Latency |
|-----------|--------|---------|
| VK Store Search | ~100MB | ~10ms |
| Learning LLM (4-bit) | ~8GB | ~200ms |
| QLoRA Training (7B) | ~12GB | ~2h/1000 samples |

## Version History

- **v1.0** (2026-01): Initial release
  - Verified Knowledge Store
  - QLoRA Training Pipeline
  - Learning LLM Integration
  - Admin Dashboard
  - E2E Test Suite
