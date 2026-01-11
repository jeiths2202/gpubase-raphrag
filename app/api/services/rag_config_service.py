"""
RAG Configuration & Governance Service
Business logic for managing RAG profiles, experiments, and metrics
"""
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

import asyncpg

from ..models.rag_config import (
    RAGProfile, RAGProfileCreate, RAGProfileUpdate, RAGProfileSummary,
    RAGExperiment, ExperimentCreate, ExperimentUpdate, ExperimentSummary,
    ExperimentVariant, ExperimentStatus, EmbeddingStatus,
    ProfileMetricsSummary, ExperimentMetricsComparison, DailyMetrics,
    DocumentProfileAssignment, RAGConfigOverview,
    ChunkingConfig, EmbeddingConfig, ImageIngestionConfig, RetrievalConfig, GenerationConfig,
    ChunkStrategy, RetrievalStrategy, OCREngine
)

logger = logging.getLogger(__name__)


class RAGConfigService:
    """Service for RAG configuration and governance"""

    def __init__(self, db_pool: asyncpg.Pool):
        self._pool = db_pool

    # =========================================================================
    # RAG Profile Methods
    # =========================================================================

    async def list_profiles(
        self,
        space_id: Optional[str] = None,
        include_inactive: bool = False,
        page: int = 1,
        limit: int = 20
    ) -> Tuple[List[RAGProfileSummary], int, int]:
        """List RAG profiles with pagination"""
        offset = (page - 1) * limit

        async with self._pool.acquire() as conn:
            # Build where clause
            where_clauses = []
            params = []
            param_idx = 1

            if space_id is not None:
                where_clauses.append(f"space_id = ${param_idx}")
                params.append(space_id)
                param_idx += 1
            else:
                where_clauses.append("space_id IS NULL")

            if not include_inactive:
                where_clauses.append("is_active = true")

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Get total counts
            count_row = await conn.fetchrow(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE is_active = true) as active
                FROM rag_profiles
                WHERE {where_sql}
            """, *params)

            # Get profiles
            rows = await conn.fetch(f"""
                SELECT
                    id, name, description, space_id,
                    embedding_version, is_active, traffic_percentage,
                    retrieval_strategy, chunk_size, created_at
                FROM rag_profiles
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """, *params, limit, offset)

            profiles = [
                RAGProfileSummary(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    space_id=row["space_id"],
                    embedding_version=row["embedding_version"],
                    is_active=row["is_active"],
                    traffic_percentage=row["traffic_percentage"],
                    retrieval_strategy=RetrievalStrategy(row["retrieval_strategy"]),
                    chunk_size=row["chunk_size"],
                    created_at=row["created_at"]
                )
                for row in rows
            ]

            return profiles, count_row["total"], count_row["active"]

    async def get_profile(self, profile_id: UUID) -> Optional[RAGProfile]:
        """Get a single profile by ID"""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM rag_profiles WHERE id = $1
            """, profile_id)

            if not row:
                return None

            return self._row_to_profile(row)

    async def create_profile(
        self,
        data: RAGProfileCreate,
        created_by: UUID
    ) -> RAGProfile:
        """Create a new RAG profile with incremented version"""
        async with self._pool.acquire() as conn:
            # Get max version for this space
            max_version = await conn.fetchval("""
                SELECT COALESCE(MAX(embedding_version), 0)
                FROM rag_profiles
                WHERE (space_id = $1 OR ($1 IS NULL AND space_id IS NULL))
                  AND (project_id = $2 OR ($2 IS NULL AND project_id IS NULL))
            """, data.space_id, data.project_id)

            new_version = max_version + 1

            row = await conn.fetchrow("""
                INSERT INTO rag_profiles (
                    name, description, space_id, project_id, created_by,
                    embedding_version, is_active,
                    chunk_strategy, chunk_size, chunk_overlap,
                    min_chunk_size, max_chunk_size, language,
                    embedding_model, embedding_dimension, embedding_normalize, embedding_batch_size,
                    image_enabled, ocr_engine, image_dpi, layout_analysis,
                    caption_generation, image_chunk_strategy,
                    retrieval_strategy, top_k, score_threshold, hybrid_alpha,
                    temperature, max_tokens,
                    metadata
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, true,
                    $7, $8, $9, $10, $11, $12,
                    $13, $14, $15, $16,
                    $17, $18, $19, $20, $21, $22,
                    $23, $24, $25, $26,
                    $27, $28,
                    $29
                )
                RETURNING *
            """,
                data.name, data.description, data.space_id, data.project_id, created_by,
                new_version,
                data.chunking.strategy.value, data.chunking.chunk_size, data.chunking.chunk_overlap,
                data.chunking.min_chunk_size, data.chunking.max_chunk_size, data.chunking.language,
                data.embedding.model, data.embedding.dimension, data.embedding.normalize, data.embedding.batch_size,
                data.image_ingestion.enabled, data.image_ingestion.ocr_engine.value, data.image_ingestion.dpi,
                data.image_ingestion.layout_analysis, data.image_ingestion.caption_generation,
                data.image_ingestion.chunk_strategy,
                data.retrieval.strategy.value, data.retrieval.top_k, data.retrieval.score_threshold,
                data.retrieval.hybrid_alpha,
                data.generation.temperature, data.generation.max_tokens,
                data.metadata
            )

            logger.info(f"Created RAG profile: {data.name} (version {new_version})")
            return self._row_to_profile(row)

    async def update_profile(
        self,
        profile_id: UUID,
        data: RAGProfileUpdate
    ) -> Optional[RAGProfile]:
        """Update profile settings (creates new version if embedding-related)"""
        async with self._pool.acquire() as conn:
            # Get current profile
            current = await conn.fetchrow("SELECT * FROM rag_profiles WHERE id = $1", profile_id)
            if not current:
                return None

            # Build update fields
            updates = []
            params = []
            param_idx = 1

            # Check if embedding-related fields changed (requires new version)
            needs_new_version = False
            if data.chunking:
                needs_new_version = True
            if data.embedding:
                needs_new_version = True

            # Simple field updates
            if data.name is not None:
                updates.append(f"name = ${param_idx}")
                params.append(data.name)
                param_idx += 1

            if data.description is not None:
                updates.append(f"description = ${param_idx}")
                params.append(data.description)
                param_idx += 1

            if data.is_active is not None:
                updates.append(f"is_active = ${param_idx}")
                params.append(data.is_active)
                param_idx += 1

            if data.traffic_percentage is not None:
                updates.append(f"traffic_percentage = ${param_idx}")
                params.append(data.traffic_percentage)
                param_idx += 1

            # Retrieval config updates (no re-embedding needed)
            if data.retrieval:
                updates.append(f"retrieval_strategy = ${param_idx}")
                params.append(data.retrieval.strategy.value)
                param_idx += 1
                updates.append(f"top_k = ${param_idx}")
                params.append(data.retrieval.top_k)
                param_idx += 1
                updates.append(f"score_threshold = ${param_idx}")
                params.append(data.retrieval.score_threshold)
                param_idx += 1
                updates.append(f"hybrid_alpha = ${param_idx}")
                params.append(data.retrieval.hybrid_alpha)
                param_idx += 1

            # Generation config updates
            if data.generation:
                updates.append(f"temperature = ${param_idx}")
                params.append(data.generation.temperature)
                param_idx += 1
                updates.append(f"max_tokens = ${param_idx}")
                params.append(data.generation.max_tokens)
                param_idx += 1

            if data.metadata is not None:
                updates.append(f"metadata = ${param_idx}")
                params.append(data.metadata)
                param_idx += 1

            # Add timestamp
            updates.append(f"updated_at = ${param_idx}")
            params.append(datetime.now(timezone.utc))
            param_idx += 1

            if needs_new_version:
                # Increment version for embedding-related changes
                new_version = current["embedding_version"] + 1
                updates.append(f"embedding_version = ${param_idx}")
                params.append(new_version)
                param_idx += 1

                if data.chunking:
                    updates.extend([
                        f"chunk_strategy = ${param_idx}",
                        f"chunk_size = ${param_idx + 1}",
                        f"chunk_overlap = ${param_idx + 2}",
                        f"min_chunk_size = ${param_idx + 3}",
                        f"max_chunk_size = ${param_idx + 4}",
                        f"language = ${param_idx + 5}"
                    ])
                    params.extend([
                        data.chunking.strategy.value,
                        data.chunking.chunk_size,
                        data.chunking.chunk_overlap,
                        data.chunking.min_chunk_size,
                        data.chunking.max_chunk_size,
                        data.chunking.language
                    ])
                    param_idx += 6

                if data.embedding:
                    updates.extend([
                        f"embedding_model = ${param_idx}",
                        f"embedding_dimension = ${param_idx + 1}",
                        f"embedding_normalize = ${param_idx + 2}",
                        f"embedding_batch_size = ${param_idx + 3}"
                    ])
                    params.extend([
                        data.embedding.model,
                        data.embedding.dimension,
                        data.embedding.normalize,
                        data.embedding.batch_size
                    ])
                    param_idx += 4

                logger.warning(f"Profile {profile_id} updated with new embedding version {new_version}. Re-embedding required.")

            if not updates:
                return self._row_to_profile(current)

            # Execute update
            params.append(profile_id)
            row = await conn.fetchrow(f"""
                UPDATE rag_profiles
                SET {", ".join(updates)}
                WHERE id = ${param_idx}
                RETURNING *
            """, *params)

            return self._row_to_profile(row) if row else None

    async def delete_profile(self, profile_id: UUID) -> bool:
        """Delete a profile (soft delete by setting is_active=false)"""
        async with self._pool.acquire() as conn:
            # Check if profile is used in active experiments
            experiment = await conn.fetchrow("""
                SELECT e.id FROM rag_experiments e
                JOIN rag_experiment_variants v ON e.id = v.experiment_id
                WHERE v.profile_id = $1 AND e.status = 'active'
                LIMIT 1
            """, profile_id)

            if experiment:
                raise ValueError("Cannot delete profile used in active experiment")

            result = await conn.execute("""
                UPDATE rag_profiles
                SET is_active = false, updated_at = $2
                WHERE id = $1
            """, profile_id, datetime.now(timezone.utc))

            return result == "UPDATE 1"

    async def get_active_profile(
        self,
        space_id: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Optional[RAGProfile]:
        """
        Get the active profile for query routing.
        Handles A/B test traffic splitting if experiment is active.
        """
        async with self._pool.acquire() as conn:
            # Check for active experiment
            exp_row = await conn.fetchrow("""
                SELECT e.id, e.baseline_profile_id
                FROM rag_experiments e
                WHERE e.status = 'active'
                  AND (e.space_id = $1 OR ($1 IS NULL AND e.space_id IS NULL))
                LIMIT 1
            """, space_id)

            if exp_row:
                # Get all variants with traffic ratios
                variants = await conn.fetch("""
                    SELECT v.profile_id, v.traffic_ratio
                    FROM rag_experiment_variants v
                    WHERE v.experiment_id = $1
                    ORDER BY v.traffic_ratio DESC
                """, exp_row["id"])

                if variants:
                    # Deterministic random based on user_id for consistent experience
                    if user_id:
                        random.seed(hash(user_id) % (2**32))
                    rand = random.random()
                    random.seed()  # Reset seed

                    cumulative = 0.0
                    selected_profile_id = exp_row["baseline_profile_id"]

                    for v in variants:
                        cumulative += v["traffic_ratio"]
                        if rand <= cumulative:
                            selected_profile_id = v["profile_id"]
                            break

                    profile_row = await conn.fetchrow(
                        "SELECT * FROM rag_profiles WHERE id = $1",
                        selected_profile_id
                    )
                    if profile_row:
                        return self._row_to_profile(profile_row)

            # No experiment - get default active profile with highest traffic %
            row = await conn.fetchrow("""
                SELECT * FROM rag_profiles
                WHERE is_active = true
                  AND (space_id = $1 OR ($1 IS NULL AND space_id IS NULL))
                  AND (project_id = $2 OR ($2 IS NULL AND project_id IS NULL))
                ORDER BY traffic_percentage DESC, created_at DESC
                LIMIT 1
            """, space_id, project_id)

            if row:
                return self._row_to_profile(row)

            # Fallback to global default
            row = await conn.fetchrow("""
                SELECT * FROM rag_profiles
                WHERE is_active = true AND space_id IS NULL AND project_id IS NULL
                ORDER BY traffic_percentage DESC
                LIMIT 1
            """)

            return self._row_to_profile(row) if row else None

    # =========================================================================
    # A/B Experiment Methods
    # =========================================================================

    async def list_experiments(
        self,
        space_id: Optional[str] = None,
        status: Optional[ExperimentStatus] = None,
        page: int = 1,
        limit: int = 20
    ) -> Tuple[List[ExperimentSummary], int, int]:
        """List experiments with pagination"""
        offset = (page - 1) * limit

        async with self._pool.acquire() as conn:
            where_clauses = []
            params = []
            param_idx = 1

            if space_id is not None:
                where_clauses.append(f"e.space_id = ${param_idx}")
                params.append(space_id)
                param_idx += 1

            if status:
                where_clauses.append(f"e.status = ${param_idx}")
                params.append(status.value)
                param_idx += 1

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            count_row = await conn.fetchrow(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE e.status = 'active') as active
                FROM rag_experiments e
                WHERE {where_sql}
            """, *params)

            rows = await conn.fetch(f"""
                SELECT
                    e.id, e.name, e.status, e.total_queries,
                    e.started_at, e.created_at,
                    p.name as baseline_name,
                    (SELECT COUNT(*) FROM rag_experiment_variants WHERE experiment_id = e.id) as variant_count
                FROM rag_experiments e
                JOIN rag_profiles p ON e.baseline_profile_id = p.id
                WHERE {where_sql}
                ORDER BY e.created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """, *params, limit, offset)

            experiments = [
                ExperimentSummary(
                    id=row["id"],
                    name=row["name"],
                    status=ExperimentStatus(row["status"]),
                    baseline_profile_name=row["baseline_name"],
                    variant_count=row["variant_count"],
                    total_queries=row["total_queries"],
                    started_at=row["started_at"],
                    created_at=row["created_at"]
                )
                for row in rows
            ]

            return experiments, count_row["total"], count_row["active"]

    async def create_experiment(
        self,
        data: ExperimentCreate,
        created_by: UUID
    ) -> RAGExperiment:
        """Create a new A/B experiment"""
        # Validate traffic ratios sum to 1.0
        total_traffic = sum(v.traffic_ratio for v in data.variants)
        if abs(total_traffic - 1.0) > 0.01:
            raise ValueError(f"Traffic ratios must sum to 1.0, got {total_traffic}")

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Create experiment
                exp_row = await conn.fetchrow("""
                    INSERT INTO rag_experiments (
                        name, description, space_id, baseline_profile_id, created_by
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING *
                """, data.name, data.description, data.space_id, data.baseline_profile_id, created_by)

                # Create variants
                for variant in data.variants:
                    await conn.execute("""
                        INSERT INTO rag_experiment_variants (
                            experiment_id, profile_id, traffic_ratio, variant_name
                        )
                        VALUES ($1, $2, $3, $4)
                    """, exp_row["id"], variant.profile_id, variant.traffic_ratio, variant.variant_name)

                # Fetch complete experiment with variants
                return await self._get_experiment_full(conn, exp_row["id"])

    async def update_experiment(
        self,
        experiment_id: UUID,
        data: ExperimentUpdate
    ) -> Optional[RAGExperiment]:
        """Update experiment status or configuration"""
        async with self._pool.acquire() as conn:
            current = await conn.fetchrow("SELECT * FROM rag_experiments WHERE id = $1", experiment_id)
            if not current:
                return None

            updates = ["updated_at = $1"]
            params = [datetime.now(timezone.utc)]
            param_idx = 2

            if data.name:
                updates.append(f"name = ${param_idx}")
                params.append(data.name)
                param_idx += 1

            if data.description is not None:
                updates.append(f"description = ${param_idx}")
                params.append(data.description)
                param_idx += 1

            if data.status:
                updates.append(f"status = ${param_idx}")
                params.append(data.status.value)
                param_idx += 1

                # Set timestamps based on status change
                if data.status == ExperimentStatus.ACTIVE and not current["started_at"]:
                    updates.append(f"started_at = ${param_idx}")
                    params.append(datetime.now(timezone.utc))
                    param_idx += 1
                elif data.status == ExperimentStatus.COMPLETED:
                    updates.append(f"ended_at = ${param_idx}")
                    params.append(datetime.now(timezone.utc))
                    param_idx += 1

            params.append(experiment_id)
            await conn.execute(f"""
                UPDATE rag_experiments
                SET {", ".join(updates)}
                WHERE id = ${param_idx}
            """, *params)

            # Update variants if provided
            if data.variants:
                total_traffic = sum(v.traffic_ratio for v in data.variants)
                if abs(total_traffic - 1.0) > 0.01:
                    raise ValueError(f"Traffic ratios must sum to 1.0, got {total_traffic}")

                await conn.execute("DELETE FROM rag_experiment_variants WHERE experiment_id = $1", experiment_id)
                for variant in data.variants:
                    await conn.execute("""
                        INSERT INTO rag_experiment_variants (
                            experiment_id, profile_id, traffic_ratio, variant_name
                        )
                        VALUES ($1, $2, $3, $4)
                    """, experiment_id, variant.profile_id, variant.traffic_ratio, variant.variant_name)

            return await self._get_experiment_full(conn, experiment_id)

    async def get_experiment_metrics(
        self,
        experiment_id: UUID,
        days: int = 7
    ) -> Optional[ExperimentMetricsComparison]:
        """Get aggregated metrics comparison for an experiment"""
        async with self._pool.acquire() as conn:
            exp = await conn.fetchrow("""
                SELECT e.*, p.name as baseline_name
                FROM rag_experiments e
                JOIN rag_profiles p ON e.baseline_profile_id = p.id
                WHERE e.id = $1
            """, experiment_id)

            if not exp:
                return None

            # Get metrics for all variants
            metrics_rows = await conn.fetch("""
                SELECT
                    em.profile_id,
                    p.name as profile_name,
                    SUM(em.query_count) as total_queries,
                    AVG(CASE WHEN em.query_count > 0
                        THEN em.success_count::FLOAT / em.query_count
                        ELSE 0 END) as success_rate,
                    AVG(em.avg_latency_ms) as avg_latency_ms,
                    AVG(em.avg_similarity_score) as avg_similarity_score,
                    AVG(em.retrieval_hit_rate) as retrieval_hit_rate,
                    SUM(em.total_input_tokens + em.total_output_tokens) as total_tokens,
                    SUM(em.estimated_cost) as estimated_cost,
                    SUM(em.thumbs_up) as thumbs_up,
                    SUM(em.thumbs_down) as thumbs_down
                FROM rag_experiment_metrics em
                JOIN rag_profiles p ON em.profile_id = p.id
                WHERE em.experiment_id = $1
                  AND em.metric_date >= CURRENT_DATE - $2
                GROUP BY em.profile_id, p.name
            """, experiment_id, days)

            def row_to_metrics(row) -> ProfileMetricsSummary:
                up = row["thumbs_up"] or 0
                down = row["thumbs_down"] or 0
                satisfaction = (up - down) / (up + down) if (up + down) > 0 else 0

                return ProfileMetricsSummary(
                    profile_id=row["profile_id"],
                    profile_name=row["profile_name"],
                    total_queries=int(row["total_queries"] or 0),
                    success_rate=float(row["success_rate"] or 0),
                    avg_latency_ms=int(row["avg_latency_ms"] or 0),
                    avg_similarity_score=float(row["avg_similarity_score"] or 0),
                    retrieval_hit_rate=float(row["retrieval_hit_rate"] or 0),
                    total_tokens=int(row["total_tokens"] or 0),
                    estimated_cost=float(row["estimated_cost"] or 0),
                    thumbs_up=up,
                    thumbs_down=down,
                    satisfaction_rate=satisfaction
                )

            # Separate baseline from variants
            baseline_metrics = None
            variant_metrics = []

            for row in metrics_rows:
                metrics = row_to_metrics(row)
                if row["profile_id"] == exp["baseline_profile_id"]:
                    baseline_metrics = metrics
                else:
                    variant_metrics.append(metrics)

            # Create empty baseline if no data
            if not baseline_metrics:
                baseline_metrics = ProfileMetricsSummary(
                    profile_id=exp["baseline_profile_id"],
                    profile_name=exp["baseline_name"],
                    total_queries=0, success_rate=0, avg_latency_ms=0,
                    avg_similarity_score=0, retrieval_hit_rate=0,
                    total_tokens=0, estimated_cost=0,
                    thumbs_up=0, thumbs_down=0, satisfaction_rate=0
                )

            # Determine winner (simple: highest satisfaction rate with >100 queries)
            winner_id = None
            winner_confidence = None

            all_metrics = [baseline_metrics] + variant_metrics
            qualifying = [m for m in all_metrics if m.total_queries >= 100]

            if len(qualifying) >= 2:
                sorted_by_satisfaction = sorted(qualifying, key=lambda m: m.satisfaction_rate, reverse=True)
                if sorted_by_satisfaction[0].satisfaction_rate > sorted_by_satisfaction[1].satisfaction_rate:
                    winner_id = sorted_by_satisfaction[0].profile_id
                    # Simple confidence based on query count
                    winner_confidence = min(0.95, sorted_by_satisfaction[0].total_queries / 1000)

            return ExperimentMetricsComparison(
                experiment_id=experiment_id,
                experiment_name=exp["name"],
                period_days=days,
                baseline=baseline_metrics,
                variants=variant_metrics,
                winner_profile_id=winner_id,
                winner_confidence=winner_confidence
            )

    # =========================================================================
    # Overview Methods
    # =========================================================================

    async def get_overview(self, space_id: Optional[str] = None) -> RAGConfigOverview:
        """Get dashboard overview of RAG configuration"""
        async with self._pool.acquire() as conn:
            # Profile counts
            profile_counts = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE is_active = true) as active
                FROM rag_profiles
                WHERE space_id = $1 OR ($1 IS NULL AND space_id IS NULL)
            """, space_id)

            # Experiment counts
            exp_counts = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'active') as active
                FROM rag_experiments
                WHERE space_id = $1 OR ($1 IS NULL AND space_id IS NULL)
            """, space_id)

            # Document profile counts
            doc_counts = await conn.fetchrow("""
                SELECT
                    COUNT(DISTINCT document_id) as custom_profile,
                    COUNT(*) FILTER (WHERE embedding_status = 'pending') as pending
                FROM document_rag_profiles
            """)

            # Recent profiles
            recent_profiles_rows = await conn.fetch("""
                SELECT
                    id, name, description, space_id,
                    embedding_version, is_active, traffic_percentage,
                    retrieval_strategy, chunk_size, created_at
                FROM rag_profiles
                WHERE space_id = $1 OR ($1 IS NULL AND space_id IS NULL)
                ORDER BY created_at DESC
                LIMIT 5
            """, space_id)

            # Recent experiments
            recent_exp_rows = await conn.fetch("""
                SELECT
                    e.id, e.name, e.status, e.total_queries,
                    e.started_at, e.created_at,
                    p.name as baseline_name,
                    (SELECT COUNT(*) FROM rag_experiment_variants WHERE experiment_id = e.id) as variant_count
                FROM rag_experiments e
                JOIN rag_profiles p ON e.baseline_profile_id = p.id
                WHERE e.space_id = $1 OR ($1 IS NULL AND e.space_id IS NULL)
                ORDER BY e.created_at DESC
                LIMIT 5
            """, space_id)

            return RAGConfigOverview(
                total_profiles=profile_counts["total"],
                active_profiles=profile_counts["active"],
                total_experiments=exp_counts["total"],
                active_experiments=exp_counts["active"],
                documents_with_custom_profile=doc_counts["custom_profile"] or 0,
                pending_reembedding=doc_counts["pending"] or 0,
                recent_profiles=[
                    RAGProfileSummary(
                        id=row["id"],
                        name=row["name"],
                        description=row["description"],
                        space_id=row["space_id"],
                        embedding_version=row["embedding_version"],
                        is_active=row["is_active"],
                        traffic_percentage=row["traffic_percentage"],
                        retrieval_strategy=RetrievalStrategy(row["retrieval_strategy"]),
                        chunk_size=row["chunk_size"],
                        created_at=row["created_at"]
                    )
                    for row in recent_profiles_rows
                ],
                recent_experiments=[
                    ExperimentSummary(
                        id=row["id"],
                        name=row["name"],
                        status=ExperimentStatus(row["status"]),
                        baseline_profile_name=row["baseline_name"],
                        variant_count=row["variant_count"],
                        total_queries=row["total_queries"],
                        started_at=row["started_at"],
                        created_at=row["created_at"]
                    )
                    for row in recent_exp_rows
                ]
            )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _row_to_profile(self, row: asyncpg.Record) -> RAGProfile:
        """Convert database row to RAGProfile model"""
        return RAGProfile(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            space_id=row["space_id"],
            project_id=row["project_id"],
            embedding_version=row["embedding_version"],
            is_active=row["is_active"],
            traffic_percentage=row["traffic_percentage"],
            experiment_id=row["experiment_id"],
            chunking=ChunkingConfig(
                strategy=ChunkStrategy(row["chunk_strategy"]),
                chunk_size=row["chunk_size"],
                chunk_overlap=row["chunk_overlap"],
                min_chunk_size=row["min_chunk_size"],
                max_chunk_size=row["max_chunk_size"],
                language=row["language"]
            ),
            embedding=EmbeddingConfig(
                model=row["embedding_model"],
                dimension=row["embedding_dimension"],
                normalize=row["embedding_normalize"],
                batch_size=row["embedding_batch_size"]
            ),
            image_ingestion=ImageIngestionConfig(
                enabled=row["image_enabled"],
                ocr_engine=OCREngine(row["ocr_engine"]),
                dpi=row["image_dpi"],
                layout_analysis=row["layout_analysis"],
                caption_generation=row["caption_generation"],
                chunk_strategy=row["image_chunk_strategy"]
            ),
            retrieval=RetrievalConfig(
                strategy=RetrievalStrategy(row["retrieval_strategy"]),
                top_k=row["top_k"],
                score_threshold=row["score_threshold"],
                hybrid_alpha=row["hybrid_alpha"]
            ),
            generation=GenerationConfig(
                temperature=row["temperature"],
                max_tokens=row["max_tokens"]
            ),
            metadata=row["metadata"] or {},
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    async def _get_experiment_full(self, conn: asyncpg.Connection, experiment_id: UUID) -> RAGExperiment:
        """Get full experiment with variants"""
        exp_row = await conn.fetchrow("""
            SELECT e.*, p.name as baseline_name
            FROM rag_experiments e
            JOIN rag_profiles p ON e.baseline_profile_id = p.id
            WHERE e.id = $1
        """, experiment_id)

        variants_rows = await conn.fetch("""
            SELECT v.*, p.name as profile_name
            FROM rag_experiment_variants v
            JOIN rag_profiles p ON v.profile_id = p.id
            WHERE v.experiment_id = $1
            ORDER BY v.traffic_ratio DESC
        """, experiment_id)

        return RAGExperiment(
            id=exp_row["id"],
            name=exp_row["name"],
            description=exp_row["description"],
            space_id=exp_row["space_id"],
            baseline_profile_id=exp_row["baseline_profile_id"],
            baseline_profile_name=exp_row["baseline_name"],
            variants=[
                ExperimentVariant(
                    profile_id=v["profile_id"],
                    profile_name=v["profile_name"],
                    traffic_ratio=v["traffic_ratio"],
                    variant_name=v["variant_name"]
                )
                for v in variants_rows
            ],
            status=ExperimentStatus(exp_row["status"]),
            started_at=exp_row["started_at"],
            ended_at=exp_row["ended_at"],
            total_queries=exp_row["total_queries"],
            created_by=exp_row["created_by"],
            created_at=exp_row["created_at"],
            updated_at=exp_row["updated_at"]
        )


# =============================================================================
# Singleton Management
# =============================================================================

_rag_config_service: Optional[RAGConfigService] = None


def init_rag_config_service(db_pool: asyncpg.Pool) -> RAGConfigService:
    """Initialize RAG config service singleton"""
    global _rag_config_service
    _rag_config_service = RAGConfigService(db_pool)
    logger.info("[OK] RAG Config Service initialized")
    return _rag_config_service


def get_rag_config_service() -> RAGConfigService:
    """Get RAG config service singleton"""
    if _rag_config_service is None:
        raise RuntimeError("RAG Config Service not initialized. Call init_rag_config_service first.")
    return _rag_config_service
