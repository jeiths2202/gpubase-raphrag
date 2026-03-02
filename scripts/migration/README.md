# KMS System Migration Scripts

이 디렉토리에는 KMS 시스템을 Redhat Linux 64-bit GPU 환경으로 이관하기 위한 자동화 스크립트가 포함되어 있습니다.

## 개요

전체 이관 프로세스는 세 단계로 구성됩니다:

1. **Export (소스 시스템)**: 모든 데이터와 설정을 내보내기
2. **Setup (타겟 시스템)**: 타겟 환경 준비
3. **Deploy (타겟 시스템)**: 애플리케이션 배포

## 스크립트 목록

| 스크립트 | 설명 | 실행 위치 |
|----------|------|----------|
| `export_system.ps1` | Windows PowerShell 내보내기 스크립트 | 소스 (Windows) |
| `export_system.sh` | Bash 내보내기 스크립트 | 소스 (Linux/Mac) |
| `setup_target.sh` | 타겟 시스템 환경 설정 | 타겟 (RHEL) |
| `deploy.sh` | 애플리케이션 배포 | 타겟 (RHEL) |

## 빠른 시작 가이드

### 1단계: 소스 시스템에서 내보내기 (Windows)

```powershell
# PowerShell에서 실행
cd C:\path\to\gpubase-raphrag
.\scripts\migration\export_system.ps1
```

생성되는 파일:
- `migration_export_YYYYMMDD_HHMMSS/` - 내보내기 디렉토리
- `kms_migration_YYYYMMDD_HHMMSS.tar.gz` - 압축 아카이브

### 2단계: 아카이브 전송

```bash
# scp 또는 rsync로 전송
scp kms_migration_*.tar.gz user@target-server:/tmp/
```

### 3단계: 타겟 시스템 설정 (RHEL)

```bash
# 타겟 서버에서 실행
cd /tmp
tar -xzvf kms_migration_*.tar.gz
cd migration_export_*

# 시스템 설정 (root 권한 필요)
sudo ./setup_target.sh
```

### 4단계: 환경 설정

```bash
# .env 파일 편집
sudo vi /opt/kms/.env

# 필수 설정 항목:
# - JWT_SECRET_KEY (openssl rand -base64 32)
# - ENCRYPTION_MASTER_KEY (openssl rand -base64 32)
# - ENCRYPTION_SALT (openssl rand -base64 16)
# - NEO4J_PASSWORD
# - POSTGRES_PASSWORD
# - NGC_API_KEY (NVIDIA NIM 사용 시)
```

### 5단계: 배포

```bash
# 배포 스크립트 실행
sudo ./deploy.sh
```

## 내보내기 구성 요소

### 데이터베이스
- PostgreSQL 스키마 (`database/schema.sql`)
- PostgreSQL 데이터 (`database/data.sql`)
- 전체 덤프 (`database/full_dump.pgdump`)
- 마이그레이션 스크립트 (`database/*.sql`)

### 소스 코드
- 백엔드 API (`source/app/`)
- 프론트엔드 UI (`source/kms-portal-ui/`)
- 유틸리티 스크립트 (`source/scripts/`)
- 테스트 (`source/tests/`)

### 설정
- 환경 변수 템플릿 (`config/.env.example`)
- Python 의존성 (`config/requirements-api.txt`)
- 프론트엔드 패키지 (`config/frontend-package.json`)
- Docker 구성 (`docker/docker-compose.yml`)

### Neo4j 데이터
- 데이터 디렉토리 (`neo4j/data/`)
- 플러그인 (`neo4j/plugins/`)

## 타겟 시스템 요구 사항

### 하드웨어
| 구성 요소 | 최소 사양 | 권장 사양 |
|-----------|----------|----------|
| CPU | 8 코어 | 16+ 코어 |
| RAM | 32GB | 64GB+ |
| GPU | NVIDIA A100 x1 | NVIDIA A100 x8 |
| 저장 장치 | 200GB SSD | 500GB+ NVMe |

### 소프트웨어
- OS: Red Hat Enterprise Linux 8/9 (64-bit)
- Python: 3.10+
- Node.js: 18+ LTS
- Docker: 24.0+
- NVIDIA Driver: 535+
- CUDA: 12.0+

## 포트 할당

| 포트 | 서비스 |
|------|--------|
| 3000 | React 프론트엔드 |
| 9000 | FastAPI 백엔드 |
| 5432 | PostgreSQL |
| 7474 | Neo4j HTTP |
| 7687 | Neo4j Bolt |
| 12800 | Nemotron LLM |
| 12801 | NeMo Embedding |
| 12802 | Mistral Code LLM |

## 배포 옵션

```bash
# 전체 배포
sudo ./deploy.sh

# Docker 서비스 건너뛰기 (수동으로 시작할 경우)
sudo ./deploy.sh --skip-docker

# 데이터베이스 초기화 건너뛰기 (이미 설정된 경우)
sudo ./deploy.sh --skip-db

# 프론트엔드 빌드 건너뛰기
sudo ./deploy.sh --skip-frontend

# 강제 재설치
sudo ./deploy.sh --force
```

## 서비스 관리

```bash
# 서비스 상태 확인
systemctl status kms-backend
systemctl status kms-frontend
systemctl status kms-docker

# 서비스 재시작
systemctl restart kms-backend
systemctl restart kms-frontend

# 로그 확인
journalctl -u kms-backend -f
journalctl -u kms-frontend -f
docker logs nemotron-graphrag -f
```

## 문제 해결

### PostgreSQL 연결 실패
```bash
# Docker 컨테이너 상태 확인
docker ps | grep postgres
docker logs postgres-graphrag

# 수동 연결 테스트
PGPASSWORD=your_password psql -h localhost -U raguser -d ragdb
```

### GPU 인식 실패
```bash
# NVIDIA 드라이버 확인
nvidia-smi

# Docker GPU 지원 확인
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# NVIDIA Container Toolkit 재설치
sudo dnf reinstall nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 백엔드 시작 실패
```bash
# 로그 확인
journalctl -u kms-backend -n 100

# 수동 시작 테스트
cd /opt/kms/app
source /opt/kms/venv/bin/activate
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 9000
```

## 롤백

문제 발생 시 이전 상태로 롤백:

```bash
# 서비스 중지
sudo systemctl stop kms-backend kms-frontend kms-docker

# Docker 볼륨 정리 (주의: 데이터 삭제됨)
docker compose -f /opt/kms/docker/docker-compose.yml down -v

# 이전 백업에서 복원
# (백업이 있는 경우)
```

## 지원

문제가 발생하면:
1. 로그 파일 확인
2. MIGRATION_REPORT.md 참조
3. 시스템 요구 사항 재확인
