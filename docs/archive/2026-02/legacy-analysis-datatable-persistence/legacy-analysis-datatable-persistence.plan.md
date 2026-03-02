# Plan: Legacy Modernization - Analysis Results Data Table & PostgreSQL Persistence

## Overview

| Item | Value |
|------|-------|
| Feature | legacy-analysis-datatable-persistence |
| Phase | Plan |
| Priority | High |
| Scope | Backend (PostgreSQL + API) + Frontend (Data Table + Popup Detail) |
| Estimated Files | ~12 files (6 backend, 6 frontend) |

## Problem Statement

현재 레거시 모더나이제이션 분석 결과에는 3가지 핵심 문제가 있음:

1. **결과 표시 방식**: 분석 결과가 Accordion/Card 형태로 표시되어 대량 파일 비교가 어려움
2. **데이터 영속성 없음**: 분석 결과가 Redis/메모리에만 저장 (TTL 24시간) → 재시작 시 소멸
3. **상세 보기 UX**: 결과 확인 시 같은 페이지 내 스크롤 → 다중 결과 비교 불편

## Goal

1. 분석 결과를 **Data Table (Data Grid)** 형식으로 화면 하단에 출력
2. Data Table의 **row 클릭 시 새 브라우저 팝업**으로 상세 분석 내용 표시
3. 모든 분석 결과를 **PostgreSQL에 영구 저장**하여 재사용 가능하게 구현

## Architecture Decision

### 현재 상태 (AS-IS)

```
분석 시작 → Redis/Memory 저장 (TTL 24h) → API 조회 → Accordion UI
                                                    ↓
                                              같은 페이지 내 확장/축소
```

### 목표 상태 (TO-BE)

```
분석 시작 → Redis 임시 저장 → 분석 완료 → PostgreSQL 영구 저장
                                              ↓
                                   API: GET /legacy/analyses (목록)
                                   API: GET /legacy/analyses/{id} (상세)
                                              ↓
                                   화면 하단 Data Table (정렬/필터/페이지네이션)
                                              ↓
                                   Row 클릭 → window.open() 팝업
                                              ↓
                                   /legacy/analysis/{id}/detail (독립 페이지)
```

### 기술 선택

| 항목 | 선택 | 이유 |
|------|------|------|
| DB | PostgreSQL (asyncpg) | 기존 인프라 재사용, JSONB 지원 |
| ORM | Raw SQL (asyncpg) | 프로젝트 기존 패턴 준수 |
| Data Table | React 자체 구현 | 외부 라이브러리 의존 최소화, 기존 CSS 체계 활용 |
| Popup | window.open + React Route | 독립 URL → 북마크/공유 가능 |

## Database Design

### 테이블: `legacy_analyses`

```sql
CREATE TABLE IF NOT EXISTS legacy_analyses (
    id UUID PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    batch_id UUID,                              -- 배치 분석 그룹 ID (nullable)

    -- 소스 정보
    file_name VARCHAR(500) NOT NULL,
    asset_type VARCHAR(20) NOT NULL,            -- cobol, jcl, map, asm
    source_code TEXT,                           -- 원본 소스 (선택적 저장)
    loc_count INTEGER DEFAULT 0,

    -- 타겟 정보
    target_product VARCHAR(100),
    target_version VARCHAR(50),
    vendors JSONB DEFAULT '[]',

    -- 분석 결과 요약
    status VARCHAR(30) NOT NULL DEFAULT 'completed', -- completed, failed
    total_features INTEGER DEFAULT 0,
    supported_count INTEGER DEFAULT 0,
    incompatible_count INTEGER DEFAULT 0,
    support_rate FLOAT DEFAULT 0.0,
    risk_high INTEGER DEFAULT 0,
    risk_medium INTEGER DEFAULT 0,
    risk_low INTEGER DEFAULT 0,

    -- 상세 결과 (JSONB)
    incompatibility_report JSONB,              -- IncompatibilityReport 전체
    reports JSONB DEFAULT '{}',                -- 9개 Report 타입별 내용
    workspace_snapshot JSONB,                  -- WorkspaceState 스냅샷

    -- 메타데이터
    analysis_duration_seconds FLOAT,
    pipeline_status VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_legacy_analyses_user_id ON legacy_analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_legacy_analyses_batch_id ON legacy_analyses(batch_id);
CREATE INDEX IF NOT EXISTS idx_legacy_analyses_created_at ON legacy_analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_legacy_analyses_asset_type ON legacy_analyses(asset_type);
CREATE INDEX IF NOT EXISTS idx_legacy_analyses_status ON legacy_analyses(status);
```

### 설계 포인트

