"""
PostgreSQL Conversation Repository Implementation

Production-ready PostgreSQL implementation with:
- Async operations using asyncpg
- Row-Level Security (RLS) context management
- Connection pooling
- Transaction support for complex operations
- Full-text search integration
"""
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4

import asyncpg
from asyncpg import Pool, Connection

from ...repositories.conversation_repository import (
    ConversationRepository,
    ConversationEntity,
    MessageEntity,
    SummaryEntity,
)
from ...repositories.base import EntityId

logger = logging.getLogger(__name__)


class PostgresConversationRepository(ConversationRepository):
    """
    PostgreSQL implementation of ConversationRepository.

    Features:
    - Connection pooling for performance
    - RLS context setting for user isolation
    - Transaction support for fork/regenerate operations
    - Full-text search for message content
    """

    def __init__(
        self,
        pool: Pool,
        *,
        set_rls_context: bool = True,
        rls_bypass_roles: Optional[List[str]] = None
    ):
        """
        Initialize PostgreSQL repository.

        Args:
            pool: asyncpg connection pool
            set_rls_context: Whether to set RLS context before operations
            rls_bypass_roles: Roles that bypass RLS (admin, super_admin)
        """
        self._pool = pool
        self._set_rls_context = set_rls_context
        self._rls_bypass_roles = rls_bypass_roles or ["admin", "super_admin"]

    @classmethod
    async def create(
        cls,
        dsn: str,
        *,
        min_size: int = 5,
        max_size: int = 20,
        **kwargs
    ) -> "PostgresConversationRepository":
        """
        Factory method to create repository with connection pool.

        Args:
            dsn: PostgreSQL connection string
            min_size: Minimum pool connections
            max_size: Maximum pool connections
            **kwargs: Additional asyncpg pool options
        """
        pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            **kwargs
        )
        return cls(pool, **kwargs)

    async def close(self) -> None:
        """Close the connection pool."""
        await self._pool.close()

    # ==================== Helper Methods ====================

    async def _set_user_context(
        self,
        conn: Connection,
        user_id: str,
        user_role: Optional[str] = None
    ) -> None:
        """Set RLS context for the connection."""
        if not self._set_rls_context:
            return

        await conn.execute(
            "SELECT set_config('app.current_user_id', $1, true)",
            user_id
        )
        if user_role:
            await conn.execute(
                "SELECT set_config('app.current_user_role', $1, true)",
                user_role
            )

    def _normalize_id(self, entity_id: EntityId) -> str:
        """Normalize entity ID to string."""
        if isinstance(entity_id, UUID):
            return str(entity_id)
        return entity_id

    def _to_uuid(self, entity_id: Optional[EntityId]) -> Optional[UUID]:
        """Convert entity ID to UUID."""
        if entity_id is None:
            return None
        if isinstance(entity_id, UUID):
            return entity_id
        return UUID(entity_id)

    def _row_to_conversation(self, row: asyncpg.Record) -> ConversationEntity:
        """Convert database row to ConversationEntity."""
        return ConversationEntity(
            id=str(row["id"]),
            user_id=row["user_id"],
            project_id=row.get("project_id"),
            session_id=row.get("session_id"),
            title=row.get("title"),
            message_count=row.get("message_count", 0),
            total_tokens=row.get("total_tokens", 0),
            is_archived=row.get("is_archived", False),
            is_starred=row.get("is_starred", False),
            is_deleted=row.get("is_deleted", False),
            deleted_at=row.get("deleted_at"),
            deleted_by=row.get("deleted_by"),
            strategy=row.get("strategy", "auto"),
            language=row.get("language", "auto"),
            metadata=json.loads(row["metadata"]) if row.get("metadata") else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    def _row_to_message(self, row: asyncpg.Record) -> MessageEntity:
        """Convert database row to MessageEntity."""
        return MessageEntity(
            id=str(row["id"]),
            conversation_id=str(row["conversation_id"]),
            parent_message_id=str(row["parent_message_id"]) if row.get("parent_message_id") else None,
            role=row["role"],
            content=row["content"],
            input_tokens=row.get("input_tokens", 0),
            output_tokens=row.get("output_tokens", 0),
            total_tokens=row.get("total_tokens", 0),
            model=row.get("model"),
            sources=json.loads(row["sources"]) if row.get("sources") else [],
            rag_context=json.loads(row["rag_context"]) if row.get("rag_context") else {},
            feedback_score=row.get("feedback_score"),
            feedback_text=row.get("feedback_text"),
            is_regenerated=row.get("is_regenerated", False),
            regeneration_count=row.get("regeneration_count", 0),
            original_message_id=str(row["original_message_id"]) if row.get("original_message_id") else None,
            branch_root_id=str(row["branch_root_id"]) if row.get("branch_root_id") else None,
            branch_depth=row.get("branch_depth", 0),
            is_active_branch=row.get("is_active_branch", True),
            is_deleted=row.get("is_deleted", False),
            deleted_at=row.get("deleted_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    def _row_to_summary(self, row: asyncpg.Record) -> SummaryEntity:
        """Convert database row to SummaryEntity."""
        return SummaryEntity(
            id=str(row["id"]),
            conversation_id=str(row["conversation_id"]),
            summary_text=row["summary_text"],
            summary_type=row.get("summary_type", "rolling"),
            covers_from_message_id=str(row["covers_from_message_id"]) if row.get("covers_from_message_id") else None,
            covers_to_message_id=str(row["covers_to_message_id"]) if row.get("covers_to_message_id") else None,
            message_count_covered=row.get("message_count_covered", 0),
            tokens_before_summary=row.get("tokens_before_summary", 0),
            tokens_after_summary=row.get("tokens_after_summary", 0),
            compression_ratio=row.get("compression_ratio"),
            confidence_score=row.get("confidence_score"),
            key_topics=json.loads(row["key_topics"]) if row.get("key_topics") else [],
            key_entities=json.loads(row["key_entities"]) if row.get("key_entities") else [],
            created_at=row["created_at"],
            updated_at=row["created_at"]
        )

    # ==================== BaseRepository Implementation ====================

    async def get(self, entity_id: EntityId) -> Optional[ConversationEntity]:
        """Get conversation by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM conversations WHERE id = $1
                """,
                self._to_uuid(entity_id)
            )
            return self._row_to_conversation(row) if row else None

    async def create(self, entity: ConversationEntity) -> ConversationEntity:
        """Create a new conversation."""
        async with self._pool.acquire() as conn:
            await self._set_user_context(conn, entity.user_id)

            entity_id = entity.id or str(uuid4())
            now = datetime.utcnow()

            row = await conn.fetchrow(
                """
                INSERT INTO conversations (
                    id, user_id, project_id, session_id, title,
                    message_count, total_tokens, is_archived, is_starred,
                    is_deleted, strategy, language, metadata,
                    created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
                )
                RETURNING *
                """,
                UUID(entity_id),
                entity.user_id,
                entity.project_id,
                entity.session_id,
                entity.title,
                entity.message_count,
                entity.total_tokens,
                entity.is_archived,
                entity.is_starred,
                entity.is_deleted,
                entity.strategy,
                entity.language,
                json.dumps(entity.metadata),
                now,
                now
            )
            return self._row_to_conversation(row)

    async def update(self, entity: ConversationEntity) -> ConversationEntity:
        """Update an existing conversation."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE conversations SET
                    title = $2,
                    project_id = $3,
                    session_id = $4,
                    is_archived = $5,
                    is_starred = $6,
                    strategy = $7,
                    language = $8,
                    metadata = $9,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                RETURNING *
                """,
                self._to_uuid(entity.id),
                entity.title,
                entity.project_id,
                entity.session_id,
                entity.is_archived,
                entity.is_starred,
                entity.strategy,
                entity.language,
                json.dumps(entity.metadata)
            )
            if not row:
                raise ValueError(f"Conversation {entity.id} not found")
            return self._row_to_conversation(row)

    async def delete(self, entity_id: EntityId) -> bool:
        """Hard delete a conversation."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM conversations WHERE id = $1",
                self._to_uuid(entity_id)
            )
            return result == "DELETE 1"

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ConversationEntity]:
        """List conversations with optional filters."""
        async with self._pool.acquire() as conn:
            query = """
                SELECT * FROM conversations
                WHERE is_deleted = FALSE
            """
            params = []
            param_idx = 1

            if filters:
                if "user_id" in filters:
                    query += f" AND user_id = ${param_idx}"
                    params.append(filters["user_id"])
                    param_idx += 1

                if "is_archived" in filters:
                    query += f" AND is_archived = ${param_idx}"
                    params.append(filters["is_archived"])
                    param_idx += 1

                if "project_id" in filters:
                    query += f" AND project_id = ${param_idx}"
                    params.append(filters["project_id"])
                    param_idx += 1

            query += f" ORDER BY updated_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
            params.extend([limit, skip])

            rows = await conn.fetch(query, *params)
            return [self._row_to_conversation(row) for row in rows]

    async def exists(self, entity_id: EntityId) -> bool:
        """Check if conversation exists."""
        async with self._pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM conversations WHERE id = $1)",
                self._to_uuid(entity_id)
            )
            return result

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count conversations matching filters."""
        async with self._pool.acquire() as conn:
            query = "SELECT COUNT(*) FROM conversations WHERE is_deleted = FALSE"
            params = []
            param_idx = 1

            if filters:
                if "user_id" in filters:
                    query += f" AND user_id = ${param_idx}"
                    params.append(filters["user_id"])
                    param_idx += 1

            return await conn.fetchval(query, *params)

    # ==================== Conversation Operations ====================

    async def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        include_archived: bool = False,
        include_deleted: bool = False
    ) -> List[ConversationEntity]:
        """Get conversations for a specific user."""
        async with self._pool.acquire() as conn:
            await self._set_user_context(conn, user_id)

            query = """
                SELECT * FROM conversations
                WHERE user_id = $1
            """
            if not include_deleted:
                query += " AND is_deleted = FALSE"
            if not include_archived:
                query += " AND is_archived = FALSE"

            query += " ORDER BY updated_at DESC LIMIT $2 OFFSET $3"

            rows = await conn.fetch(query, user_id, limit, skip)
            return [self._row_to_conversation(row) for row in rows]

    async def get_by_project(
        self,
        project_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[ConversationEntity]:
        """Get conversations for a specific project."""
        async with self._pool.acquire() as conn:
            await self._set_user_context(conn, user_id)

            rows = await conn.fetch(
                """
                SELECT * FROM conversations
                WHERE project_id = $1 AND user_id = $2 AND is_deleted = FALSE
                ORDER BY updated_at DESC
                LIMIT $3 OFFSET $4
                """,
                project_id, user_id, limit, skip
            )
            return [self._row_to_conversation(row) for row in rows]

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[Tuple[ConversationEntity, float]]:
        """Full-text search across conversation messages."""
        async with self._pool.acquire() as conn:
            await self._set_user_context(conn, user_id)

            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (c.id)
                    c.*,
                    ts_rank(to_tsvector('english', m.content), plainto_tsquery('english', $2)) as rank
                FROM conversations c
                JOIN messages m ON m.conversation_id = c.id
                WHERE c.user_id = $1
                    AND c.is_deleted = FALSE
                    AND m.is_deleted = FALSE
                    AND to_tsvector('english', m.content) @@ plainto_tsquery('english', $2)
                ORDER BY c.id, rank DESC
                LIMIT $3
                """,
                user_id, query, limit
            )

            results = []
            for row in rows:
                conv = self._row_to_conversation(row)
                rank = float(row["rank"]) if row["rank"] else 0.0
                results.append((conv, rank))

            return sorted(results, key=lambda x: x[1], reverse=True)

    async def soft_delete(
        self,
        conversation_id: EntityId,
        deleted_by: str
    ) -> bool:
        """Soft delete a conversation."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE conversations SET
                    is_deleted = TRUE,
                    deleted_at = CURRENT_TIMESTAMP,
                    deleted_by = $2,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                self._to_uuid(conversation_id),
                deleted_by
            )
            return result == "UPDATE 1"

    async def restore(self, conversation_id: EntityId) -> bool:
        """Restore a soft-deleted conversation."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE conversations SET
                    is_deleted = FALSE,
                    deleted_at = NULL,
                    deleted_by = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                self._to_uuid(conversation_id)
            )
            return result == "UPDATE 1"

    async def archive(
        self,
        conversation_id: EntityId,
        archived: bool = True
    ) -> bool:
        """Toggle archive status."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE conversations SET
                    is_archived = $2,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                self._to_uuid(conversation_id),
                archived
            )
            return result == "UPDATE 1"

    async def star(
        self,
        conversation_id: EntityId,
        starred: bool = True
    ) -> bool:
        """Toggle starred status."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE conversations SET
                    is_starred = $2,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                self._to_uuid(conversation_id),
                starred
            )
            return result == "UPDATE 1"

    # ==================== Message Operations ====================

    async def add_message(
        self,
        conversation_id: EntityId,
        role: str,
        content: str,
        parent_message_id: Optional[EntityId] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        model: Optional[str] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        rag_context: Optional[Dict[str, Any]] = None
    ) -> MessageEntity:
        """Add a message to a conversation."""
        async with self._pool.acquire() as conn:
            # Get branch info from parent if exists
            branch_root_id = None
            branch_depth = 0

            if parent_message_id:
                parent = await conn.fetchrow(
                    "SELECT branch_root_id, branch_depth FROM messages WHERE id = $1",
                    self._to_uuid(parent_message_id)
                )
                if parent:
                    branch_root_id = parent["branch_root_id"]
                    branch_depth = parent["branch_depth"] + 1

            message_id = uuid4()
            now = datetime.utcnow()

            row = await conn.fetchrow(
                """
                INSERT INTO messages (
                    id, conversation_id, parent_message_id, role, content,
                    input_tokens, output_tokens, total_tokens, model,
                    sources, rag_context, branch_root_id, branch_depth,
                    is_active_branch, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
                )
                RETURNING *
                """,
                message_id,
                self._to_uuid(conversation_id),
                self._to_uuid(parent_message_id),
                role,
                content,
                input_tokens,
                output_tokens,
                total_tokens,
                model,
                json.dumps(sources or []),
                json.dumps(rag_context or {}),
                self._to_uuid(branch_root_id) if branch_root_id else None,
                branch_depth,
                True,
                now,
                now
            )

            return self._row_to_message(row)

    async def get_messages(
        self,
        conversation_id: EntityId,
        include_inactive_branches: bool = False,
        include_deleted: bool = False,
        skip: int = 0,
        limit: int = 100
    ) -> List[MessageEntity]:
        """Get messages in a conversation."""
        async with self._pool.acquire() as conn:
            query = """
                SELECT * FROM messages
                WHERE conversation_id = $1
            """
            if not include_deleted:
                query += " AND is_deleted = FALSE"
            if not include_inactive_branches:
                query += " AND is_active_branch = TRUE"

            query += " ORDER BY created_at LIMIT $2 OFFSET $3"

            rows = await conn.fetch(
                query,
                self._to_uuid(conversation_id),
                limit,
                skip
            )
            return [self._row_to_message(row) for row in rows]

    async def get_active_branch_messages(
        self,
        conversation_id: EntityId,
        limit: int = 100
    ) -> List[MessageEntity]:
        """Get only active branch messages."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM get_active_messages($1)
                LIMIT $2
                """,
                self._to_uuid(conversation_id),
                limit
            )
            # The helper function returns limited columns, so we need to fetch full records
            message_ids = [row["id"] for row in rows]
            if not message_ids:
                return []

            full_rows = await conn.fetch(
                """
                SELECT * FROM messages
                WHERE id = ANY($1)
                ORDER BY created_at
                """,
                message_ids
            )
            return [self._row_to_message(row) for row in full_rows]

    async def get_message(self, message_id: EntityId) -> Optional[MessageEntity]:
        """Get a specific message by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM messages WHERE id = $1",
                self._to_uuid(message_id)
            )
            return self._row_to_message(row) if row else None

    async def update_message_feedback(
        self,
        message_id: EntityId,
        score: int,
        text: Optional[str] = None
    ) -> bool:
        """Update feedback for a message."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE messages SET
                    feedback_score = $2,
                    feedback_text = $3,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                self._to_uuid(message_id),
                score,
                text
            )
            return result == "UPDATE 1"

    async def regenerate_message(
        self,
        original_message_id: EntityId,
        new_content: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        model: Optional[str] = None,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[MessageEntity, MessageEntity]:
        """Create a regenerated version of a message."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Get original message
                original = await conn.fetchrow(
                    "SELECT * FROM messages WHERE id = $1",
                    self._to_uuid(original_message_id)
                )
                if not original:
                    raise ValueError(f"Message {original_message_id} not found")

                # Mark original as inactive
                await conn.execute(
                    """
                    UPDATE messages SET
                        is_active_branch = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $1
                    """,
                    self._to_uuid(original_message_id)
                )

                # Calculate regeneration count
                regen_count = original["regeneration_count"] + 1

                # Create new message with same parent
                new_id = uuid4()
                now = datetime.utcnow()

                new_row = await conn.fetchrow(
                    """
                    INSERT INTO messages (
                        id, conversation_id, parent_message_id, role, content,
                        input_tokens, output_tokens, total_tokens, model,
                        sources, rag_context, is_regenerated, regeneration_count,
                        original_message_id, branch_root_id, branch_depth,
                        is_active_branch, created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
                    )
                    RETURNING *
                    """,
                    new_id,
                    original["conversation_id"],
                    original["parent_message_id"],
                    original["role"],
                    new_content,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    model,
                    json.dumps(sources or []),
                    json.dumps({}),
                    True,
                    regen_count,
                    self._to_uuid(original_message_id),
                    original["branch_root_id"],
                    original["branch_depth"],
                    True,
                    now,
                    now
                )

                # Fetch updated original
                updated_original = await conn.fetchrow(
                    "SELECT * FROM messages WHERE id = $1",
                    self._to_uuid(original_message_id)
                )

                return (
                    self._row_to_message(new_row),
                    self._row_to_message(updated_original)
                )

    async def soft_delete_message(self, message_id: EntityId) -> bool:
        """Soft delete a message."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE messages SET
                    is_deleted = TRUE,
                    deleted_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                self._to_uuid(message_id)
            )
            return result == "UPDATE 1"

    # ==================== Fork Operations ====================

    async def fork_conversation(
        self,
        conversation_id: EntityId,
        from_message_id: EntityId,
        new_user_id: str,
        new_title: Optional[str] = None,
        include_system_messages: bool = True
    ) -> Tuple[ConversationEntity, int]:
        """Fork a conversation from a specific message point."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Get original conversation
                original_conv = await conn.fetchrow(
                    "SELECT * FROM conversations WHERE id = $1",
                    self._to_uuid(conversation_id)
                )
                if not original_conv:
                    raise ValueError(f"Conversation {conversation_id} not found")

                # Verify fork point message exists
                fork_point = await conn.fetchrow(
                    "SELECT * FROM messages WHERE id = $1 AND conversation_id = $2",
                    self._to_uuid(from_message_id),
                    self._to_uuid(conversation_id)
                )
                if not fork_point:
                    raise ValueError(f"Fork point message {from_message_id} not found")

                # Create new conversation
                new_conv_id = uuid4()
                now = datetime.utcnow()
                title = new_title or f"Fork of {original_conv['title'] or 'Untitled'}"

                new_conv_row = await conn.fetchrow(
                    """
                    INSERT INTO conversations (
                        id, user_id, project_id, session_id, title,
                        strategy, language, metadata, created_at, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10
                    )
                    RETURNING *
                    """,
                    new_conv_id,
                    new_user_id,
                    original_conv["project_id"],
                    None,  # New session
                    title,
                    original_conv["strategy"],
                    original_conv["language"],
                    json.dumps({"forked_from": str(conversation_id), "fork_point": str(from_message_id)}),
                    now,
                    now
                )

                # Get messages to copy (up to and including fork point)
                query = """
                    SELECT * FROM messages
                    WHERE conversation_id = $1
                        AND is_deleted = FALSE
                        AND is_active_branch = TRUE
                        AND created_at <= (
                            SELECT created_at FROM messages WHERE id = $2
                        )
                """
                if not include_system_messages:
                    query += " AND role != 'system'"
                query += " ORDER BY created_at"

                messages_to_copy = await conn.fetch(
                    query,
                    self._to_uuid(conversation_id),
                    self._to_uuid(from_message_id)
                )

                # Copy messages with new IDs
                old_to_new_id: Dict[str, str] = {}
                messages_copied = 0

                for msg in messages_to_copy:
                    new_msg_id = uuid4()
                    old_to_new_id[str(msg["id"])] = str(new_msg_id)

                    # Map parent_message_id
                    new_parent_id = None
                    if msg["parent_message_id"]:
                        old_parent = str(msg["parent_message_id"])
                        new_parent_id = UUID(old_to_new_id.get(old_parent, old_parent))

                    await conn.execute(
                        """
                        INSERT INTO messages (
                            id, conversation_id, parent_message_id, role, content,
                            input_tokens, output_tokens, total_tokens, model,
                            sources, rag_context, branch_depth, is_active_branch,
                            created_at, updated_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15
                        )
                        """,
                        new_msg_id,
                        new_conv_id,
                        new_parent_id,
                        msg["role"],
                        msg["content"],
                        msg["input_tokens"],
                        msg["output_tokens"],
                        msg["total_tokens"],
                        msg["model"],
                        msg["sources"],
                        msg["rag_context"],
                        msg["branch_depth"],
                        True,
                        now,
                        now
                    )
                    messages_copied += 1

                return (
                    self._row_to_conversation(new_conv_row),
                    messages_copied
                )

    async def get_fork_tree(self, message_id: EntityId) -> List[MessageEntity]:
        """Get all message branches from a specific point."""
        async with self._pool.acquire() as conn:
            # Get all messages with same parent (branches)
            msg = await conn.fetchrow(
                "SELECT parent_message_id FROM messages WHERE id = $1",
                self._to_uuid(message_id)
            )
            if not msg or not msg["parent_message_id"]:
                return []

            rows = await conn.fetch(
                """
                SELECT * FROM messages
                WHERE parent_message_id = $1 AND is_deleted = FALSE
                ORDER BY created_at
                """,
                msg["parent_message_id"]
            )
            return [self._row_to_message(row) for row in rows]

    # ==================== Summary Operations ====================

    async def add_summary(
        self,
        conversation_id: EntityId,
        summary_text: str,
        summary_type: str = "rolling",
        covers_from_id: Optional[EntityId] = None,
        covers_to_id: Optional[EntityId] = None,
        message_count: int = 0,
        tokens_before: int = 0,
        tokens_after: int = 0,
        key_topics: Optional[List[str]] = None,
        key_entities: Optional[List[str]] = None
    ) -> SummaryEntity:
        """Add a conversation summary."""
        async with self._pool.acquire() as conn:
            summary_id = uuid4()
            now = datetime.utcnow()

            compression_ratio = None
            if tokens_before > 0:
                compression_ratio = tokens_after / tokens_before

            row = await conn.fetchrow(
                """
                INSERT INTO conversation_summaries (
                    id, conversation_id, summary_text, summary_type,
                    covers_from_message_id, covers_to_message_id,
                    message_count_covered, tokens_before_summary, tokens_after_summary,
                    compression_ratio, key_topics, key_entities, created_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
                )
                RETURNING *
                """,
                summary_id,
                self._to_uuid(conversation_id),
                summary_text,
                summary_type,
                self._to_uuid(covers_from_id),
                self._to_uuid(covers_to_id),
                message_count,
                tokens_before,
                tokens_after,
                compression_ratio,
                json.dumps(key_topics or []),
                json.dumps(key_entities or []),
                now
            )
            return self._row_to_summary(row)

    async def get_latest_summary(
        self,
        conversation_id: EntityId
    ) -> Optional[SummaryEntity]:
        """Get the most recent summary for a conversation."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM conversation_summaries
                WHERE conversation_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                self._to_uuid(conversation_id)
            )
            return self._row_to_summary(row) if row else None

    async def get_summaries(
        self,
        conversation_id: EntityId,
        summary_type: Optional[str] = None
    ) -> List[SummaryEntity]:
        """Get all summaries for a conversation."""
        async with self._pool.acquire() as conn:
            if summary_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM conversation_summaries
                    WHERE conversation_id = $1 AND summary_type = $2
                    ORDER BY created_at DESC
                    """,
                    self._to_uuid(conversation_id),
                    summary_type
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM conversation_summaries
                    WHERE conversation_id = $1
                    ORDER BY created_at DESC
                    """,
                    self._to_uuid(conversation_id)
                )
            return [self._row_to_summary(row) for row in rows]

    # ==================== Context Window Operations ====================

    async def get_context_window(
        self,
        conversation_id: EntityId,
        max_tokens: int = 4000,
        include_summary: bool = True
    ) -> Dict[str, Any]:
        """Get messages fitting in context window."""
        async with self._pool.acquire() as conn:
            # Use PostgreSQL helper function
            rows = await conn.fetch(
                """
                SELECT * FROM get_context_window_messages($1, $2)
                """,
                self._to_uuid(conversation_id),
                max_tokens
            )

            # Get full message details
            message_ids = [row["id"] for row in rows]
            if message_ids:
                full_rows = await conn.fetch(
                    """
                    SELECT * FROM messages
                    WHERE id = ANY($1)
                    ORDER BY created_at
                    """,
                    message_ids
                )
                messages = [self._row_to_message(row) for row in full_rows]
            else:
                messages = []

            # Get summary if requested
            summary = None
            messages_summarized = 0
            if include_summary:
                summary_entity = await self.get_latest_summary(conversation_id)
                if summary_entity:
                    summary = summary_entity.summary_text
                    messages_summarized = summary_entity.message_count_covered

            total_tokens = sum(m.total_tokens for m in messages)

            return {
                "messages": messages,
                "summary": summary,
                "total_tokens": total_tokens,
                "messages_included": len(messages),
                "messages_summarized": messages_summarized
            }

    async def get_token_count(
        self,
        conversation_id: EntityId,
        active_branch_only: bool = True
    ) -> int:
        """Get total token count for a conversation."""
        async with self._pool.acquire() as conn:
            if active_branch_only:
                result = await conn.fetchval(
                    "SELECT get_conversation_token_count($1)",
                    self._to_uuid(conversation_id)
                )
            else:
                result = await conn.fetchval(
                    """
                    SELECT COALESCE(SUM(total_tokens), 0)
                    FROM messages
                    WHERE conversation_id = $1 AND is_deleted = FALSE
                    """,
                    self._to_uuid(conversation_id)
                )
            return result or 0

    # ==================== Statistics ====================

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get conversation statistics for a user."""
        async with self._pool.acquire() as conn:
            await self._set_user_context(conn, user_id)

            stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE is_deleted = FALSE) as total_conversations,
                    COUNT(*) FILTER (WHERE is_deleted = FALSE AND is_archived = FALSE) as active_conversations,
                    COUNT(*) FILTER (WHERE is_deleted = FALSE AND is_archived = TRUE) as archived_conversations,
                    COALESCE(SUM(message_count) FILTER (WHERE is_deleted = FALSE), 0) as total_messages,
                    COALESCE(SUM(total_tokens) FILTER (WHERE is_deleted = FALSE), 0) as total_tokens
                FROM conversations
                WHERE user_id = $1
                """,
                user_id
            )

            return {
                "total_conversations": stats["total_conversations"] or 0,
                "active_conversations": stats["active_conversations"] or 0,
                "archived_conversations": stats["archived_conversations"] or 0,
                "total_messages": stats["total_messages"] or 0,
                "total_tokens": stats["total_tokens"] or 0
            }
