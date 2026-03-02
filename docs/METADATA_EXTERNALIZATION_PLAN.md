# 메타데이터 외부화 계획 (Metadata Externalization Plan)

## 1. 현황 분석

### 1.1 문제점
현재 시스템에 **143개의 하드코딩된 메타데이터 항목**이 4개 서비스에 분산되어 있습니다.

| 서비스 | 하드코딩 항목 | 개수 | 영향도 |
|--------|-------------|------|--------|
| `opencode_service.py` | `_CORE_TERMS`, `query_patterns` | 26개 | 높음 |
| `summary_search_service.py` | `module_ranges`, `product_map` | 50개 | 높음 |
| `query_expansion_service.py` | 동의어 매핑 (JA/KO/EN) | 56개 | 중간 |
| `knowledge_graph_service.py` | `ENTITY_PATTERNS` | 11개 | 낮음 |

### 1.2 주요 문제 사례
- **ADRDSSU 검색 실패**: `ADRDSSU` → `Utility-Reference-Guide` 매핑 누락
- **새 제품 추가 시 배포 필수**: 코드 수정 없이 용어 추가 불가
- **다국어 확장 어려움**: 언어별 동의어가 코드에 분산

---

## 2. 목표 아키텍처

### 2.1 PostgreSQL 테이블 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    kms_metadata (Schema)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────┐    ┌─────────────────────┐            │
│  │ domain_glossary     │    │ document_mappings   │            │
│  ├─────────────────────┤    ├─────────────────────┤            │
│  │ id (PK)             │    │ id (PK)             │            │
│  │ term                │    │ keyword             │            │
│  │ full_name           │    │ document_pattern    │            │
│  │ description         │    │ category            │            │
│  │ category            │    │ priority            │            │
│  │ translations (JSONB)│    │ active              │            │
│  │ active              │    │ created_at          │            │
│  │ created_at          │    │ updated_at          │            │
│  │ updated_at          │    └─────────────────────┘            │
│  └─────────────────────┘                                        │
│                                                                 │
│  ┌─────────────────────┐    ┌─────────────────────┐            │
│  │ error_code_ranges   │    │ synonyms            │            │
│  ├─────────────────────┤    ├─────────────────────┤            │
│  │ id (PK)             │    │ id (PK)             │            │
│  │ module              │    │ base_term           │            │
│  │ range_start         │    │ synonym             │            │
│  │ range_end           │    │ language            │            │
│  │ file_path           │    │ domain              │            │
│  │ category            │    │ confidence          │            │
│  │ description         │    │ active              │            │
│  │ active              │    │ created_at          │            │
│  │ created_at          │    └─────────────────────┘            │
│  │ updated_at          │                                        │
│  └─────────────────────┘                                        │
│                                                                 │
│  ┌─────────────────────┐    ┌─────────────────────┐            │
│  │ visual_keywords     │    │ entity_patterns     │            │
│  ├─────────────────────┤    ├─────────────────────┤            │
│  │ id (PK)             │    │ id (PK)             │            │
│  │ keyword             │    │ entity_type         │            │
│  │ language            │    │ regex_pattern       │            │
│  │ category            │    │ language            │            │
│  │ active              │    │ confidence          │            │
│  │ created_at          │    │ description         │            │
│  └─────────────────────┘    │ active              │            │
│                              │ created_at          │            │
│                              └─────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 서비스 아키텍처

