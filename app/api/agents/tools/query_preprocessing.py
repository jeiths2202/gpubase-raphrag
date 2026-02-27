"""Query Preprocessing Module

Contains query validation, semantic analysis, and special marker extraction.
"""
import logging
import re
from typing import Dict, Any, List, Tuple, Optional

from ..types import AgentContext
from .adaptive_search import _validate_query

logger = logging.getLogger(__name__)


def preprocess_query(
    query: str,
    context: AgentContext,
    query_understanding_service,
    enable_semantic_preprocessing: bool = True,
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Preprocess query: extract special markers, validate, semantic analysis.

    Args:
        query: Input query
        context: Agent context with metadata
        query_understanding_service: Service for semantic query analysis
        enable_semantic_preprocessing: Whether to run semantic analysis

    Returns:
        Tuple of (query, search_query, query_state_dict)
    """
    # Get original query from context metadata
    original_user_query = ""
    if context and context.metadata:
        original_user_query = context.metadata.get('original_query', '')

    # Option C: Block LLM query modification
    llm_modified_query = query
    if original_user_query and query != original_user_query:
        logger.info(f"[OptionC] Blocking LLM modification: '{query}' -> '{original_user_query}'")
        query = original_user_query

    # Feature: "@" prefix for web source priority search
    prioritize_web_sources = False
    if query.startswith("@"):
        prioritize_web_sources = True
        query = query[1:].strip()
    elif original_user_query.startswith("@"):
        prioritize_web_sources = True

    if prioritize_web_sources:
        logger.info(f"Web source priority mode activated for query: {query[:50]}...")

    # Feature: Exact phrase matching with double quotes
    exact_phrases = []
    quote_pattern = r'"([^"]+)"'
    quote_matches = re.findall(quote_pattern, query)
    if not quote_matches and original_user_query:
        quote_matches = re.findall(quote_pattern, original_user_query)

    if quote_matches:
        exact_phrases = [phrase.strip() for phrase in quote_matches if phrase.strip()]
        search_query = re.sub(quote_pattern, r'\1', query)
        logger.info(f"Exact phrase matching enabled: {exact_phrases}")
    else:
        search_query = query

    query_was_corrected = (llm_modified_query != query)

    # Semantic query preprocessing
    semantic_entities = []
    semantic_rewritten_query = None
    if enable_semantic_preprocessing and query_understanding_service:
        try:
            query_analysis = query_understanding_service.analyze_sync(search_query)
            semantic_entities = query_analysis.entities
            semantic_rewritten_query = query_analysis.rewritten_query

            logger.info(
                f"[SemanticSearch] Query analysis: intent={query_analysis.intent.value}, "
                f"entities={[e.value for e in semantic_entities]}, "
                f"language={query_analysis.language}"
            )

            # Store analysis in context metadata
            if context and context.metadata is not None:
                context.metadata['query_analysis'] = {
                    'intent': query_analysis.intent.value,
                    'entities': [{'type': e.type, 'value': e.value} for e in semantic_entities],
                    'rewritten_query': semantic_rewritten_query,
                    'language': query_analysis.language,
                    'keywords': query_analysis.keywords,
                }

        except Exception as e:
            logger.warning(f"[SemanticSearch] Query analysis failed, continuing with original: {e}")

    # Character corruption check
    if original_user_query and query != original_user_query:
        validated_query, was_corrupted = _validate_query(query, original_user_query)
        if was_corrupted:
            logger.info(f"Query corruption fixed: '{query}' -> '{validated_query}'")
            query = validated_query
            search_query = validated_query
            query_was_corrected = True

    query_state = {
        "original_user_query": original_user_query,
        "exact_phrases": exact_phrases,
        "prioritize_web_sources": prioritize_web_sources,
        "query_was_corrected": query_was_corrected,
        "semantic_entities": semantic_entities,
        "semantic_rewritten_query": semantic_rewritten_query,
    }

    return query, search_query, query_state


def enhance_query_with_entities(
    search_query: str,
    semantic_entities: List,
) -> str:
    """
    Enhance search query with semantic entity terms.

    Args:
        search_query: Original search query
        semantic_entities: Detected semantic entities

    Returns:
        Enhanced query string
    """
    if not semantic_entities:
        return search_query

    entity_terms = []
    for entity in semantic_entities:
        if entity.type in ("command", "error_code", "product"):
            entity_terms.append(entity.value)

    if entity_terms:
        enhanced = f"{search_query} {' '.join(entity_terms)}"
        logger.debug(f"[SemanticSearch] Enhanced search query with entities: {entity_terms}")
        return enhanced

    return search_query


def merge_detected_with_semantic(
    detected_commands: List[str],
    detected_error_codes: List[str],
    semantic_entities: List,
) -> Tuple[List[str], List[str]]:
    """
    Merge detected items with semantic entity detections.

    Args:
        detected_commands: Commands detected from summary search
        detected_error_codes: Error codes detected from summary search
        semantic_entities: Entities from semantic analysis

    Returns:
        Tuple of (merged_commands, merged_error_codes)
    """
    commands = list(detected_commands)
    error_codes = list(detected_error_codes)

    if semantic_entities:
        for entity in semantic_entities:
            if entity.type == "command" and entity.value not in commands:
                commands.append(entity.value)
                logger.debug(f"[SemanticSearch] Added command from query analysis: {entity.value}")
            elif entity.type == "error_code" and entity.value not in error_codes:
                error_codes.append(entity.value)
                logger.debug(f"[SemanticSearch] Added error code from query analysis: {entity.value}")

    return commands, error_codes