- **요약 컬럼 분리**: `support_rate`, `risk_high` 등 → Data Table 정렬/필터용 (JSONB 내부 조회 비용 절감)
- **JSONB 상세 데이터**: `incompatibility_report`, `reports`, `workspace_snapshot` → 팝업 상세 페이지용
- **source_code TEXT**: 선택적 저장 (재분석 가능하도록, 옵션 플래그로 제어)
- **batch_id**: 배치 분석 시 그룹핑 조회 지원

## Implementation Plan

### Phase 1: Backend - PostgreSQL Repository (신규)

**새 파일**: `app/api/infrastructure/postgres/legacy_analysis_repository.py`

기존 패턴 준수 (asyncpg raw SQL):
- `initialize()`: CREATE TABLE IF NOT EXISTS
- `save_analysis()`: INSERT 분석 결과
- `get_analysis()`: SELECT by ID (상세)
- `list_analyses()`: SELECT with pagination, sort, filter
- `delete_analysis()`: DELETE by ID
- `get_batch_analyses()`: SELECT by batch_id

```python
class LegacyAnalysisRepository:
    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def initialize(self):
        """Create table if not exists"""

    async def save_analysis(self, analysis_data: dict) -> str:
        """Save completed analysis to PostgreSQL"""

    async def get_analysis(self, analysis_id: str) -> Optional[dict]:
        """Get full analysis detail (for popup page)"""

    async def list_analyses(
        self, user_id: str, page: int = 1, limit: int = 20,
        sort_by: str = "created_at", sort_order: str = "desc",
        asset_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> Tuple[List[dict], int]:
        """List analyses with pagination (for Data Table)"""

    async def delete_analysis(self, analysis_id: str, user_id: str) -> bool:
        """Delete analysis (소프트 삭제 or 하드 삭제)"""
```

### Phase 2: Backend - Analysis Service 연동

**변경 파일**: `app/api/legacy_modernization/services/analysis_service.py`

분석 완료 시점에 PostgreSQL 저장 로직 추가:

```python
# 기존 pipeline 완료 콜백에 추가
async def _on_analysis_completed(self, analysis_id, workspace):
    # 기존: Redis에만 저장
    # 추가: PostgreSQL에 영구 저장
    await self.legacy_repo.save_analysis({
        "id": analysis_id,
        "user_id": session.tenant_id,
        "file_name": workspace.file_name,
        "asset_type": workspace.asset_type,
        "support_rate": workspace.support_rate,
        "incompatibility_report": workspace.incompatibility_report,
        "reports": session.reports,
        ...
    })
```

### Phase 3: Backend - 목록/상세 API 엔드포인트

**변경 파일**: `app/api/legacy_modernization/routers/analysis.py`

새 엔드포인트 추가:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/legacy/analyses` | GET | 분석 결과 목록 (Data Table용, 페이지네이션) |
| `/legacy/analyses/{id}` | GET | 분석 결과 상세 (팝업 페이지용) |
| `/legacy/analyses/{id}` | DELETE | 분석 결과 삭제 |

```python
@router.get("/analyses")
async def list_analyses(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    asset_type: Optional[str] = Query(None),
    current_user = Depends(get_current_user)
):
    """Data Table용 분석 결과 목록"""

@router.get("/analyses/{analysis_id}")
async def get_analysis_detail(
    analysis_id: str,
    current_user = Depends(get_current_user)
):
    """팝업 상세 페이지용 분석 결과"""
```

### Phase 4: Backend - Pydantic 스키마 추가

**변경 파일**: `app/api/legacy_modernization/routers/schemas.py`

```python
class AnalysisListItem(BaseModel):
    """Data Table row 표시용"""
    id: str
    file_name: str
    asset_type: str
    status: str
    total_features: int
    supported_count: int
    incompatible_count: int
    support_rate: float
    risk_high: int
    risk_medium: int
    risk_low: int
    target_product: Optional[str]
    created_at: datetime

class AnalysisListResponse(BaseModel):
    """Data Table 페이지네이션 응답"""
    items: List[AnalysisListItem]
    total: int
    page: int
    limit: int
    total_pages: int

class AnalysisDetailResponse(BaseModel):
    """팝업 상세 페이지용"""
    id: str
    file_name: str
    asset_type: str
    source_code: Optional[str]
    loc_count: int
    target_product: Optional[str]
    target_version: Optional[str]
    status: str
    support_rate: float
    incompatibility_report: Optional[dict]
    reports: dict
    workspace_snapshot: Optional[dict]
    analysis_duration_seconds: Optional[float]
    created_at: datetime
```

### Phase 5: Backend - DI 등록

**변경 파일**: `app/api/core/deps.py`

```python
# LegacyAnalysisRepository 인스턴스화
_legacy_analysis_repo = None

def get_legacy_analysis_repo():
    global _legacy_analysis_repo
    if _legacy_analysis_repo is None:
        _legacy_analysis_repo = LegacyAnalysisRepository(db_pool)
    return _legacy_analysis_repo
