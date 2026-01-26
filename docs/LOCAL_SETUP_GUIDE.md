# KMS 로컬 개발 환경 구성 가이드

이 문서는 KMS 시스템을 로컬 PC의 Docker 환경에서 동일하게 구성하는 방법을 설명합니다.

## 목차
1. [사전 요구사항](#1-사전-요구사항)
2. [환경별 구성 방법](#2-환경별-구성-방법)
3. [설치 단계](#3-설치-단계)
4. [서비스 시작](#4-서비스-시작)
5. [Ollama 모델 설치](#5-ollama-모델-설치)
6. [접속 확인](#6-접속-확인)
7. [문제 해결](#7-문제-해결)

---

## 1. 사전 요구사항

### 필수 소프트웨어
| 소프트웨어 | 최소 버전 | 확인 명령어 |
|-----------|----------|------------|
| Docker | 24.0+ | `docker --version` |
| Docker Compose | 2.20+ | `docker compose version` |
| Git | 2.30+ | `git --version` |

### 하드웨어 요구사항

#### CPU 모드 (GPU 없음)
- RAM: 16GB 이상 (32GB 권장)
- Disk: 50GB 이상 여유 공간
- CPU: 4코어 이상

#### GPU 모드
- RAM: 32GB 이상
- Disk: 100GB 이상 여유 공간
- GPU: NVIDIA GPU (VRAM 24GB 이상 권장)
  - RTX 3090/4090 (24GB)
  - RTX A5000/A6000 (24GB/48GB)
  - A100 (40GB/80GB)
- NVIDIA Driver: 535+
- NVIDIA Container Toolkit 설치 필요

---

## 2. 환경별 구성 방법

### 옵션 비교

| 구성 | LLM | Embedding | GPU 필요 | 추천 대상 |
|-----|-----|-----------|---------|----------|
| CPU 모드 | Ollama (qwen2.5:7b) | Ollama (nomic-embed) | X | 개발/테스트 |
| GPU 모드 | NVIDIA NIM | NVIDIA NIM | O | 프로덕션급 |
| 하이브리드 | Ollama (GPU) | Ollama | △ | 중간 성능 |
| **Remote 모드** | Remote GPU | Remote GPU | X (원격) | 원격 GPU 활용 |

---

## 3. 설치 단계

### Step 1: 소스 코드 클론
```bash
git clone <repository-url> kms
cd kms
```

### Step 2: 환경 변수 설정
```bash
# 템플릿 복사
cp .env.local.example .env.local

# 편집기로 열어서 필요한 값 수정
nano .env.local  # 또는 vim, code 등
```

**필수 수정 항목:**
```bash
# 보안 키 생성 (터미널에서 실행)
python3 -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_MASTER_KEY=' + Fernet.generate_key().decode())"
python3 -c "import secrets; print('ENCRYPTION_SALT=' + secrets.token_urlsafe(16))"
```

### Step 3: Docker 이미지 빌드
```bash
# CPU 모드
docker compose -f docker-compose-local.yml --profile cpu build

# GPU 모드
docker compose -f docker-compose-local.yml --profile gpu build
```

---

## 4. 서비스 시작

### CPU 모드 (GPU 없음)
```bash
# 기본 서비스 시작 (Backend + Frontend + DB + Ollama)
docker compose -f docker-compose-local.yml --profile cpu up -d

# 로그 확인
docker compose -f docker-compose-local.yml logs -f
```

### GPU 모드
```bash
# NVIDIA Container Toolkit 설치 확인
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi

# GPU 서비스 시작
docker compose -f docker-compose-local.yml --profile gpu up -d
```

### 전체 서비스 (pgAdmin 포함)
```bash
docker compose -f docker-compose-local.yml --profile all up -d
```

---

## 5. Ollama 모델 설치

### CPU 모드에서 모델 다운로드
```bash
# Ollama 컨테이너 접속
docker exec -it ollama-local ollama pull qwen2.5:7b

# Code LLM
docker exec -it ollama-local ollama pull codellama:7b

# Embedding 모델
docker exec -it ollama-local ollama pull nomic-embed-text

# 설치된 모델 확인
docker exec -it ollama-local ollama list
```

### GPU 모드 (선택사항)
```bash
# Ollama GPU 버전 사용 시
docker exec -it ollama-gpu ollama pull qwen2.5:7b
docker exec -it ollama-gpu ollama pull codellama:7b
docker exec -it ollama-gpu ollama pull nomic-embed-text
```

---

## 6. 접속 확인

### 서비스 상태 확인
```bash
docker compose -f docker-compose-local.yml ps
```

### 접속 URL

| 서비스 | URL | 용도 |
|--------|-----|------|
| Frontend | http://localhost:3000 | 웹 UI |
| Backend API | http://localhost:9000 | REST API |
| API Docs | http://localhost:9000/docs | Swagger UI |
| Neo4j Browser | http://localhost:7474 | Graph DB UI |
| pgAdmin | http://localhost:5050 | PostgreSQL UI |
| Ollama | http://localhost:11434 | LLM API |

### 헬스 체크
```bash
# Backend
curl http://localhost:9000/health

# Neo4j
curl http://localhost:7474

# Ollama
curl http://localhost:11434/api/tags
```

---

## 7. 문제 해결

### 포트 충돌
```bash
# 사용 중인 포트 확인
lsof -i :9000
lsof -i :3000

# 프로세스 종료 또는 docker-compose-local.yml에서 포트 변경
```

### Neo4j 시작 실패
```bash
# 로그 확인
docker logs neo4j-graphrag

# 볼륨 초기화 (데이터 삭제 주의!)
docker volume rm kms_neo4j_data
```

### Ollama 모델 로딩 느림
```bash
# 모델 상태 확인
docker exec -it ollama-local ollama list

# 메모리 사용량 확인
docker stats ollama-local
```

### NVIDIA GPU 인식 안됨
```bash
# 드라이버 확인
nvidia-smi

# Docker GPU 지원 확인
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi

# NVIDIA Container Toolkit 재설치
# Ubuntu/Debian
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 메모리 부족
```bash
# Docker 메모리 제한 확인 (Docker Desktop)
# Settings > Resources > Memory: 최소 8GB 이상 설정

# 컨테이너별 메모리 확인
docker stats
```

---

## 추가 참고

### 파일 구조
```
kms/
├── docker-compose-local.yml    # 로컬 개발용 Docker Compose
├── Dockerfile.local            # 로컬 개발용 Dockerfile
├── .env.local.example          # 환경 변수 템플릿
├── .env.local                  # 실제 환경 변수 (git 무시)
├── requirements-pinned.txt     # Python 패키지 (버전 고정)
└── kms-portal-ui/
    └── package.json            # Node.js 패키지
```

### 데이터 백업
```bash
# 볼륨 백업
docker run --rm -v kms_neo4j_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/neo4j-backup.tar.gz -C /data .

docker run --rm -v kms_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres-backup.tar.gz -C /data .
```

### 완전 초기화
```bash
# 모든 컨테이너 및 볼륨 삭제
docker compose -f docker-compose-local.yml down -v

# 이미지까지 삭제
docker compose -f docker-compose-local.yml down -v --rmi all
```

---

## 8. Remote 모드 (원격 GPU/DB 사용)

로컬 PC에서는 Backend와 Frontend만 실행하고, GPU 및 데이터베이스는 원격 서버를 사용하는 구성입니다.

### 원격 서버 구성 (192.168.8.11)

| 서비스 | 포트 | 설명 |
|--------|------|------|
| PostgreSQL | 5432 | 관계형 데이터베이스 |
| Neo4j HTTP | 7474 | Graph DB 웹 UI |
| Neo4j Bolt | 7687 | Graph DB 연결 |
| Nemotron LLM | 12800 | 메인 LLM (GPU 0) |
| Embedding | 12801 | 임베딩 모델 (GPU 1) |
| Code LLM | 12802 | 코드 분석 LLM (GPU 2) |
| Ollama | 11434 | 로컬 LLM 서버 |

### Remote 모드 시작

```bash
# 1. 환경 변수 확인/수정
# .env.local 파일에서 원격 서버 IP 확인
cat .env.local | grep "192.168.8.11"

# 2. 원격 서버 연결 테스트
# PostgreSQL
nc -zv 192.168.8.11 5432

# Neo4j
nc -zv 192.168.8.11 7687

# LLM API
curl http://192.168.8.11:12800/v1/health/ready

# Embedding API
curl http://192.168.8.11:12801/v1/health/ready

# 3. 서비스 시작 (Backend + Frontend만)
docker compose -f docker-compose-remote.yml up -d

# 4. 로그 확인
docker compose -f docker-compose-remote.yml logs -f
```

### Remote 모드 환경 변수 (.env.local)

```bash
# 데이터베이스 (원격)
NEO4J_URI=bolt://192.168.8.11:7687
POSTGRES_HOST=192.168.8.11

# LLM API (원격 GPU)
LLM_API_URL=http://192.168.8.11:12800/v1/chat/completions
EMBEDDING_API_URL=http://192.168.8.11:12801/v1
CODE_LLM_API_URL=http://192.168.8.11:12802/v1/chat/completions
OLLAMA_BASE_URL=http://192.168.8.11:11434
```

### 원격 서버 상태 확인

```bash
# 모든 원격 서비스 헬스 체크
echo "=== PostgreSQL ===" && nc -zv 192.168.8.11 5432
echo "=== Neo4j ===" && curl -s http://192.168.8.11:7474
echo "=== LLM ===" && curl -s http://192.168.8.11:12800/v1/health/ready
echo "=== Embedding ===" && curl -s http://192.168.8.11:12801/v1/health/ready
echo "=== Code LLM ===" && curl -s http://192.168.8.11:12802/health
echo "=== Ollama ===" && curl -s http://192.168.8.11:11434/api/tags
```

### Remote 모드 문제 해결

#### 원격 서버 연결 실패
```bash
# 방화벽 확인 (원격 서버에서)
sudo firewall-cmd --list-ports

# 필요한 포트 열기 (원격 서버에서)
sudo firewall-cmd --permanent --add-port=5432/tcp
sudo firewall-cmd --permanent --add-port=7474/tcp
sudo firewall-cmd --permanent --add-port=7687/tcp
sudo firewall-cmd --permanent --add-port=12800-12805/tcp
sudo firewall-cmd --permanent --add-port=11434/tcp
sudo firewall-cmd --reload
```

#### LLM 응답 지연
```bash
# 네트워크 지연 확인
ping 192.168.8.11

# API 응답 시간 측정
time curl -s http://192.168.8.11:12800/v1/health/ready
```

### Remote 모드 파일 구조

```
kms/
├── docker-compose-remote.yml   # Remote 모드용 (Backend + Frontend만)
├── docker-compose-local.yml    # 로컬 전체 구성용
├── .env.local                  # 원격 서비스 URL 설정
└── Dockerfile.local            # 로컬 빌드용
```
