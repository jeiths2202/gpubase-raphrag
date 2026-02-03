"""Chunk Processing Module

Contains chunk linking and expansion logic.
"""
import logging
import os
from typing import Dict, Any, Optional, List

from ...services.scoring_config_service import get_scoring_config_sync
from ...models.scoring_config import ScoringConfig

logger = logging.getLogger(__name__)


async def fetch_linked_chunks(
    results: List[Dict[str, Any]],
    num_following: int = 2,
    web_only: bool = False,
    scoring_config: Optional[ScoringConfig] = None
) -> List[Dict[str, Any]]:
    """
    Fetch subsequent chunks for each result to include related content.
    This helps include tables/lists that follow headers.

    Args:
        results: Search results to expand
        num_following: Number of subsequent chunks to fetch (default: 2)
        web_only: If True, only link web source chunks
        scoring_config: Optional scoring configuration

    Returns:
        Expanded results with linked chunks appended
    """
    if not results or num_following <= 0:
        return results

    # Load config
    config = scoring_config or get_scoring_config_sync()
    no_result_rank = config.search.no_result_rank

    try:
        from neo4j import GraphDatabase

        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "")

        driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_password)
        )

        linked_chunks = []
        seen_chunk_ids = set()

        # Track original chunk IDs
        for r in results:
            chunk_id = r.get("chunk_id")
            if chunk_id:
                seen_chunk_ids.add(chunk_id)

        with driver.session() as session:
            for result in results:
                chunk_id = result.get("chunk_id")
                source_type = result.get("source_type", "document")

                # Skip if web_only and not a web source
                if web_only and source_type != "web":
                    continue

                if not chunk_id:
                    continue

                # Get the index of this chunk
                index_result = session.run("""
                    MATCH (c:Chunk)
                    WHERE c.id = $chunk_id
                    RETURN c.index AS chunk_index, c.source_type AS source_type
                """, chunk_id=chunk_id)

                index_record = index_result.single()
                if not index_record or index_record["chunk_index"] is None:
                    continue

                current_index = index_record["chunk_index"]
                chunk_source_type = index_record["source_type"] or "document"

                # Fetch subsequent chunks
                if chunk_source_type == "web":
                    following_query = """
                        MATCH (c:Chunk)
                        WHERE c.source_type = 'web'
                          AND c.index > $current_index
                          AND c.index <= $max_index
                        RETURN c.id AS chunk_id,
                               c.content AS content,
                               c.source_type AS source_type,
                               c.source_url AS source_url,
                               c.index AS chunk_index
                        ORDER BY c.index ASC
                    """
                else:
                    following_query = """
                        MATCH (c:Chunk)
                        WHERE c.index > $current_index
                          AND c.index <= $max_index
                        OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                        RETURN c.id AS chunk_id,
                               c.content AS content,
                               c.source_type AS source_type,
                               c.source_url AS source_url,
                               c.index AS chunk_index,
                               d.id AS doc_id,
                               d.title AS doc_title
                        ORDER BY c.index ASC
                    """

                following_result = session.run(
                    following_query,
                    current_index=current_index,
                    max_index=current_index + num_following
                )

                for record in following_result:
                    linked_chunk_id = record["chunk_id"]
                    if linked_chunk_id in seen_chunk_ids:
                        continue

                    seen_chunk_ids.add(linked_chunk_id)
                    content = record["content"] or ""

                    # Create linked chunk result
                    linked_chunk_default_score = config.search.linked_chunk_default_score
                    linked_chunk_score_multiplier = config.search.linked_chunk_score_multiplier
                    linked_chunk = {
                        "chunk_id": linked_chunk_id,
                        "content": content,
                        "score": result.get("score", linked_chunk_default_score) * linked_chunk_score_multiplier,
                        "source": result.get("source", ""),
                        "doc_id": result.get("doc_id", ""),
                        "document_name": result.get("document_name", ""),
                        "source_type": record["source_type"] or "document",
                        "source_url": record["source_url"] or result.get("source_url", ""),
                        "rank": result.get("rank", no_result_rank) + record["chunk_index"] - current_index,
                        "origin": "linked_chunk",
                        "linked_from": chunk_id,
                        "chunk_index": record["chunk_index"],
                        "is_linked_chunk": True
                    }
                    linked_chunks.append(linked_chunk)

        driver.close()

        if linked_chunks:
            logger.debug(f"Fetched {len(linked_chunks)} linked chunks")

        return results + linked_chunks

    except Exception as e:
        logger.error(f"Chunk linking error: {e}")
        return results