```
┌──────────────────────────────────────────────────────────────────┐
│                     Application Layer                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  opencode_service    summary_search    query_expansion            │
│        │                   │                 │                    │
│        └───────────────────┼─────────────────┘                    │
│                            │                                      │
│                            ▼                                      │
│              ┌─────────────────────────┐                         │
│              │  MetadataConfigService  │  ◄── 신규 서비스         │
│              ├─────────────────────────┤                         │
│              │ - get_glossary_terms()  │                         │
│              │ - get_doc_mappings()    │                         │
│              │ - get_error_ranges()    │                         │
│              │ - get_synonyms()        │                         │
│              │ - get_visual_keywords() │                         │
│              │ - refresh_cache()       │                         │
│              └───────────┬─────────────┘                         │
│                          │                                        │
│              ┌───────────▼─────────────┐                         │
│              │     Redis Cache         │  ◄── RedisCacheService  │
│              │   (TTL: 5min, prefix:   │      + InMemory 폴백    │
│              │    "metadata:")         │                         │
│              └───────────┬─────────────┘                         │
│                          │                                        │
├──────────────────────────┼───────────────────────────────────────┤
│                          │     Infrastructure Layer               │
│              ┌───────────▼─────────────┐                         │
│              │ MetadataRepository      │                         │
│              │ (PostgreSQL asyncpg)    │                         │
│              └─────────────────────────┘                         │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 테이블 상세 설계

### 3.1 domain_glossary (도메인 용어 사전)

```sql
CREATE TABLE IF NOT EXISTS domain_glossary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50) DEFAULT 'system',  -- system, utility, vsam, batch
    translations JSONB DEFAULT '{}',         -- {"ko": "...", "ja": "..."}
    equivalent_to VARCHAR(255),              -- IBM/mainframe equivalent
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_glossary_term ON domain_glossary(term);
CREATE INDEX idx_glossary_category ON domain_glossary(category);
CREATE INDEX idx_glossary_active ON domain_glossary(active) WHERE active = TRUE;
```

**초기 데이터 예시:**
```sql
INSERT INTO domain_glossary (term, full_name, description, category, equivalent_to) VALUES
('TJES', 'Tmax Job Entry Subsystem', 'Batch job scheduling system', 'system', 'JES2/JES3'),
('TACF', 'Tmax Access Control Facility', 'Security and access control', 'system', 'RACF'),
('HiDB', 'Hierarchical Database', 'IMS-compatible database', 'database', 'IMS DB'),
('ADRDSSU', 'ADRDSSU Utility', 'Dataset dump/restore utility', 'utility', 'ADRDSSU'),
('KSDS', 'Key Sequenced Data Set', 'VSAM key-ordered dataset', 'vsam', 'VSAM KSDS'),
('ESDS', 'Entry Sequenced Data Set', 'VSAM entry-ordered dataset', 'vsam', 'VSAM ESDS');
```

### 3.2 document_mappings (키워드-문서 매핑)

```sql
CREATE TABLE IF NOT EXISTS document_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword VARCHAR(100) NOT NULL,
    document_pattern VARCHAR(255) NOT NULL,  -- 파일명에서 검색할 패턴
    category VARCHAR(50) DEFAULT 'product',  -- product, utility, config
    priority INT DEFAULT 100,                -- 매칭 우선순위 (낮을수록 우선)
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(keyword, document_pattern)
);

CREATE INDEX idx_doc_mapping_keyword ON document_mappings(keyword);
CREATE INDEX idx_doc_mapping_active ON document_mappings(active) WHERE active = TRUE;
```

**초기 데이터 예시:**
```sql
INSERT INTO document_mappings (keyword, document_pattern, category, priority) VALUES
-- 제품명 → 문서 패턴
('HiDB', 'HiDB', 'product', 10),
('HIDB', 'HiDB', 'product', 10),
('TJES', 'TJES', 'product', 10),
('TACF', 'TACF', 'product', 10),
('OSC', 'OSC', 'product', 10),
('BASE', 'Base', 'product', 10),

-- 유틸리티 → Utility 문서
('ADRDSSU', 'Utility', 'utility', 20),
('IDCAMS', 'Utility', 'utility', 20),
('IEBCOPY', 'Utility', 'utility', 20),
('IEBGENER', 'Utility', 'utility', 20),
('DFSORT', 'Utility', 'utility', 20),
('SORT', 'Utility', 'utility', 20),

-- 설정 → Configuration 문서
('ds.conf', 'Configuration', 'config', 30),
('tjes.conf', 'Configuration', 'config', 30),
('osc.conf', 'Configuration', 'config', 30);
```

### 3.3 error_code_ranges (에러 코드 범위)

```sql
CREATE TABLE IF NOT EXISTS error_code_ranges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module VARCHAR(50) NOT NULL,        -- BASE, BATCH, TACF, AIM, NDB
    range_start INT NOT NULL,
    range_end INT NOT NULL,
    file_path VARCHAR(255) NOT NULL,    -- error-codes/BASE-5000.md
    category VARCHAR(50),
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(module, range_start, range_end)
);

