# HybridRAG KMS 성능 개선 및 규모 확장 가이드

이 문서는 HybridRAG KMS 프로젝트의 성능 개선 및 규모 확장 시 설정해야 할 파라미터를 정리합니다.

## 목차

1. [현재 시스템 용량](#1-현재-시스템-용량)
2. [SSL/TLS 설정](#2-ssltls-설정)
3. [Nginx 최적화](#3-nginx-최적화)
4. [FastAPI/Uvicorn 최적화](#4-fastapiuvicorn-최적화)
5. [PostgreSQL 최적화](#5-postgresql-최적화)
6. [Neo4j 최적화](#6-neo4j-최적화)
7. [LLM 서비스 최적화](#7-llm-서비스-최적화)
8. [Rate Limiting 조정](#8-rate-limiting-조정)
9. [백그라운드 작업 최적화](#9-백그라운드-작업-최적화)
10. [Docker/컨테이너 최적화](#10-docker컨테이너-최적화)
11. [모니터링 및 로깅](#11-모니터링-및-로깅)
12. [규모별 권장 설정](#12-규모별-권장-설정)

---

## 1. 현재 시스템 용량

### 기본 설정 기준 용량

| 항목 | 현재값 | 동시 처리 능력 |
|------|--------|---------------|
| Uvicorn 워커 | 4개 | ~400 req/sec |
| PostgreSQL 연결 풀 | 20개 | 20개 동시 쿼리 |
| LLM 동시 시퀀스 | 64개 | 64개 동시 추론 |
| 백그라운드 작업 | 3개 | 3개 동시 작업 |
| **적정 동시 사용자** | - | **100-500명** |

---

## 2. SSL/TLS 설정

### 2.1 인증서 생성

#### Let's Encrypt (무료, 프로덕션 권장)

```bash
# Certbot 설치
apt-get install certbot python3-certbot-nginx

# 인증서 발급
certbot --nginx -d your-domain.com -d www.your-domain.com

# 자동 갱신 설정 (cron)
0 0 1 * * /usr/bin/certbot renew --quiet
```

#### 자체 서명 인증서 (개발/테스트용)

```bash
# 인증서 디렉토리 생성
mkdir -p /etc/nginx/ssl

# 자체 서명 인증서 생성
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/private.key \
  -out /etc/nginx/ssl/certificate.crt \
  -subj "/C=KR/ST=Seoul/L=Seoul/O=Company/CN=your-domain.com"

# Diffie-Hellman 파라미터 생성 (보안 강화)
openssl dhparam -out /etc/nginx/ssl/dhparam.pem 2048
```

### 2.2 Nginx SSL 설정

**파일:** `kms-portal-ui/nginx.conf`

```nginx
# HTTP → HTTPS 리다이렉트
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS 서버
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL 인증서
    ssl_certificate /etc/nginx/ssl/certificate.crt;
    ssl_certificate_key /etc/nginx/ssl/private.key;
    ssl_dhparam /etc/nginx/ssl/dhparam.pem;

    # SSL 프로토콜 (TLS 1.2, 1.3만 허용)
    ssl_protocols TLSv1.2 TLSv1.3;

    # 암호화 스위트 (강력한 암호만 사용)
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # SSL 세션 캐시 (성능 향상)
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # OCSP Stapling (인증서 검증 속도 향상)
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;

    # HSTS (HTTP Strict Transport Security)
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    # 기존 설정 유지...
    root /usr/share/nginx/html;
    index index.html;

    # Gzip 압축
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied expired no-cache no-store private auth;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml application/javascript application/json;

    # 보안 헤더
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';" always;

    # API 프록시
    location /api/ {
        proxy_pass http://backend:9000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # 정적 파일 캐싱
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA 라우팅
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 헬스 체크
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

### 2.3 SSL 보안 등급 확인

```bash
# SSL Labs 테스트 (온라인)
# https://www.ssllabs.com/ssltest/

# 로컬 테스트
openssl s_client -connect your-domain.com:443 -tls1_2
openssl s_client -connect your-domain.com:443 -tls1_3
```

---

## 3. Nginx 최적화

### 3.1 전역 설정

**파일:** `/etc/nginx/nginx.conf`

```nginx
# 워커 프로세스 (CPU 코어 수에 맞춤)
worker_processes auto;

# 워커당 최대 연결 수
events {
    worker_connections 4096;      # 기본 1024 → 4096
    use epoll;                    # Linux 최적화
    multi_accept on;              # 다중 연결 수락
}

http {
    # 파일 전송 최적화
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;

    # Keep-Alive 설정
    keepalive_timeout 65;
    keepalive_requests 1000;

    # 버퍼 크기
    client_body_buffer_size 128k;
    client_max_body_size 100m;    # 파일 업로드 크기
    client_header_buffer_size 1k;
    large_client_header_buffers 4 32k;

    # 프록시 버퍼
    proxy_buffer_size 128k;
    proxy_buffers 4 256k;
    proxy_busy_buffers_size 256k;

    # 타임아웃
    proxy_connect_timeout 90s;
    proxy_send_timeout 90s;
    proxy_read_timeout 300s;

    # 로그 포맷
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct=$upstream_connect_time '
                    'uht=$upstream_header_time urt=$upstream_response_time';

    access_log /var/log/nginx/access.log main buffer=16k flush=5s;
    error_log /var/log/nginx/error.log warn;

    # 응답 압축
    gzip on;
    gzip_comp_level 5;
    gzip_min_length 256;
    gzip_proxied any;
    gzip_vary on;
    gzip_types
        application/javascript
        application/json
        application/xml
        text/css
        text/javascript
        text/plain
        text/xml;

    include /etc/nginx/conf.d/*.conf;
}
```

### 3.2 로드 밸런싱 설정 (다중 백엔드)

```nginx
upstream backend_cluster {
    least_conn;                           # 최소 연결 방식

    server backend1:9000 weight=5;        # 가중치 부여
    server backend2:9000 weight=5;
    server backend3:9000 weight=3 backup; # 백업 서버

    keepalive 32;                         # 연결 유지
}

server {
    location /api/ {
        proxy_pass http://backend_cluster/api/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";   # keepalive 활성화
        # ... 기타 설정
    }
}
```

### 3.3 캐싱 설정

```nginx
# 프록시 캐시 영역 정의
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m
                 max_size=1g inactive=60m use_temp_path=off;

server {
    # 캐싱 가능한 API 응답
    location /api/v1/public/ {
        proxy_pass http://backend:9000;
        proxy_cache api_cache;
        proxy_cache_valid 200 10m;
        proxy_cache_valid 404 1m;
        proxy_cache_use_stale error timeout updating;
        add_header X-Cache-Status $upstream_cache_status;
    }
}
```

---

## 4. FastAPI/Uvicorn 최적화

### 4.1 Uvicorn 워커 설정

**파일:** `app/api/core/config.py`

```python
# 워커 수 계산: CPU 코어 × 2 + 1 (권장)
# 8코어 서버 기준: 8 × 2 + 1 = 17

class APISettings(BaseSettings):
    # 기본값
    WORKERS: int = 4

    # 규모별 권장값
    # 소규모 (100명): 4
    # 중규모 (500명): 8
    # 대규모 (1000명+): 16
```

**파일:** `app/api/main.py` (라인 554-584)

```python
# 프로덕션 설정
uvicorn.run(
    "app.api.main:app",
    host="0.0.0.0",
    port=api_settings.PORT,
    workers=api_settings.WORKERS,        # 워커 수
    limit_concurrency=1000,              # 동시 연결 제한
    limit_max_requests=10000,            # 워커당 최대 요청 후 재시작
    timeout_keep_alive=30,               # Keep-Alive 타임아웃
    access_log=False,                    # 프로덕션에서 비활성화 (성능)
)
```

### 4.2 Gunicorn + Uvicorn 조합 (권장)

대규모 환경에서는 Gunicorn을 프로세스 매니저로 사용:

```bash
# 설치
pip install gunicorn

# 실행
gunicorn app.api.main:app \
    --workers 8 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:9000 \
    --timeout 120 \
    --keep-alive 30 \
    --max-requests 10000 \
    --max-requests-jitter 1000 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile -
```

**Gunicorn 설정 파일:** `gunicorn.conf.py`

```python
# 바인딩
bind = "0.0.0.0:9000"

# 워커 설정
workers = 8                              # CPU × 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# 타임아웃
timeout = 120
keepalive = 30
graceful_timeout = 30

# 메모리 관리 (메모리 누수 방지)
max_requests = 10000
max_requests_jitter = 1000

# 로깅
accesslog = "-"
errorlog = "-"
loglevel = "warning"

# 프로세스 이름
proc_name = "hybridrag-api"

# 사전 로드 (메모리 공유)
preload_app = True
```

### 4.3 비동기 설정 최적화

**파일:** `app/api/main.py`

```python
import asyncio

# 이벤트 루프 최적화 (Linux)
if sys.platform != 'win32':
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
```

---

## 5. PostgreSQL 최적화

### 5.1 연결 풀 설정

**파일:** `app/api/main.py` (라인 111-125)

```python
# 현재 설정
db_pool = await asyncpg.create_pool(
    dsn,
    min_size=5,           # 최소 연결
    max_size=20,          # 최대 연결
    command_timeout=60    # 명령 타임아웃
)

# 규모별 권장 설정
# ┌────────────┬──────────┬──────────┬─────────────┐
# │ 규모       │ min_size │ max_size │ timeout     │
# ├────────────┼──────────┼──────────┼─────────────┤
# │ 소규모     │ 5        │ 20       │ 60          │
# │ 중규모     │ 10       │ 50       │ 60          │
# │ 대규모     │ 20       │ 100      │ 90          │
# └────────────┴──────────┴──────────┴─────────────┘

# 대규모 환경 설정 예시
db_pool = await asyncpg.create_pool(
    dsn,
    min_size=20,
    max_size=100,
    max_inactive_connection_lifetime=300,  # 유휴 연결 정리
    command_timeout=90,
    statement_cache_size=1024,             # 쿼리 캐시
)
```

### 5.2 PostgreSQL 서버 설정

**파일:** `postgresql.conf`

```ini
# 연결 설정
max_connections = 200                    # 최대 연결 (기본 100)
superuser_reserved_connections = 3

# 메모리 설정 (서버 메모리의 25%)
shared_buffers = 4GB                     # 16GB RAM 기준
effective_cache_size = 12GB              # 16GB RAM 기준
work_mem = 64MB                          # 복잡한 쿼리용
maintenance_work_mem = 512MB             # VACUUM, CREATE INDEX용

# WAL 설정
wal_buffers = 64MB
checkpoint_completion_target = 0.9
max_wal_size = 2GB
min_wal_size = 1GB

# 쿼리 플래너
random_page_cost = 1.1                   # SSD 사용 시
effective_io_concurrency = 200           # SSD 사용 시

# 로깅
log_min_duration_statement = 1000        # 1초 이상 쿼리 로깅
log_checkpoints = on
log_connections = on
log_disconnections = on
log_lock_waits = on

# 병렬 쿼리
max_parallel_workers_per_gather = 4
max_parallel_workers = 8
max_parallel_maintenance_workers = 4
```

### 5.3 pgvector 인덱스 최적화

```sql
-- IVFFlat 인덱스 (빠른 빌드, 근사 검색)
CREATE INDEX ON embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);  -- sqrt(행 수) 권장

-- HNSW 인덱스 (느린 빌드, 정확한 검색)
CREATE INDEX ON embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 검색 시 ef_search 파라미터
SET hnsw.ef_search = 100;  -- 정확도 vs 속도 트레이드오프
```

---

## 6. Neo4j 최적화

### 6.1 Neo4j 서버 설정

**파일:** `docker/docker-compose.yml` 또는 `neo4j.conf`

```yaml
# Docker Compose 환경 변수
neo4j:
  environment:
    # 메모리 설정 (서버 메모리의 50-70%)
    - NEO4J_server_memory_heap_initial__size=4G
    - NEO4J_server_memory_heap_max__size=8G
    - NEO4J_server_memory_pagecache_size=4G

    # 연결 설정
    - NEO4J_server_bolt_connection__keep__alive=30s
    - NEO4J_server_bolt_connection__keep__alive__for__requests=ALL

    # 트랜잭션 설정
    - NEO4J_db_transaction_timeout=60s
    - NEO4J_db_transaction_concurrent_maximum=0  # 무제한

    # 쿼리 캐시
    - NEO4J_db_query__cache__size=1000

    # 로깅
    - NEO4J_db_logs_query_enabled=INFO
    - NEO4J_db_logs_query_threshold=1000ms
```

### 6.2 Python 드라이버 설정

```python
from neo4j import AsyncGraphDatabase

# 연결 풀 설정
driver = AsyncGraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", password),
    max_connection_lifetime=3600,        # 연결 수명 (초)
    max_connection_pool_size=100,        # 풀 크기
    connection_acquisition_timeout=60,   # 연결 획득 타임아웃
    connection_timeout=30,               # 연결 타임아웃
)
```

---

## 7. LLM 서비스 최적화

### 7.1 Nemotron LLM (NIM)

**파일:** `docker/docker-compose.yml`

```yaml
nemotron-llm:
  environment:
    # 동시 처리 설정
    - NIM_MAX_NUM_SEQS=64            # 기본값, 최대 128까지
    - NIM_MAX_MODEL_LEN=8192         # 컨텍스트 길이

    # GPU 메모리 최적화
    - NIM_TENSOR_PARALLEL_SIZE=1     # GPU 병렬화 (다중 GPU 시)

    # 배치 설정
    - NIM_MAX_BATCH_SIZE=32          # 배치 크기

  # 공유 메모리 (GPU 통신)
  shm_size: '16gb'                   # 대규모: 32gb

  # 리소스 제한
  deploy:
    resources:
      limits:
        memory: 40G
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

### 7.2 Mistral NeMo (vLLM)

```yaml
mistral-nemo-coder:
  command: >
    --model mistralai/Mistral-Nemo-Instruct-2407
    --max-model-len 8192
    --gpu-memory-utilization 0.9      # GPU 메모리 사용률
    --max-num-batched-tokens 32768    # 배치 토큰 수
    --max-num-seqs 64                 # 동시 시퀀스
    --enable-chunked-prefill          # 청크 프리필 (메모리 효율)
    --disable-log-requests            # 요청 로깅 비활성화 (성능)
```

### 7.3 Embedding 서비스

```yaml
nemo-embedding:
  environment:
    - NIM_TRITON_PERFORMANCE_MODE=throughput  # 처리량 우선
    # 또는
    - NIM_TRITON_PERFORMANCE_MODE=latency     # 지연시간 우선

    # 배치 설정
    - NIM_MAX_BATCH_SIZE=64
```

---

## 8. Rate Limiting 조정

### 8.1 전역 Rate Limit 설정

**파일:** `app/api/core/config.py`

```python
class APISettings(BaseSettings):
    # 기본 Rate Limit
    RATE_LIMIT_DEFAULT: int = 120      # 분당 요청 수
    RATE_LIMIT_QUERY: int = 60         # 쿼리 분당 요청 수
    RATE_LIMIT_UPLOAD: int = 10        # 업로드 분당 요청 수

    # 규모별 권장값
    # ┌────────────┬─────────┬───────┬────────┐
    # │ 규모       │ DEFAULT │ QUERY │ UPLOAD │
    # ├────────────┼─────────┼───────┼────────┤
    # │ 소규모     │ 120     │ 60    │ 10     │
    # │ 중규모     │ 300     │ 150   │ 30     │
    # │ 대규모     │ 600     │ 300   │ 60     │
    # └────────────┴─────────┴───────┴────────┘
```

### 8.2 Vision API Rate Limit

**파일:** `app/api/middleware/vision_rate_limiter.py`

```python
@dataclass
class RateLimitConfig:
    # 요청 제한
    requests_per_minute: int = 20      # 중규모: 50, 대규모: 100
    requests_per_hour: int = 200       # 중규모: 500, 대규모: 1000
    requests_per_day: int = 1000       # 중규모: 3000, 대규모: 10000

    # 토큰 제한
    tokens_per_minute: int = 100000    # 중규모: 300000
    tokens_per_hour: int = 500000      # 중규모: 1500000

    # 비용 제한
    cost_per_hour: float = 10.0        # 중규모: 50.0
    cost_per_day: float = 50.0         # 중규모: 200.0

    # 버스트 허용
    burst_multiplier: float = 1.5      # 순간 허용 배율
```

### 8.3 사용자 등급별 Rate Limit

```python
# 사용자 등급별 설정 예시
RATE_LIMITS_BY_TIER = {
    "free": {
        "requests_per_minute": 20,
        "requests_per_day": 500,
    },
    "basic": {
        "requests_per_minute": 60,
        "requests_per_day": 3000,
    },
    "premium": {
        "requests_per_minute": 200,
        "requests_per_day": 10000,
    },
    "enterprise": {
        "requests_per_minute": 1000,
        "requests_per_day": -1,  # 무제한
    },
}
```

---

## 9. 백그라운드 작업 최적화

### 9.1 작업 큐 설정

**파일:** `app/api/ims_crawler/infrastructure/services/background_task_queue.py`

```python
# 현재 설정
task_queue = get_task_queue(max_concurrent=3)

# 규모별 권장값
# ┌────────────┬────────────────┬──────────────────────┐
# │ 규모       │ max_concurrent │ 비고                 │
# ├────────────┼────────────────┼──────────────────────┤
# │ 소규모     │ 3              │ 기본값               │
# │ 중규모     │ 5-8            │ CPU 코어 수 고려     │
# │ 대규모     │ 10-15          │ 별도 워커 서버 권장  │
# └────────────┴────────────────┴──────────────────────┘
```

### 9.2 작업 분리 (대규모 환경)

```python
# IMS 크롤링 전용 큐
ims_queue = get_task_queue(max_concurrent=3, name="ims")

# 문서 처리 전용 큐
document_queue = get_task_queue(max_concurrent=5, name="document")

# 일반 작업 큐
general_queue = get_task_queue(max_concurrent=5, name="general")
```

### 9.3 Lock Manager 설정

**파일:** `app/api/core/concurrency.py`

```python
# 현재 설정
_session_locks = AsyncLockManager(max_locks=10000)
_user_locks = AsyncLockManager(max_locks=5000)
_document_locks = AsyncLockManager(max_locks=20000)

# 대규모 환경 설정
_session_locks = AsyncLockManager(max_locks=50000)
_user_locks = AsyncLockManager(max_locks=20000)
_document_locks = AsyncLockManager(max_locks=100000)
```

---

## 10. Docker/컨테이너 최적화

### 10.1 리소스 제한 설정

**파일:** `docker/docker-compose.yml`

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G

    # 헬스체크 최적화
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  postgres:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

    # 공유 메모리 (PostgreSQL 성능)
    shm_size: '256mb'

  neo4j:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 8G
```

### 10.2 다중 인스턴스 (Docker Swarm/Kubernetes)

```yaml
# Docker Compose with replicas
services:
  backend:
    image: hybridrag-backend:latest
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
```

### 10.3 Kubernetes 설정 예시

```yaml
# kubernetes/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hybridrag-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: hybridrag-backend
  template:
    spec:
      containers:
      - name: backend
        image: hybridrag-backend:latest
        resources:
          requests:
            cpu: "1000m"
            memory: "2Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 9000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 9000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: hybridrag-backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: hybridrag-backend
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## 11. 모니터링 및 로깅

### 11.1 Prometheus 메트릭

```python
# app/api/main.py
from prometheus_client import Counter, Histogram, Gauge
from prometheus_fastapi_instrumentator import Instrumentator

# 메트릭 정의
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency')
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active WebSocket connections')

# FastAPI 계측
Instrumentator().instrument(app).expose(app)
```

### 11.2 로깅 설정

```python
# app/api/core/logging_config.py
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "level": "INFO"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/app.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "json",
            "level": "WARNING"
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"]
    }
}
```

### 11.3 Grafana 대시보드

주요 모니터링 지표:
- 요청 처리량 (requests/sec)
- 응답 시간 (p50, p95, p99)
- 에러율 (4xx, 5xx)
- CPU/메모리 사용량
- 데이터베이스 연결 수
- LLM 응답 시간

---

## 12. 규모별 권장 설정

### 12.1 소규모 (동시 100명 이하)

```yaml
# 현재 기본 설정 유지
Uvicorn Workers: 4
PostgreSQL Pool: 5-20
Background Tasks: 3
LLM Sequences: 64
```

### 12.2 중규모 (동시 100-500명)

| 항목 | 설정값 | 변경 파일 |
|------|--------|----------|
| Uvicorn Workers | 8 | `config.py` |
| PostgreSQL min_size | 10 | `main.py` |
| PostgreSQL max_size | 50 | `main.py` |
| Background Tasks | 5 | `background_task_queue.py` |
| Nginx worker_connections | 2048 | `nginx.conf` |
| Rate Limit Default | 300/min | `config.py` |

### 12.3 대규모 (동시 500-1000명)

| 항목 | 설정값 | 비고 |
|------|--------|------|
| Uvicorn Workers | 16 | Gunicorn 사용 권장 |
| PostgreSQL min_size | 20 | |
| PostgreSQL max_size | 100 | |
| Background Tasks | 10 | 작업 분리 권장 |
| Nginx worker_connections | 4096 | |
| LLM Sequences | 128 | GPU 메모리 확인 |
| Rate Limit Default | 600/min | |
| 로드 밸런서 | 필수 | Nginx upstream |
| 캐시 서버 | 권장 | Redis 추가 |

### 12.4 엔터프라이즈 (동시 1000명 이상)

```
┌─────────────────────────────────────────────────────────────┐
│                    권장 아키텍처                              │
├─────────────────────────────────────────────────────────────┤
│  Load Balancer (Nginx/HAProxy/Cloud LB)                     │
│              │                                              │
│    ┌─────────┼─────────┐                                    │
│    ▼         ▼         ▼                                    │
│  Backend   Backend   Backend  (3-10 인스턴스)                │
│    │         │         │                                    │
│    └─────────┼─────────┘                                    │
│              │                                              │
│    ┌─────────┼─────────┐                                    │
│    ▼         ▼         ▼                                    │
│  Redis    PostgreSQL  Neo4j   (각각 고가용성 구성)           │
│ (캐시)    (Primary/   (Cluster)                             │
│           Replica)                                          │
│              │                                              │
│    ┌─────────┼─────────┐                                    │
│    ▼         ▼         ▼                                    │
│  LLM-1    LLM-2     LLM-3    (다중 GPU 서버)                │
└─────────────────────────────────────────────────────────────┘

필수 구성요소:
- Kubernetes 또는 Docker Swarm
- 자동 스케일링 (HPA)
- 분산 캐시 (Redis Cluster)
- 데이터베이스 복제
- 중앙 로깅 (ELK/Loki)
- 모니터링 (Prometheus/Grafana)
```

---

## 체크리스트

### 성능 개선 전 확인사항

- [ ] 현재 병목 지점 식별 (모니터링 데이터 분석)
- [ ] 하드웨어 리소스 확인 (CPU, RAM, GPU, SSD)
- [ ] 네트워크 대역폭 확인
- [ ] 예상 동시 사용자 수 산정

### 설정 변경 후 확인사항

- [ ] 부하 테스트 실행 (k6, locust, wrk)
- [ ] 응답 시간 측정 (p50, p95, p99)
- [ ] 에러율 모니터링
- [ ] 메모리 누수 확인
- [ ] 로그 확인

### SSL 설정 확인사항

- [ ] 인증서 유효성 확인
- [ ] SSL Labs 테스트 (A+ 등급 목표)
- [ ] HSTS 헤더 확인
- [ ] 인증서 자동 갱신 설정

---

## 참고 자료

- [Uvicorn Settings](https://www.uvicorn.org/settings/)
- [Gunicorn Settings](https://docs.gunicorn.org/en/stable/settings.html)
- [Nginx Tuning](https://www.nginx.com/blog/tuning-nginx/)
- [PostgreSQL Tuning](https://wiki.postgresql.org/wiki/Tuning_Your_PostgreSQL_Server)
- [Neo4j Performance](https://neo4j.com/docs/operations-manual/current/performance/)
- [vLLM Performance](https://docs.vllm.ai/en/latest/serving/performance.html)
