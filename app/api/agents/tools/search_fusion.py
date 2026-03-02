"""Search Result Fusion Module

RRF (Reciprocal Rank Fusion) and hybrid merge algorithms.
Extracted from unified_search.py for code organization.
"""
import logging
from typing import Dict, Any, List, Optional

from ...services.scoring_config_service import get_scoring_config_sync
from ...models.scoring_config import ScoringConfig

logger = logging.getLogger(__name__)


def rrf_fusion(
    neo4j_results: List[Dict],
    postgres_results: List[Dict],
    error_codes: List[str],
    k: Optional[int] = None,
    prioritize_web: bool = False,
    scoring_config: Optional[ScoringConfig] = None
) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion (RRF) to combine search results.
    RRF score = 1/(k + rank_v) + 1/(k + rank_k) + error_boost
    """
    config = scoring_config or get_scoring_config_sync()

    if k is None:
        k = config.rrf.k

    no_result_rank = config.search.no_result_rank
    web_priority_boost = config.boost.web_priority_boost
    web_priority_penalty = config.boost.web_priority_penalty
    error_code_boost = config.boost.error_code_boost
    web_normal_rank_threshold = config.boost.web_normal_rank_threshold
    web_normal_rank_offset = config.boost.web_normal_rank_offset

    all_chunks = {}

    # Process Neo4j results
    for result in neo4j_results:
        key = result.get("chunk_id") or hash(result.get("content", "")[:200])
        all_chunks[key] = {
            **result,
            "neo4j_rank": result.get("rank", no_result_rank),
            "postgres_rank": no_result_rank,
            "rrf_score": 0.0
        }

    # Process PostgreSQL results
    for result in postgres_results:
        key = result.get("chunk_id") or hash(result.get("content", "")[:200])
        if key in all_chunks:
            all_chunks[key]["postgres_rank"] = result.get("rank", no_result_rank)
            all_chunks[key]["postgres_data"] = result
        else:
            all_chunks[key] = {
                **result,
                "neo4j_rank": no_result_rank,
                "postgres_rank": result.get("rank", no_result_rank),
                "rrf_score": 0.0
            }

    # Calculate RRF scores
    for key, chunk in all_chunks.items():
        neo4j_rank = chunk.get("neo4j_rank", no_result_rank)
        postgres_rank = chunk.get("postgres_rank", no_result_rank)
        rrf_score = 1.0 / (k + neo4j_rank) + 1.0 / (k + postgres_rank)
        source_type = chunk.get("source_type", "")

        if prioritize_web:
            if source_type == "web":
                simulated_postgres_rank = min(neo4j_rank, 3)
                rrf_score = 1.0 / (k + neo4j_rank) + 1.0 / (k + simulated_postgres_rank)
                rrf_score *= web_priority_boost
                chunk["web_priority_boosted"] = True
            else:
                rrf_score *= web_priority_penalty
                chunk["web_priority_penalized"] = True
        else:
            if source_type == "web" and postgres_rank == no_result_rank and neo4j_rank <= web_normal_rank_threshold:
                simulated_postgres_rank = neo4j_rank + web_normal_rank_offset
                rrf_score = 1.0 / (k + neo4j_rank) + 1.0 / (k + simulated_postgres_rank)
                chunk["web_boosted"] = True

        # Error code boosting
        content = chunk.get("content", "")
        if error_codes and any(code in content for code in error_codes):
            rrf_score *= error_code_boost
            chunk["error_boosted"] = True

        chunk["rrf_score"] = rrf_score

    sorted_chunks = sorted(all_chunks.values(), key=lambda x: x.get("rrf_score", 0), reverse=True)

    if prioritize_web:
        web_only = [c for c in sorted_chunks if c.get("source_type") == "web"]
        if web_only:
            logger.info(f"[RRF] Web priority mode: {len(web_only)} web-only results")
            return web_only
        logger.warning(f"[RRF] Web priority mode but no web sources, returning {len(sorted_chunks)} general results")

    logger.info(f"[RRF] Fusion produced {len(sorted_chunks)} unique results")
    return sorted_chunks


def simple_hybrid_merge(
    neo4j_results: List[Dict],
    postgres_results: List[Dict],
    error_codes: List[str],
    scoring_config: Optional[ScoringConfig] = None
) -> List[Dict]:
    """
    Simple hybrid merge WITHOUT RRF score calculation.
    Uses Neo4j vector scores directly, marks results also in PostgreSQL.
    """
    config = scoring_config or get_scoring_config_sync()
    keyword_only_default_score = config.search.keyword_only_default_score

    postgres_chunk_ids = {r.get("chunk_id") for r in postgres_results if r.get("chunk_id")}

    merged = []
    for result in neo4j_results:
        chunk_id = result.get("chunk_id")
        if chunk_id in postgres_chunk_ids:
            result["keyword_match"] = True
            result["source_type"] = "hybrid"
        else:
            result["keyword_match"] = False
            result["source_type"] = "vector"
        merged.append(result)

    # Add PostgreSQL-only results
    neo4j_chunk_ids = {r.get("chunk_id") for r in neo4j_results if r.get("chunk_id")}
    for result in postgres_results:
        chunk_id = result.get("chunk_id")
        if chunk_id and chunk_id not in neo4j_chunk_ids:
            result["keyword_match"] = True
            result["source_type"] = "keyword"
            if "score" not in result:
                result["score"] = keyword_only_default_score
            merged.append(result)

    merged.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Error code boost
    if error_codes:
        for result in merged:
            content = result.get("content", "").lower()
            if any(code.lower() in content for code in error_codes):
                result["error_match"] = True

    logger.info(f"[HybridMerge] {len(merged)} results ({sum(1 for r in merged if r.get('keyword_match'))} keyword match)")
    return merged


def apply_web_priority(results: List[Dict]) -> List[Dict]:
    """Apply web source priority boosting."""
    web_results = [r for r in results if r.get("source_type") == "web"]
    non_web = [r for r in results if r.get("source_type") != "web"]

    if web_results:
        logger.info(f"[WebPriority] {len(web_results)} web sources prioritized")
        return web_results + non_web
    return results


def apply_exact_phrase_priority(results: List[Dict], exact_phrases: List[str]) -> List[Dict]:
    """Prioritize results containing exact phrases."""
    if not exact_phrases:
        return results

    exact_match = []
    partial_match = []
    no_match = []

    for result in results:
        content = result.get("content", "").lower()
        all_match = all(phrase.lower() in content for phrase in exact_phrases)
        any_match = any(phrase.lower() in content for phrase in exact_phrases)

        if all_match:
            result["exact_phrase_match"] = True
            exact_match.append(result)
        elif any_match:
            result["exact_phrase_partial"] = True
            partial_match.append(result)
        else:
            no_match.append(result)

    combined = exact_match + partial_match + no_match
    logger.debug(f"Exact phrase priority: {len(exact_match)} exact, {len(partial_match)} partial")
    return combined