CREATE INDEX idx_error_range_module ON error_code_ranges(module);
CREATE INDEX idx_error_range_start ON error_code_ranges(range_start);
```

**초기 데이터 예시:**
```sql
INSERT INTO error_code_ranges (module, range_start, range_end, file_path, category) VALUES
('BASE', 0, 999, 'BASE-0.md', 'system'),
('BASE', 1000, 1999, 'BASE-1000.md', 'dataset'),
('BASE', 5000, 5999, 'BASE-5000.md', 'allocation'),
('BATCH', 9000, 9999, 'BATCH-9000.md', 'batch'),
('TACF', 18000, 18999, 'TACF-18000.md', 'security'),
('AIM', 21000, 21999, 'AIM-21000.md', 'integration');
```

### 3.4 synonyms (동의어)

```sql
CREATE TABLE IF NOT EXISTS synonyms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    base_term VARCHAR(255) NOT NULL,
    synonym VARCHAR(255) NOT NULL,
    language VARCHAR(10) NOT NULL,      -- ja, ko, en
    domain VARCHAR(50) DEFAULT 'general', -- general, technical, product
    confidence FLOAT DEFAULT 1.0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(base_term, synonym, language)
);

CREATE INDEX idx_synonyms_base_term ON synonyms(base_term);
CREATE INDEX idx_synonyms_language ON synonyms(language);
```

### 3.5 visual_keywords (시각 키워드)

```sql
CREATE TABLE IF NOT EXISTS visual_keywords (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword VARCHAR(100) NOT NULL,
    language VARCHAR(10) NOT NULL,      -- ja, ko, en
    category VARCHAR(50) DEFAULT 'diagram', -- diagram, table, chart, image
    weight FLOAT DEFAULT 1.0,           -- 가중치 (Vision LLM 라우팅용)
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(keyword, language)
);

CREATE INDEX idx_visual_kw_language ON visual_keywords(language);
CREATE INDEX idx_visual_kw_category ON visual_keywords(category);
```

**초기 데이터 예시:**
```sql
INSERT INTO visual_keywords (keyword, language, category, weight) VALUES
-- 일본어
('図', 'ja', 'diagram', 1.0),
('プロセス図', 'ja', 'diagram', 1.2),
('フローチャート', 'ja', 'diagram', 1.2),
('テーブル', 'ja', 'table', 1.0),
('表', 'ja', 'table', 1.0),
('フォーマット', 'ja', 'format', 0.8),
('チャート', 'ja', 'chart', 1.0),
('画像', 'ja', 'image', 1.0),

-- 한국어
('그림', 'ko', 'diagram', 1.0),
('프로세스도', 'ko', 'diagram', 1.2),
('플로우차트', 'ko', 'diagram', 1.2),
('테이블', 'ko', 'table', 1.0),
('표', 'ko', 'table', 1.0),

-- 영어
('diagram', 'en', 'diagram', 1.0),
('flowchart', 'en', 'diagram', 1.2),
('process', 'en', 'diagram', 0.8),
('table', 'en', 'table', 1.0),
('chart', 'en', 'chart', 1.0),
('format', 'en', 'format', 0.8),
('structure', 'en', 'format', 0.8);
```

---

## 4. 서비스 설계

### 4.1 MetadataConfigService

```python
# app/api/services/metadata_config_service.py

class MetadataConfigService:
    """
    중앙 메타데이터 설정 서비스
    - PostgreSQL에서 설정 로드
    - Redis 캐시로 성능 최적화 (InMemory 폴백)
    - 주기적 리프레시 지원
    """

    # Cache key prefix for metadata
    CACHE_PREFIX = "metadata:"
    CACHE_TTL = timedelta(minutes=5)

    def __init__(self, repository):
        self._repo = repository
        self._cache = None  # Lazy loaded (Redis or InMemory)

    # === Glossary ===
    async def get_glossary_term(self, term: str) -> Optional[Dict]:
        """단일 용어 조회"""

    async def get_all_glossary_terms(self) -> Dict[str, Dict]:
        """전체 용어 사전 (캐시됨)"""

    # === Document Mappings ===
    async def get_document_pattern(self, keyword: str) -> Optional[str]:
        """키워드 → 문서 패턴 매핑"""

    async def get_all_document_mappings(self) -> Dict[str, str]:
        """전체 매핑 (캐시됨)"""

    # === Error Code Ranges ===
    async def get_error_file(self, error_code: int) -> Optional[str]:
        """에러 코드 → 파일 경로"""

    async def get_all_error_ranges(self) -> List[Dict]:
        """전체 범위 (캐시됨)"""

    # === Synonyms ===
    async def get_synonyms(self, term: str, language: str) -> List[str]:
        """동의어 목록"""

    # === Visual Keywords ===
    async def get_visual_keywords(self, language: str = None) -> List[str]:
        """시각 키워드 목록"""

    async def is_visual_keyword(self, text: str) -> Tuple[bool, float]:
        """시각 키워드 포함 여부 및 가중치"""

    # === Cache Management ===
    async def refresh_cache(self):
        """캐시 강제 리프레시"""

    async def invalidate(self, table: str = None):
        """특정 테이블 또는 전체 캐시 무효화"""