```

### Phase 6: Frontend - API 클라이언트 추가

**변경 파일**: `kms-portal-ui/src/api/legacy.api.ts`

```typescript
// 분석 결과 목록 (Data Table용)
getAnalyses(params: {
  page?: number;
  limit?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  asset_type?: string;
}): Promise<AnalysisListResponse>

// 분석 결과 상세 (팝업용)
getAnalysisDetail(id: string): Promise<AnalysisDetailResponse>

// 분석 결과 삭제
deleteAnalysis(id: string): Promise<void>
```

### Phase 7: Frontend - Data Table 컴포넌트

**새 파일**: `kms-portal-ui/src/components/ModernizationAI/AnalysisDataTable.tsx`

Data Table 기능:
- **컬럼**: 파일명, 유형(COBOL/JCL/MAP/ASM), 호환율(%), 위험도(H/M/L), 기능수, 타겟제품, 분석일시
- **정렬**: 각 컬럼 헤더 클릭으로 ASC/DESC 정렬
- **필터**: 유형별 필터, 상태별 필터
- **페이지네이션**: 20/50/100건 단위
- **Row 클릭**: `window.open('/legacy/analysis/{id}', '_blank', 'popup')` → 새 팝업 창
- **삭제**: 체크박스 선택 → 일괄 삭제 버튼
- **자동 새로고침**: 분석 완료 시 테이블 자동 갱신

```
┌─────────────────────────────────────────────────────────────────┐
│ 분석 결과                                          [필터] [삭제]│
├────┬──────────┬──────┬──────┬──────────┬─────┬────────┬────────┤
│ ☐  │ 파일명   │ 유형 │호환율│ 위험도   │기능수│타겟제품│분석일시│
├────┼──────────┼──────┼──────┼──────────┼─────┼────────┼────────┤
│ ☐  │ MAIN.cbl │ COBOL│ 85%  │ H:2 M:3  │ 45  │ OSC    │ 02/19  │
│ ☐  │ BATCH.jcl│ JCL  │ 92%  │ M:1 L:2  │ 18  │ BATCH  │ 02/19  │
│ ☐  │ SCRN.map │ MAP  │ 78%  │ H:5 M:2  │ 30  │ OSC    │ 02/18  │
├────┴──────────┴──────┴──────┴──────────┴─────┴────────┴────────┤
│  << 1 2 3 4 5 >>                         20건/페이지  총 87건   │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 8: Frontend - 팝업 상세 페이지

**새 파일**: `kms-portal-ui/src/pages/LegacyAnalysisDetailPage.tsx`

독립 라우트: `/legacy/analysis/:id`

팝업 페이지 구성:
1. **헤더**: 파일명, 유형 배지, 호환율 게이지, 분석 일시
2. **요약 카드**: 전체 기능수, 호환/비호환 수, 위험도 분포
3. **비호환성 리포트**: 기존 `IncompatibilityReportView` 컴포넌트 재사용
4. **리포트 탭**: 9가지 리포트 타입별 상세 내용
5. **소스 코드 뷰어**: 원본 코드 (syntax highlighting)

```
┌─ Legacy Analysis Detail ────────────────────── [×] ─┐
│                                                      │
│  📄 MAIN.cbl (COBOL)          호환율: ████░ 85%     │
│  분석일: 2026-02-19 14:30     소요시간: 45초         │
│                                                      │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                │
│  │ 기능  │ │ 호환  │ │ 비호환│ │위험도│                │
│  │  45   │ │  38   │ │   7  │ │H:2M:3│               │
│  └──────┘ └──────┘ └──────┘ └──────┘                │
│                                                      │
│  [비호환성 리포트] [소스코드] [기술분석] [비용추정]  │
│  ┌──────────────────────────────────────────────┐    │
│  │  (탭 내용 - IncompatibilityReportView 등)    │    │
│  │  ...                                         │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

### Phase 9: Frontend - 라우트 등록 & 페이지 레이아웃 변경

**변경 파일**:
- `kms-portal-ui/src/App.tsx` - 새 라우트 추가: `/legacy/analysis/:id`
- `kms-portal-ui/src/pages/LegacyModernizationPage.tsx` - 하단에 Data Table 영역 추가

레이아웃 변경:
```
기존: [에디터 | 파이프라인+결과]  (2컬럼 가로 분할)

변경: [에디터 | 파이프라인+결과]  (2컬럼 가로 분할, 상단)
      [─── Data Table ───────]  (전체 너비, 하단)
