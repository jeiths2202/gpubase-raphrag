"""
PostgreSQL Legacy Analysis Repository

Provides persistent storage for legacy modernization analysis results with:
- Full CRUD operations
- Filtering and pagination
- Batch grouping
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from asyncpg import Pool

logger = logging.getLogger(__name__)


class LegacyAnalysisRepository:
    """PostgreSQL repository for legacy modernization analysis results."""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS legacy_analyses (
        id UUID PRIMARY KEY,
        user_id VARCHAR(100) NOT NULL,
        batch_id UUID,

        -- 소스 정보
        file_name VARCHAR(500) NOT NULL,
        asset_type VARCHAR(20) NOT NULL,
        source_code TEXT,
        loc_count INTEGER DEFAULT 0,

        -- 타겟 정보
        target_product VARCHAR(100),
        target_version VARCHAR(50),
        vendors JSONB DEFAULT '[]',

        -- 분석 결과 요약 (Data Table 정렬/필터용)
        status VARCHAR(30) NOT NULL DEFAULT 'completed',
        total_features INTEGER DEFAULT 0,
        supported_count INTEGER DEFAULT 0,
        incompatible_count INTEGER DEFAULT 0,
        support_rate FLOAT DEFAULT 0.0,
        risk_high INTEGER DEFAULT 0,
        risk_medium INTEGER DEFAULT 0,
        risk_low INTEGER DEFAULT 0,

        -- 상세 결과 (JSONB)
        incompatibility_report JSONB,
        reports JSONB DEFAULT '{}',
        workspace_snapshot JSONB,

        -- 메타데이터
        analysis_duration_seconds FLOAT,
        pipeline_status VARCHAR(30),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_legacy_analyses_user_id ON legacy_analyses(user_id);
    CREATE INDEX IF NOT EXISTS idx_legacy_analyses_batch_id ON legacy_analyses(batch_id);
    CREATE INDEX IF NOT EXISTS idx_legacy_analyses_created_at ON legacy_analyses(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_legacy_analyses_asset_type ON legacy_analyses(asset_type);
    CREATE INDEX IF NOT EXISTS idx_legacy_analyses_status ON legacy_analyses(status);
    """

    def __init__(self, pool: Pool):
        self._pool = pool

    @classmethod
    def from_pool(cls, pool: Pool) -> "LegacyAnalysisRepository":
        return cls(pool)

    async def initialize(self) -> None:
        """Create table if not exists."""
        async with self._pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLE_SQL)
            logger.info("legacy_analyses table ensured")

    async def save_analysis(self, data: Dict[str, Any]) -> str:
        """Save a completed analysis result.

        Args:
            data: Analysis data dict with all fields.

        Returns:
            The analysis ID string.
        """
        query = """
            INSERT INTO legacy_analyses (
                id, user_id, batch_id,
                file_name, asset_type, source_code, loc_count,
                target_product, target_version, vendors,
                status, total_features, supported_count, incompatible_count,
                support_rate, risk_high, risk_medium, risk_low,
                incompatibility_report, reports, workspace_snapshot,
                analysis_duration_seconds, pipeline_status,
                created_at, updated_at
            ) VALUES (
                $1::uuid, $2, $3::uuid,
                $4, $5, $6, $7,
                $8, $9, $10::jsonb,
                $11, $12, $13, $14,
                $15, $16, $17, $18,
                $19::jsonb, $20::jsonb, $21::jsonb,
                $22, $23,
                $24, $25
            )
            ON CONFLICT (id) DO UPDATE SET
                status = EXCLUDED.status,
                total_features = EXCLUDED.total_features,
                supported_count = EXCLUDED.supported_count,
                incompatible_count = EXCLUDED.incompatible_count,
                support_rate = EXCLUDED.support_rate,
                risk_high = EXCLUDED.risk_high,
                risk_medium = EXCLUDED.risk_medium,
                risk_low = EXCLUDED.risk_low,
                incompatibility_report = EXCLUDED.incompatibility_report,
                reports = EXCLUDED.reports,
                workspace_snapshot = EXCLUDED.workspace_snapshot,
                analysis_duration_seconds = EXCLUDED.analysis_duration_seconds,
                pipeline_status = EXCLUDED.pipeline_status,
                updated_at = EXCLUDED.updated_at
            RETURNING id
        """

        now = datetime.now(timezone.utc)
        batch_id = data.get("batch_id")

        try:
            async with self._pool.acquire() as conn:
                result = await conn.fetchval(
                    query,
                    UUID(data["id"]),
                    data["user_id"],
                    UUID(batch_id) if batch_id else None,
                    data["file_name"],
                    data["asset_type"],
                    data.get("source_code"),
                    data.get("loc_count", 0),
                    data.get("target_product"),
                    data.get("target_version"),
                    json.dumps(data.get("vendors", [])),
                    data.get("status", "completed"),
                    data.get("total_features", 0),
                    data.get("supported_count", 0),
                    data.get("incompatible_count", 0),
                    data.get("support_rate", 0.0),
                    data.get("risk_high", 0),
                    data.get("risk_medium", 0),
                    data.get("risk_low", 0),
                    json.dumps(data.get("incompatibility_report")) if data.get("incompatibility_report") else None,
                    json.dumps(data.get("reports", {})),
                    json.dumps(data.get("workspace_snapshot")) if data.get("workspace_snapshot") else None,
                    data.get("analysis_duration_seconds"),
                    data.get("pipeline_status"),
                    data.get("created_at", now),
                    now,
                )
            logger.info("Saved analysis %s for user %s", data["id"], data["user_id"])
            return str(result)
        except Exception as exc:
            logger.error("Failed to save analysis %s: %s", data.get("id"), exc)
            raise

    async def get_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Get full analysis detail by ID."""
        query = "SELECT * FROM legacy_analyses WHERE id = $1::uuid"

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, UUID(analysis_id))

            if not row:
                return None
            return self._row_to_detail(row)
        except Exception as exc:
            logger.error("Failed to get analysis %s: %s", analysis_id, exc)
            return None

    async def list_analyses(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 20,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        asset_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List analyses with pagination for Data Table.

        Returns:
            Tuple of (items, total_count).
        """
        # Whitelist sortable columns
        allowed_sort = {
            "created_at", "file_name", "asset_type", "support_rate",
            "total_features", "incompatible_count", "risk_high",
        }
        if sort_by not in allowed_sort:
            sort_by = "created_at"
        if sort_order not in ("asc", "desc"):
            sort_order = "desc"

        conditions = ["user_id = $1"]
        params: list = [user_id]
        param_idx = 2

        if asset_type:
            conditions.append(f"asset_type = ${param_idx}")
            params.append(asset_type)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        count_query = f"SELECT COUNT(*) FROM legacy_analyses WHERE {where_clause}"

        # Data Table에 필요한 컬럼만 조회 (JSONB 제외하여 성능 확보)
        data_query = f"""
            SELECT id, user_id, batch_id, file_name, asset_type, loc_count,
                   target_product, target_version, status,
                   total_features, supported_count, incompatible_count,
                   support_rate, risk_high, risk_medium, risk_low,
                   analysis_duration_seconds, pipeline_status,
                   created_at, updated_at
            FROM legacy_analyses
            WHERE {where_clause}
            ORDER BY {sort_by} {sort_order}
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        offset = (page - 1) * limit
        params.extend([limit, offset])

        try:
            async with self._pool.acquire() as conn:
                total = await conn.fetchval(count_query, *params[:-2])
                rows = await conn.fetch(data_query, *params)

            items = [self._row_to_list_item(row) for row in rows]
            return items, total or 0
        except Exception as exc:
            logger.error("Failed to list analyses: %s", exc)
            return [], 0

    async def delete_analysis(self, analysis_id: str, user_id: str) -> bool:
        """Delete an analysis (only if owned by user)."""
        query = "DELETE FROM legacy_analyses WHERE id = $1::uuid AND user_id = $2"

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(query, UUID(analysis_id), user_id)
            deleted = result == "DELETE 1"
            if deleted:
                logger.info("Deleted analysis %s", analysis_id)
            return deleted
        except Exception as exc:
            logger.error("Failed to delete analysis %s: %s", analysis_id, exc)
            return False

    async def delete_batch(self, batch_id: str, user_id: str) -> int:
        """Delete all analyses in a batch."""
        query = "DELETE FROM legacy_analyses WHERE batch_id = $1::uuid AND user_id = $2"

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(query, UUID(batch_id), user_id)
            count = int(result.split()[-1]) if result else 0
            logger.info("Deleted %d analyses from batch %s", count, batch_id)
            return count
        except Exception as exc:
            logger.error("Failed to delete batch %s: %s", batch_id, exc)
            return 0

    # ==================== Helpers ====================

    @staticmethod
    def _row_to_list_item(row) -> Dict[str, Any]:
        """Convert row to Data Table list item (no JSONB fields)."""
        return {
            "id": str(row["id"]),
            "batch_id": str(row["batch_id"]) if row["batch_id"] else None,
            "file_name": row["file_name"],
            "asset_type": row["asset_type"],
            "loc_count": row["loc_count"],
            "target_product": row["target_product"],
            "target_version": row["target_version"],
            "status": row["status"],
            "total_features": row["total_features"],
            "supported_count": row["supported_count"],
            "incompatible_count": row["incompatible_count"],
            "support_rate": row["support_rate"],
            "risk_high": row["risk_high"],
            "risk_medium": row["risk_medium"],
            "risk_low": row["risk_low"],
            "analysis_duration_seconds": row["analysis_duration_seconds"],
            "pipeline_status": row["pipeline_status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }

    @staticmethod
    def _row_to_detail(row) -> Dict[str, Any]:
        """Convert row to full detail (includes JSONB fields)."""
        return {
            "id": str(row["id"]),
            "user_id": row["user_id"],
            "batch_id": str(row["batch_id"]) if row["batch_id"] else None,
            "file_name": row["file_name"],
            "asset_type": row["asset_type"],
            "source_code": row["source_code"],
            "loc_count": row["loc_count"],
            "target_product": row["target_product"],
            "target_version": row["target_version"],
            "vendors": json.loads(row["vendors"]) if row["vendors"] else [],
            "status": row["status"],
            "total_features": row["total_features"],
            "supported_count": row["supported_count"],
            "incompatible_count": row["incompatible_count"],
            "support_rate": row["support_rate"],
            "risk_high": row["risk_high"],
            "risk_medium": row["risk_medium"],
            "risk_low": row["risk_low"],
            "incompatibility_report": json.loads(row["incompatibility_report"]) if row["incompatibility_report"] else None,
            "reports": json.loads(row["reports"]) if row["reports"] else {},
            "workspace_snapshot": json.loads(row["workspace_snapshot"]) if row["workspace_snapshot"] else None,
            "analysis_duration_seconds": row["analysis_duration_seconds"],
            "pipeline_status": row["pipeline_status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