```

### 4.2 MetadataRepository

```python
# app/api/infrastructure/postgres/metadata_repository.py

class MetadataRepository:
    """PostgreSQL 메타데이터 저장소"""

    async def _ensure_tables(self):
        """모든 메타데이터 테이블 생성"""

    # CRUD for each table
    async def get_glossary_terms(self, active_only=True) -> List[Dict]
    async def add_glossary_term(self, term: str, full_name: str, ...) -> str
    async def update_glossary_term(self, term: str, **kwargs) -> bool

    async def get_document_mappings(self, active_only=True) -> List[Dict]
    async def add_document_mapping(self, keyword: str, pattern: str, ...) -> str

    async def get_error_ranges(self, active_only=True) -> List[Dict]
    async def find_error_range(self, error_code: int) -> Optional[Dict]

    async def get_synonyms(self, language: str = None) -> List[Dict]
    async def add_synonym(self, base_term: str, synonym: str, lang: str) -> str

    async def get_visual_keywords(self, language: str = None) -> List[Dict]
```

---

## 5. 마이그레이션 계획

### Phase 1: 인프라 구축 (1일) ✅ 완료
1. [x] `MetadataRepository` 클래스 생성 → `app/api/infrastructure/postgres/metadata_repository.py`
2. [x] 모든 테이블 DDL 작성 → `scripts/migrations/005_metadata_tables.sql`
3. [x] `MetadataConfigService` 기본 구현 → `app/api/services/metadata_config_service.py`
4. [x] Pydantic 모델 작성 → `app/api/models/metadata.py`
5. [x] 단위 테스트 작성 → `tests/api/test_metadata_service.py`

### Phase 2: 초기 데이터 마이그레이션 (1일) ✅ 완료
1. [x] 기존 하드코딩 데이터 → SQL INSERT 스크립트 (scripts/migrations/005_metadata_tables.sql)
2. [x] `domain_glossary` 초기 데이터 (26개 용어)
3. [x] `document_mappings` 초기 데이터 (39개 매핑)
4. [x] `error_code_ranges` 초기 데이터 (35개 범위)
5. [x] `visual_keywords` 초기 데이터 (51개 키워드)
6. [x] `synonyms` 초기 데이터 (50개 동의어)

### Phase 3: 서비스 통합 (2일) ✅ 완료
1. [x] `opencode_service.py` 수정
   - `_CORE_TERMS` → `metadata_service.get_all_glossary_terms()` ✅
   - `query_patterns` → `metadata_service.find_document_for_keyword()` ✅
   - `visual_keywords` → `metadata_service.is_visual_keyword()` ✅
   - Fallback 로직 유지 (DB 실패 시 하드코딩 사용) ✅

2. [x] `summary_search_service.py` 수정
   - `module_ranges` → `metadata_service.get_error_file()` ✅
   - `product_map` → `metadata_service.get_document_pattern()` ✅
   - Fallback 로직 유지 ✅

3. [x] `query_expansion_service.py` 수정
   - `JA_SYNONYMS`, `KO_SYNONYMS`, `EN_SYNONYMS` → `metadata_service.get_all_synonyms()` ✅
   - `expand_async()` 메서드 추가 (DB 로드 포함) ✅
   - `get_query_expansion_service_async()` 팩토리 함수 추가 ✅
   - Fallback 로직 유지 ✅

### Phase 4: 테스트 및 검증 (1일) ✅ 완료
1. [x] PostgreSQL 마이그레이션 실행 (005_metadata_tables.sql)
   - domain_glossary: 25 records
   - document_mappings: 38 records
   - error_code_ranges: 35 records
   - synonyms: 49 records
   - visual_keywords: 49 records
   - **총 196 records**
2. [x] Redis 캐시 통합
   - `RedisCacheService` 사용 (기존 IMS Crawler와 공유)
   - 캐시 키 프리픽스: `metadata:`
   - TTL: 5분 (300초)
   - InMemory 폴백 지원
3. [x] 단위 테스트 업데이트 (Redis 캐시 모킹)
4. [x] 롤백 계획 확인 (DB 실패 시 하드코딩 폴백)

---

## 6. API 엔드포인트 (관리용)

```
POST   /api/v1/admin/metadata/glossary          # 용어 추가
GET    /api/v1/admin/metadata/glossary          # 용어 목록
PUT    /api/v1/admin/metadata/glossary/{term}   # 용어 수정
DELETE /api/v1/admin/metadata/glossary/{term}   # 용어 삭제

