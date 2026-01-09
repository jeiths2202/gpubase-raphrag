"""
PostgreSQL Issue Repository - Store and retrieve IMS issues with vector search

Implements issue storage with pgvector semantic search support.
"""

import asyncpg
import json
from typing import List, Optional
from uuid import UUID

from ...domain.entities import Issue
from ..ports.issue_repository_port import IssueRepositoryPort


class PostgreSQLIssueRepository(IssueRepositoryPort):
    """
    PostgreSQL implementation of issue repository with vector search.

    Uses pgvector for semantic similarity search.
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize repository with connection pool.

        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool

    async def save(self, issue: Issue) -> UUID:
        """
        Save or update issue.

        Uses UPSERT for idempotent saves.
        Returns the actual ID stored in DB (may differ on conflict).
        """
        query = """
            INSERT INTO ims_issues (
                id, ims_id, user_id, title, description,
                status, priority, status_raw, priority_raw,
                reporter, assignee,
                project_key, issue_type, labels,
                comments_count, attachments_count,
                created_at, updated_at, resolved_at,
                crawled_at, source_url, custom_fields,
                category, product, version, module, customer, issued_date,
                issue_details, action_no
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30)
            ON CONFLICT (user_id, ims_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                status = EXCLUDED.status,
                priority = EXCLUDED.priority,
                status_raw = EXCLUDED.status_raw,
                priority_raw = EXCLUDED.priority_raw,
                assignee = EXCLUDED.assignee,
                labels = EXCLUDED.labels,
                comments_count = EXCLUDED.comments_count,
                attachments_count = EXCLUDED.attachments_count,
                updated_at = EXCLUDED.updated_at,
                resolved_at = EXCLUDED.resolved_at,
                category = EXCLUDED.category,
                product = EXCLUDED.product,
                version = EXCLUDED.version,
                module = EXCLUDED.module,
                customer = EXCLUDED.customer,
                issued_date = EXCLUDED.issued_date,
                issue_details = EXCLUDED.issue_details,
                action_no = EXCLUDED.action_no
            RETURNING id
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                issue.id, issue.ims_id, issue.user_id,
                issue.title, issue.description,
                issue.status.value, issue.priority.value,
                issue.status_raw, issue.priority_raw,
                issue.reporter, issue.assignee,
                issue.project_key, issue.issue_type, issue.labels,
                issue.comments_count, issue.attachments_count,
                issue.created_at, issue.updated_at, issue.resolved_at,
                issue.crawled_at, issue.source_url,
                json.dumps(issue.custom_fields) if issue.custom_fields else "{}",
                issue.category, issue.product, issue.version,
                issue.module, issue.customer, issue.issued_date,
                issue.issue_details, issue.action_no
            )
            return row['id']

    async def save_embedding(self, issue_id: UUID, embedding: List[float], embedded_text: str) -> None:
        """
        Save vector embedding for issue.

        Args:
            issue_id: Issue UUID
            embedding: 4096-dim vector
            embedded_text: Text that was embedded
        """
        # Convert embedding list to pgvector string format: '[0.1, 0.2, ...]'
        embedding_str = '[' + ','.join(str(v) for v in embedding) + ']'

        query = """
            INSERT INTO ims_issue_embeddings (issue_id, embedding, embedded_text)
            VALUES ($1, $2::vector, $3)
            ON CONFLICT (issue_id)
            DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedded_text = EXCLUDED.embedded_text,
                created_at = NOW()
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, issue_id, embedding_str, embedded_text)

    async def save_relation(
        self,
        source_issue_id: UUID,
        target_issue_id: UUID,
        relation_type: str
    ) -> None:
        """
        Save a relationship between two issues.

        Args:
            source_issue_id: Source issue UUID
            target_issue_id: Target issue UUID
            relation_type: Type of relation ('relates_to', 'blocks', 'duplicates')
        """
        query = """
            INSERT INTO ims_issue_relations (source_issue_id, target_issue_id, relation_type)
            VALUES ($1, $2, $3)
            ON CONFLICT (source_issue_id, target_issue_id, relation_type)
            DO NOTHING
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, source_issue_id, target_issue_id, relation_type)

    async def find_by_id(self, issue_id: UUID) -> Optional[Issue]:
        """Find issue by ID"""
        query = """
            SELECT * FROM ims_issues WHERE id = $1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, issue_id)
            return self._row_to_issue(row) if row else None

    async def find_by_user_id(self, user_id: UUID, limit: int = 100) -> List[Issue]:
        """
        Find recent issues for user.

        Args:
            user_id: User UUID
            limit: Max results

        Returns:
            List of issues sorted by crawled_at DESC
        """
        query = """
            SELECT * FROM ims_issues
            WHERE user_id = $1
            ORDER BY crawled_at DESC
            LIMIT $2
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, limit)
            return [self._row_to_issue(row) for row in rows]

    async def search_by_vector(
        self,
        embedding: List[float],
        user_id: UUID,
        limit: int = 20
    ) -> List[Issue]:
        """
        Semantic search using vector similarity.

        Args:
            embedding: Query embedding (4096-dim)
            user_id: User UUID (filter)
            limit: Max results

        Returns:
            List of issues sorted by similarity DESC
        """
        # Convert embedding list to pgvector string format
        embedding_str = '[' + ','.join(str(v) for v in embedding) + ']'

        query = """
            SELECT
                i.*,
                1 - (e.embedding <=> $1::vector) AS similarity_score
            FROM ims_issues i
            INNER JOIN ims_issue_embeddings e ON i.id = e.issue_id
            WHERE i.user_id = $2
            ORDER BY e.embedding <=> $1::vector
            LIMIT $3
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, embedding_str, user_id, limit)
            issues = []
            for row in rows:
                issue = self._row_to_issue(row)
                # Add similarity score as custom field
                issue.custom_fields['similarity_score'] = float(row['similarity_score'])
                issues.append(issue)
            return issues

    async def search_hybrid(
        self,
        query_text: str,
        user_id: UUID,
        limit: int = 20,
        candidate_limit: int = 100
    ) -> List[Issue]:
        """
        Hybrid search using BM25 + Semantic scoring.

        Retrieves candidate issues from database, then applies
        in-memory hybrid ranking with CJK-optimized tokenization.

        Args:
            query_text: Natural language query
            user_id: User UUID filter
            limit: Final result count
            candidate_limit: Initial candidates from DB (for hybrid reranking)

        Returns:
            List of issues sorted by hybrid score DESC
        """
        # Get candidates from database (broader retrieval)
        query = """
            SELECT i.*
            FROM ims_issues i
            WHERE i.user_id = $1
            ORDER BY i.created_date DESC
            LIMIT $2
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, candidate_limit)
            candidates = [self._row_to_issue(row) for row in rows]

        if not candidates:
            return []

        # Apply hybrid search in-memory
        from ..services.hybrid_search_service import HybridSearchService

        searcher = HybridSearchService()

        # Convert issues to searchable documents
        documents = []
        for issue in candidates:
            documents.append({
                'id': issue.id,
                'content': f"{issue.title} {issue.description}",
                'issue': issue
            })

        # Index and search
        searcher.index_documents(documents)
        results = searcher.search(query_text, top_k=limit)

        # Extract issues with hybrid scores
        ranked_issues = []
        for doc, score in results:
            issue = doc['issue']
            issue.custom_fields['hybrid_score'] = score
            ranked_issues.append(issue)

        return ranked_issues

    async def get_embedded_ims_ids(self, user_id: UUID, ims_ids: List[str]) -> set:
        """
        Get set of ims_ids that already have embeddings stored.

        Args:
            user_id: User UUID
            ims_ids: List of ims_ids to check

        Returns:
            Set of ims_ids that have embeddings
        """
        if not ims_ids:
            return set()

        query = """
            SELECT i.ims_id
            FROM ims_issues i
            INNER JOIN ims_issue_embeddings e ON i.id = e.issue_id
            WHERE i.user_id = $1 AND i.ims_id = ANY($2)
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, ims_ids)
            return {row['ims_id'] for row in rows}

    def _row_to_issue(self, row: asyncpg.Record) -> Issue:
        """Convert database row to Issue entity"""
        from ...domain.entities import IssueStatus, IssuePriority

        # Parse custom_fields - handle both JSON string and dict
        custom_fields_raw = row['custom_fields']
        if custom_fields_raw:
            if isinstance(custom_fields_raw, str):
                custom_fields = json.loads(custom_fields_raw)
            elif isinstance(custom_fields_raw, dict):
                custom_fields = custom_fields_raw
            else:
                custom_fields = {}
        else:
            custom_fields = {}

        return Issue(
            id=row['id'],
            ims_id=row['ims_id'],
            user_id=row['user_id'],
            title=row['title'],
            description=row['description'] or "",
            status=IssueStatus(row['status']),
            priority=IssuePriority(row['priority']),
            # IMS-specific fields
            category=row.get('category') or "",
            product=row.get('product') or "",
            version=row.get('version') or "",
            module=row.get('module') or "",
            customer=row.get('customer') or "",
            issued_date=row.get('issued_date'),
            # Metadata
            reporter=row['reporter'] or "",
            assignee=row['assignee'],
            project_key=row['project_key'] or "",
            issue_type=row['issue_type'] or "Task",
            labels=list(row['labels']) if row['labels'] else [],
            comments_count=row['comments_count'] or 0,
            attachments_count=row['attachments_count'] or 0,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            resolved_at=row['resolved_at'],
            crawled_at=row['crawled_at'],
            source_url=row['source_url'] or "",
            custom_fields=custom_fields
        )
