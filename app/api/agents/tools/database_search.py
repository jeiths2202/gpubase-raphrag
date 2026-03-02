"""Database Search Module

Contains Neo4j vector search, PostgreSQL keyword search, and exact phrase search.
"""
import logging
import os
from typing import Dict, Any, Optional, List

from ...services.scoring_config_service import get_scoring_config_sync
from ...models.scoring_config import ScoringConfig
from ..types import AgentContext

logger = logging.getLogger(__name__)


async def execute_pg_query(query: str) -> List[Dict]:
    """Execute a raw SQL query on PostgreSQL"""
    try:
        import asyncpg
        from ...core.config import api_settings

        dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"PostgreSQL query failed: {e}")
        return []


async def neo4j_vector_search(
    rag_service,
    query: str,
    top_k: int,
    language: str,
    context: AgentContext
) -> List[Dict[str, Any]]:
    """Execute vector search via Neo4j using RAGService"""
    logger.debug(f"Neo4j vector search: rag_service={rag_service is not None}")
    try:
        if rag_service is None:
            logger.error("RAG service is None - cannot execute Neo4j search")
            return []

        result = await rag_service.query(
            question=query,
            strategy="hybrid",
            language=language,
            top_k=top_k * 2,  # Fetch more for fusion
            session_id=context.session_id,
            user_id=context.user_id
        )

        sources = result.get("sources", [])
        neo4j_results = []

        # Debug: Log scores
        if sources:
            logger.info(f"[neo4j_vector_search] Sources count: {len(sources)}")
            for i, src in enumerate(sources[:3]):
                score = src.get("score", "MISSING")
                doc_name = src.get("doc_name", "?")[:30]
                logger.info(f"  [{i}] doc_name={doc_name}, score={score}")

        for i, source in enumerate(sources):
            neo4j_results.append({
                "chunk_id": source.get("doc_id", f"neo4j_{i}"),
                "content": source.get("content", ""),
                "score": source.get("score", 0.0),
                "source": source.get("doc_name") or source.get("source", "Unknown"),
                "doc_id": source.get("doc_id", ""),
                "page_number": source.get("page_number"),
                "rank": i + 1,
                "origin": "neo4j",
                "source_type": source.get("source_type", "document"),
                "source_url": source.get("source_url", "")
            })

        logger.info(f"Neo4j returned {len(neo4j_results)} results")
        return neo4j_results

    except Exception as e:
        logger.error(f"Neo4j vector search error: {e}", exc_info=True)
        return []


async def postgres_keyword_search(
    query: str,
    top_k: int,
    doc_filter: Optional[str] = None,
    error_codes: Optional[List[str]] = None,
    scoring_config: Optional[ScoringConfig] = None
) -> List[Dict[str, Any]]:
    """Execute keyword search via PostgreSQL ts_rank"""
    try:
        # Load config
        config = scoring_config or get_scoring_config_sync()
        error_code_boost = config.boost.error_code_boost

        # Build search terms for ts_query
        terms = query.split()
        ts_terms = " | ".join([t.replace("'", "''") for t in terms if t])

        # Build error code boost condition
        error_boost_sql = ""
        if error_codes:
            error_patterns = " OR ".join([
                f"content ILIKE '%{code}%'" for code in error_codes
            ])
            error_boost_sql = f"""
                CASE WHEN ({error_patterns}) THEN {error_code_boost} ELSE 1.0 END as error_boost,
            """

        # Build document filter
        doc_filter_sql = ""
        if doc_filter:
            safe_filter = doc_filter.replace("'", "''")
            if doc_filter.startswith("doc_"):
                doc_filter_sql = f"AND pdf_id = '{safe_filter}'"
            else:
                doc_filter_sql = f"AND pdf_id IN (SELECT id FROM documents WHERE filename ILIKE '%{safe_filter}%' OR original_name ILIKE '%{safe_filter}%')"
                logger.info(f"[postgres_keyword_search] doc_filter '{doc_filter}' using fuzzy filename match")

        # PostgreSQL full-text search with ts_rank
        sql = f"""
            SELECT
                chunk_id,
                pdf_id,
                content,
                chunk_type,
                page_start,
                page_end,
                section_title,
                section_path,
                relations,
                {error_boost_sql}
                ts_rank(
                    to_tsvector('simple', content),
                    plainto_tsquery('simple', '{ts_terms}')
                ) as keyword_score
            FROM adaptive_pdf_chunks
            WHERE to_tsvector('simple', content) @@ plainto_tsquery('simple', '{ts_terms}')
            {doc_filter_sql}
            ORDER BY keyword_score DESC
            LIMIT {top_k * 2}
        """

        rows = await execute_pg_query(sql)

        postgres_results = []
        for i, row in enumerate(rows):
            score = row.get("keyword_score", 0)
            error_boost = row.get("error_boost", 1.0)
            final_score = score * (error_boost if error_boost else 1.0)

            postgres_results.append({
                "chunk_id": row.get("chunk_id"),
                "content": row.get("content", ""),
                "score": final_score,
                "source": row.get("pdf_id", "Unknown"),
                "doc_id": row.get("pdf_id", ""),
                "page_start": row.get("page_start"),
                "page_end": row.get("page_end"),
                "section_title": row.get("section_title"),
                "section_path": row.get("section_path"),
                "chunk_type": row.get("chunk_type", "TEXT"),
                "relations": row.get("relations", {}),
                "rank": i + 1,
                "origin": "postgres",
                "error_boosted": error_boost > 1.0 if error_boost else False
            })

        logger.info(f"[postgres_keyword_search] PostgreSQL returned {len(postgres_results)} results")
        return postgres_results

    except Exception as e:
        logger.error(f"PostgreSQL keyword search error: {e}")
        return []