```

### Phase 10: i18n 번역

**변경 파일**:
- `kms-portal-ui/src/i18n/locales/en/legacy.json`
- `kms-portal-ui/src/i18n/locales/ko/legacy.json`
- `kms-portal-ui/src/i18n/locales/ja/legacy.json`

Data Table 헤더, 필터, 팝업 페이지 관련 번역 키 추가.

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `app/api/infrastructure/postgres/legacy_analysis_repository.py` | **New** | PostgreSQL 분석 결과 Repository |
| `app/api/legacy_modernization/services/analysis_service.py` | **Modify** | 분석 완료 시 PostgreSQL 저장 |
| `app/api/legacy_modernization/routers/analysis.py` | **Modify** | 목록/상세/삭제 API 엔드포인트 추가 |
| `app/api/legacy_modernization/routers/schemas.py` | **Modify** | AnalysisListItem, AnalysisDetailResponse 추가 |
| `app/api/core/deps.py` | **Modify** | LegacyAnalysisRepository DI 등록 |
| `app/api/main.py` | **Modify** | Repository 초기화 (필요 시) |
| `kms-portal-ui/src/api/legacy.api.ts` | **Modify** | getAnalyses, getAnalysisDetail API 추가 |
| `kms-portal-ui/src/components/ModernizationAI/AnalysisDataTable.tsx` | **New** | Data Table 컴포넌트 |
| `kms-portal-ui/src/components/ModernizationAI/AnalysisDataTable.css` | **New** | Data Table 스타일 |
| `kms-portal-ui/src/pages/LegacyAnalysisDetailPage.tsx` | **New** | 팝업 상세 페이지 |
| `kms-portal-ui/src/pages/LegacyAnalysisDetailPage.css` | **New** | 팝업 페이지 스타일 |
| `kms-portal-ui/src/pages/LegacyModernizationPage.tsx` | **Modify** | 하단 Data Table 영역 추가 |
| `kms-portal-ui/src/pages/LegacyModernizationPage.css` | **Modify** | 레이아웃 변경 (상하 분할) |
| `kms-portal-ui/src/App.tsx` | **Modify** | `/legacy/analysis/:id` 라우트 추가 |
| `kms-portal-ui/src/i18n/locales/en/legacy.json` | **Modify** | 영어 번역 추가 |
| `kms-portal-ui/src/i18n/locales/ko/legacy.json` | **Modify** | 한국어 번역 추가 |
| `kms-portal-ui/src/i18n/locales/ja/legacy.json` | **Modify** | 일본어 번역 추가 |

## Dependencies

| 의존성 | 상태 | 비고 |
|--------|------|------|
| PostgreSQL (asyncpg) | ✅ 기존 사용 중 | db_pool 재사용 |
| Redis | ✅ 기존 사용 중 | 분석 중 임시 저장 유지 |
| React Router | ✅ 기존 사용 중 | 팝업 라우트 추가만 필요 |
| IncompatibilityReportView | ✅ 기존 컴포넌트 | 팝업 페이지에서 재사용 |
| BatchSummaryCard | ✅ 기존 컴포넌트 | 팝업 페이지에서 재사용 |

## Implementation Order

```
Phase 1 (DB Repository) → Phase 4 (Schemas)
    ↓
Phase 5 (DI 등록) → Phase 2 (Service 연동) → Phase 3 (API)
    ↓
Phase 6 (Frontend API) → Phase 7 (Data Table) → Phase 9 (레이아웃)
    ↓                                               ↓
Phase 8 (팝업 페이지) ← ← ← ← ← ← ← ← ← ← ← ← ←
    ↓
Phase 10 (i18n)
```

## Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| JSONB 컬럼 크기 (workspace_snapshot) | Medium | source_code 저장 옵션화, 필요 시 별도 테이블 분리 |
| 대량 데이터 조회 성능 | Low | 인덱스 + 페이지네이션 + 요약 컬럼 분리 |
| 팝업 차단 (브라우저 설정) | Low | `window.open` 실패 시 같은 탭에서 열기 fallback |
| 기존 분석 흐름 영향 | Low | PostgreSQL 저장은 완료 후 비동기 → 실패해도 기존 흐름 영향 없음 |
| deps.py 크기 (44K tokens) | Low | 기존 패턴 따라 최소한의 함수 추가 |

## Success Criteria

- [ ] 분석 완료 후 결과가 PostgreSQL에 영구 저장됨
- [ ] 서버 재시작 후에도 이전 분석 결과가 Data Table에 표시됨
- [ ] Data Table에서 컬럼별 정렬/필터/페이지네이션이 동작함
- [ ] Data Table row 클릭 시 새 브라우저 팝업이 열림
- [ ] 팝업에서 비호환성 리포트, 소스코드, 각종 리포트를 확인 가능
- [ ] 배치 분석 결과도 개별 행으로 Data Table에 표시됨
- [ ] 3개 언어(en/ko/ja) 번역 완료