POST   /api/v1/admin/metadata/mappings          # 매핑 추가
GET    /api/v1/admin/metadata/mappings          # 매핑 목록

POST   /api/v1/admin/metadata/cache/refresh     # 캐시 리프레시
```

---

## 7. 예상 효과

| 항목 | Before | After |
|------|--------|-------|
| 새 용어 추가 | 코드 수정 + 배포 | DB INSERT만 |
| 매핑 수정 | 코드 수정 + 배포 | DB UPDATE만 |
| 다국어 확장 | 코드 수정 | translations JSONB 업데이트 |
| 변경 이력 | 추적 불가 | created_at, updated_at 자동 |
| 테스트 | 전체 재테스트 | 설정만 검증 |

---

## 8. 파일 구조

```
app/api/
├── infrastructure/
│   └── postgres/
│       └── metadata_repository.py    # 신규
├── services/
│   └── metadata_config_service.py    # 신규
├── routers/
│   └── admin_metadata.py             # 신규 (관리 API)
└── models/
    └── metadata.py                   # 신규 (Pydantic 모델)

scripts/
└── migrations/
    └── 005_metadata_tables.sql       # 신규 (DDL + 초기 데이터)
```

---

## 9. 롤백 계획

문제 발생 시:
1. `MetadataConfigService` 에서 DB 조회 실패 → 기존 하드코딩 fallback
2. 캐시 무효화 → 즉시 DB에서 재로드
3. 테이블 삭제 → 기존 코드로 자동 복원 (하드코딩 유지)

```python
# 예시: fallback 로직
async def get_glossary_term(self, term: str) -> Optional[Dict]:
    try:
        return await self._load_from_db(term)
    except Exception:
        # Fallback to hardcoded
        return self._HARDCODED_TERMS.get(term)
```

---

## 10. 승인 및 진행

- [x] 계획 검토 완료
- [x] Phase 1 시작 승인
- [x] **전체 완료: 2026-01-29** (Phase 1-4)

---

## 11. 구현 완료 요약 ✅

### 생성된 파일
| 파일 | 용도 |
|------|------|
| `app/api/infrastructure/postgres/metadata_repository.py` | PostgreSQL 저장소 |
| `app/api/services/metadata_config_service.py` | 중앙 메타데이터 서비스 (Redis 캐시) |
| `app/api/models/metadata.py` | Pydantic 모델 |
| `scripts/migrations/005_metadata_tables.sql` | DDL + 초기 데이터 |
| `tests/api/test_metadata_service.py` | 단위 테스트 |

### 수정된 파일
| 파일 | 변경 사항 |
|------|----------|
| `opencode_service.py` | MetadataConfigService 연동, 폴백 로직 |
| `summary_search_service.py` | 에러 코드/문서 패턴 DB 조회 |
| `query_expansion_service.py` | 동의어 DB 로드, async 메서드 추가 |

### 캐시 아키텍처
```
요청 → MetadataConfigService._cache_get(key)
         ↓
    Redis 캐시 조회 (key: "metadata:{cache_key}")
         ↓ miss
    PostgreSQL 조회 → _cache_set(key, value, TTL=5min)
         ↓ fail
    Fallback 하드코딩 값 반환
```

### Redis 키 패턴
| 키 | 용도 |
|----|------|
| `metadata:glossary_all` | 전체 용어 사전 |
| `metadata:mappings_all` | 전체 문서 매핑 |
| `metadata:error_ranges_all` | 전체 에러 범위 |
| `metadata:synonyms_{lang}` | 언어별 동의어 |
| `metadata:visual_kw_{lang}` | 언어별 시각 키워드 |

---

*작성일: 2026-01-29*
*완료일: 2026-01-29*
*작성자: Claude Code*
