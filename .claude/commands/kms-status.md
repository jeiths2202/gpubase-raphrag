---
description: KMS 시스템 상태를 확인합니다. 서버 상태, Docker 컨테이너, GPU, 서비스 헬스체크를 수행합니다.
---

# KMS Status Check Skill

KMS 시스템의 전체 상태를 확인하는 스킬입니다.

## 사용법

```
/kms-status            # 전체 상태 확인
/kms-status server     # 서버 상태만
/kms-status docker     # Docker 컨테이너 상태
/kms-status gpu        # GPU 상태
/kms-status health     # API 헬스체크
```

## 전체 상태 확인

### 1. 서버 상태 (PowerShell)
```powershell
.\scripts\server.ps1 status
```

### 2. Docker 컨테이너 상태
```bash
docker ps | grep kms
docker ps | grep -E "neo4j|postgres|minicpm|embed"
```

### 3. GPU 상태
```bash
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv
```

### 4. API 헬스체크
```bash
# Backend
curl -s http://localhost:9000/health | jq

# OpenFrame RAG
curl -s http://localhost:9000/api/v1/openframe-rag/health | jq

# Frontend
curl -s http://localhost:3000 -o /dev/null -w "%{http_code}"
```

## 포트 할당

| 포트 | 서비스 |
|------|--------|
| 3000 | React Frontend |
| 9000 | FastAPI Backend |
| 7474 | Neo4j HTTP |
| 7687 | Neo4j Bolt |
| 12800 | Nemotron LLM (백업) |
| 12801 | Embeddings |
| 12802 | Mistral Code |
| 12803 | MiniCPM-V Vision LLM |

## Docker 컨테이너 관리

### 상태 확인
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### 로그 확인
```bash
docker logs kms-backend-local --tail 50
docker logs minicpm-vision-graphrag --tail 50
```

### 재시작
```bash
docker restart kms-backend-local
docker restart kms-frontend-local
```

## GPU 구성 (현재)

| 컨테이너 | 모델 | GPU | 포트 |
|----------|------|-----|------|
| minicpm-vision-graphrag | MiniCPM-V 2.6 | 5, 6 | 12803 |
| embedding-server | NV-EmbedQA-Mistral 7B | - | 12801 |

## 서비스 헬스체크 상세

### Backend API
```bash
curl -s http://localhost:9000/api/v1/health | python -m json.tool
```

### Learning LLM 상태
```bash
curl -s http://localhost:9000/api/v1/learning-llm/status | python -m json.tool
```

### OpenFrame RAG 제품 목록
```bash
curl -s http://localhost:9000/api/v1/openframe-rag/products | python -m json.tool
```

## Windows 직접 실행 모드

### 서버 시작/중지
```powershell
.\scripts\server.ps1 all start       # 전체 시작
.\scripts\server.ps1 all stop        # 전체 중지
.\scripts\server.ps1 all restart     # 전체 재시작
```

### 개별 서비스
```powershell
.\scripts\server.ps1 backend start   # 백엔드만
.\scripts\server.ps1 frontend start  # 프론트엔드만
.\scripts\server.ps1 backend logs 100 # 로그 확인
```

## 환경 파일 전환

```powershell
# Windows 직접 실행용
copy .env.local .env

# Docker 실행용
copy .env.docker .env
```

## 문제 해결

### Backend 시작 안됨
```bash
netstat -ano | findstr :9000  # 포트 사용 확인
python --version              # Python 3.10+ 확인
```

### Neo4j 연결 실패
```bash
curl http://localhost:7474    # Neo4j 상태 확인
```

### GPU 메모리 부족
```bash
nvidia-smi                    # GPU 메모리 확인
docker restart minicpm-vision-graphrag
```