async def exact_phrase_search(
    exact_phrases: List[str],
    top_k: int = 10,
    web_only: bool = False
) -> List[Dict[str, Any]]:
    """
    Search for chunks containing exact phrases in Neo4j.
    This is a direct string match search to complement vector search.

    Args:
        exact_phrases: List of exact phrases to search for
        top_k: Maximum number of results
        web_only: If True, only search web sources
    """
    if not exact_phrases:
        return []

    try:
        from neo4j import GraphDatabase

        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "")

        driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )

        results = []
        with driver.session() as session:
            for phrase in exact_phrases:
                phrase_lower = phrase.lower()

                # Build query based on web_only filter
                if web_only:
                    query_result = session.run("""
                        MATCH (c:Chunk)
                        WHERE toLower(c.content) CONTAINS $phrase
                          AND c.source_type = 'web'
                        OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                        RETURN c.id AS chunk_id,
                               c.content AS content,
                               c.source_type AS source_type,
                               c.source_url AS source_url,
                               c.index AS chunk_index,
                               d.id AS doc_id,
                               d.title AS doc_title
                        LIMIT $limit
                    """, phrase=phrase_lower, limit=top_k)
                else:
                    query_result = session.run("""
                        MATCH (c:Chunk)
                        WHERE toLower(c.content) CONTAINS $phrase
                        OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                        RETURN c.id AS chunk_id,
                               c.content AS content,
                               c.source_type AS source_type,
                               c.source_url AS source_url,
                               c.index AS chunk_index,
                               d.id AS doc_id,
                               d.title AS doc_title
                        LIMIT $limit
                    """, phrase=phrase_lower, limit=top_k)

                for record in query_result:
                    content = record["content"] or ""
                    source_type = record["source_type"] or "document"
                    doc_id = record["doc_id"] or record["chunk_id"]

                    results.append({
                        "chunk_id": record["chunk_id"],
                        "content": content,
                        "score": 1.0,
                        "source": doc_id,
                        "doc_id": doc_id,
                        "document_name": record["doc_title"] or doc_id,
                        "source_type": source_type,
                        "source_url": record["source_url"] or "",
                        "rank": len(results) + 1,
                        "origin": "exact_phrase",
                        "exact_phrase_match": True,
                        "matched_phrases": [phrase]
                    })

        driver.close()

        logger.info(f"Exact phrase search found {len(results)} results for phrases: {exact_phrases}")
        return results

    except Exception as e:
        logger.error(f"Exact phrase search error: {e}")
        return []


async def graph_traversal_search(
    query: str,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Graph-based search using Entity relationships.

    Strategy:
    1. Extract keywords from query
    2. Find Chunks containing those keywords
    3. Find Entities related to those keywords
    4. Return chunks connected via MENTIONS relationships
    """
    try:
        from neo4j import GraphDatabase

        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "")

        driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )

        results = []

        # Extract keywords for graph search
        keywords = [w.strip() for w in query.split() if len(w.strip()) > 2]
        keywords = [w for w in keywords if w.lower() not in {"the", "is", "of", "and", "a", "를", "을", "이", "가", "에", "は", "の", "を", "が"}]

        if not keywords:
            logger.debug("[GraphSearch] No valid keywords extracted")
            driver.close()
            return []

        with driver.session() as session:
            for keyword in keywords[:3]:
                # Search for entities matching keyword
                entity_results = session.run("""
                    MATCH (e:Entity)
                    WHERE toLower(e.name) CONTAINS toLower($keyword)
                    MATCH (c:Chunk)-[:MENTIONS]->(e)
                    OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                    RETURN DISTINCT
                        c.id AS chunk_id,
                        c.content AS content,
                        e.name AS entity_name,
                        e.type AS entity_type,
                        d.id AS doc_id,
                        d.title AS doc_title
                    LIMIT $limit
                """, keyword=keyword, limit=top_k)

                for record in entity_results:
                    chunk_id = record["chunk_id"]

                    # Avoid duplicates
                    if any(r["chunk_id"] == chunk_id for r in results):
                        continue

                    content = record["content"] or ""
                    doc_id = record["doc_id"] or chunk_id

                    results.append({
                        "chunk_id": chunk_id,
                        "content": content,
                        "score": 0.8,  # Graph match score
                        "source": doc_id,
                        "doc_id": doc_id,
                        "document_name": record["doc_title"] or doc_id,
                        "entity_name": record["entity_name"],
                        "entity_type": record["entity_type"],
                        "rank": len(results) + 1,
                        "origin": "graph",
                        "graph_match": True
                    })

                if len(results) >= top_k:
                    break

        driver.close()

        logger.info(f"[GraphSearch] Found {len(results)} graph results for keywords: {keywords[:3]}")
        return results[:top_k]

    except Exception as e:
        logger.error(f"[GraphSearch] Error: {e}")
        return []
