"""
Adaptive Search Tool
Structure-preserving PDF search using pgvector embeddings.

Supports:
- Text semantic search on adaptive chunks
- CLIP-based image semantic search (text-to-image)
- Page-based image association
"""
import logging
import re
import unicodedata
from typing import Dict, Any, Optional, List, Tuple
import json

from .base import BaseTool
from ..types import ToolResult, AgentContext

logger = logging.getLogger(__name__)


def _is_allowed_character(char: str) -> bool:
    """
    Check if a character is allowed (Japanese, Korean, English, numbers, punctuation).

    Allowed:
    - ASCII letters and numbers
    - Japanese Hiragana, Katakana, and common Kanji
    - Korean Hangul
    - Common punctuation and whitespace

    Rejected:
    - Simplified Chinese-only characters (not used in Japanese)
    - Other scripts
    """
    # Get Unicode category and name
    try:
        name = unicodedata.name(char, '')
        category = unicodedata.category(char)
    except ValueError:
        return False

    # Allow ASCII (letters, numbers, punctuation, whitespace)
    if ord(char) < 128:
        return True

    # Allow common punctuation and symbols
    if category in ('Po', 'Ps', 'Pe', 'Pi', 'Pf', 'Pd', 'Sm', 'Sc', 'Sk', 'So'):
        return True

    # Allow whitespace
    if category in ('Zs', 'Zl', 'Zp'):
        return True

    # Allow Japanese Hiragana (U+3040-U+309F)
    if 0x3040 <= ord(char) <= 0x309F:
        return True

    # Allow Japanese Katakana (U+30A0-U+30FF)
    if 0x30A0 <= ord(char) <= 0x30FF:
        return True

    # Allow Katakana Phonetic Extensions (U+31F0-U+31FF)
    if 0x31F0 <= ord(char) <= 0x31FF:
        return True

    # Allow Half-width Katakana (U+FF65-U+FF9F)
    if 0xFF65 <= ord(char) <= 0xFF9F:
        return True

    # Allow Full-width ASCII (U+FF01-U+FF5E)
    if 0xFF01 <= ord(char) <= 0xFF5E:
        return True

    # Allow Korean Hangul (U+AC00-U+D7AF)
    if 0xAC00 <= ord(char) <= 0xD7AF:
        return True

    # Allow Korean Jamo (U+1100-U+11FF, U+3130-U+318F)
    if 0x1100 <= ord(char) <= 0x11FF or 0x3130 <= ord(char) <= 0x318F:
        return True

    # Allow CJK Unified Ideographs (common to Japanese and Chinese)
    # Note: We allow these as they're used in Japanese Kanji
    if 0x4E00 <= ord(char) <= 0x9FFF:
        return True

    # Allow CJK Extension A (some used in Japanese)
    if 0x3400 <= ord(char) <= 0x4DBF:
        return True

    return False


def _validate_query(query: str, original_query: str) -> Tuple[str, bool]:
    """
    Validate query and return corrected version if corrupted.

    Detects LLM query corruption (e.g., Japanese → Chinese character substitution)
    by comparing character composition.

    Args:
        query: Query from LLM tool call
        original_query: Original user query from context

    Returns:
        Tuple of (validated_query, was_corrupted)
    """
    if not query or not original_query:
        return query or original_query, False

    # If queries are identical, no corruption
    if query == original_query:
        return query, False

    # Calculate allowed character ratio for both
    def calc_allowed_ratio(text: str) -> float:
        if not text:
            return 1.0
        allowed = sum(1 for c in text if _is_allowed_character(c))
        return allowed / len(text)

    query_ratio = calc_allowed_ratio(query)
    original_ratio = calc_allowed_ratio(original_query)

    # If query has significantly lower allowed ratio, it's likely corrupted
    # Original should have high ratio (user typed valid text)
    if query_ratio < 0.8 and original_ratio > 0.9:
        logger.warning(
            f"[QueryValidation] Query corruption detected! "
            f"LLM query ratio={query_ratio:.2f}, original ratio={original_ratio:.2f}"
        )
        logger.warning(f"[QueryValidation] LLM query: {query}")
        logger.warning(f"[QueryValidation] Original: {original_query}")
        return original_query, True

    # Check for character substitution (query is very different but same length)
    # This catches cases like 画面構成 → 图面機成
    if len(query) == len(original_query) and query != original_query:
        # Count how many characters are different
        diff_count = sum(1 for a, b in zip(query, original_query) if a != b)
        # If 30% or more characters differ, consider it corrupted
        # LLM sometimes substitutes similar-looking characters
        if diff_count >= max(1, len(query) * 0.3):
            print(
                f"[QueryValidation] Character substitution detected! "
                f"{diff_count}/{len(query)} chars differ", flush=True
            )
            print(f"[QueryValidation] LLM query: {query}", flush=True)
            print(f"[QueryValidation] Original: {original_query}", flush=True)
            return original_query, True

    # Even if lengths differ, check if query doesn't match original at all
    # This catches partial corruption
    if query != original_query and len(query) > 0:
        # Check if query shares any substring with original
        common_chars = sum(1 for c in query if c in original_query)
        similarity = common_chars / max(len(query), len(original_query))
        if similarity < 0.5:  # Less than 50% character overlap
            print(
                f"[QueryValidation] Low similarity detected! "
                f"similarity={similarity:.2f}", flush=True
            )
            print(f"[QueryValidation] LLM query: {query}", flush=True)
            print(f"[QueryValidation] Original: {original_query}", flush=True)
            return original_query, True

    # Check for length mismatch with similar semantic content
    # If LLM shortened/modified the query significantly
    if len(query) < len(original_query) * 0.5:
        logger.warning(
            f"[QueryValidation] Query truncation detected! "
            f"LLM len={len(query)}, original len={len(original_query)}"
        )
        return original_query, True

    return query, False


class AdaptiveSearchTool(BaseTool):
    """
    Adaptive Search Tool for structure-preserving PDF search.

    Uses PostgreSQL pgvector for semantic search on adaptive chunks
    that preserve document structure (sections, tables, images).
    """

    def __init__(self):
        super().__init__(
            name="adaptive_search",
            description=(
                "**PRIORITY TOOL - CALL THIS FIRST** for any document search query. "
                "Searches ALL uploaded PDF documents with structure-preserving embeddings. "
                "Returns results from technical manuals, reports, contracts with full context. "
                "Also finds semantically similar images using CLIP (text-to-image search). "
                "If this returns 0 results, then try vector_search as fallback."
            )
        )
        self._adaptive_service = None
        self._embedding_service = None
        self._clip_service = None

    def _get_default_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query - MUST be the EXACT user question without modification, translation, or summarization"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "default": 5
                },
                "pdf_id": {
                    "type": "string",
                    "description": "Optional PDF ID to filter results"
                },
                "section_filter": {
                    "type": "string",
                    "description": "Optional section path prefix to filter results (e.g., '1.2')"
                },
                "include_images": {
                    "type": "boolean",
                    "description": "Include CLIP-based image search (default: true)",
                    "default": True
                },
                "image_limit": {
                    "type": "integer",
                    "description": "Maximum number of images to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }

    async def _get_adaptive_service(self):
        """Lazy load adaptive service"""
        if self._adaptive_service is None:
            try:
                from ...core.deps import get_adaptive_embedding_service
                self._adaptive_service = await get_adaptive_embedding_service()
            except Exception as e:
                logger.error(f"Failed to get adaptive service: {e}")
        return self._adaptive_service

    async def _get_embedding_service(self):
        """Lazy load embedding service"""
        if self._embedding_service is None:
            try:
                from ...services.multimodal_embedding import TextEmbeddingService
                self._embedding_service = TextEmbeddingService()
            except Exception as e:
                logger.error(f"Failed to get embedding service: {e}")
        return self._embedding_service

    async def _get_clip_service(self):
        """Lazy load CLIP embedding service for text-to-image search"""
        if self._clip_service is None:
            try:
                from ...services.clip_embedding_service import get_clip_embedding_service
                self._clip_service = get_clip_embedding_service()
            except Exception as e:
                logger.error(f"Failed to get CLIP service: {e}")
        return self._clip_service

    async def execute(
        self,
        context: AgentContext,
        **kwargs
    ) -> ToolResult:
        """
        Execute adaptive search.

        Args:
            context: Agent execution context
            query: Search query
            top_k: Number of results (default: 5)
            pdf_id: Optional PDF ID filter
            section_filter: Optional section path filter

        Returns:
            ToolResult with search results
        """
        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", 5)
        pdf_id = kwargs.get("pdf_id")
        section_filter = kwargs.get("section_filter")
        include_images = kwargs.get("include_images", True)
        image_limit = kwargs.get("image_limit", 5)

        # Track original LLM query for UI display
        llm_query = query
        query_was_corrected = False

        # Validate query against original to detect LLM corruption
        # LLM sometimes corrupts Japanese/Korean text in tool calls
        original_query = context.metadata.get('original_query', '')
        if original_query and query != original_query:
            validated_query, was_corrupted = _validate_query(query, original_query)
            if was_corrupted:
                print(f"[AdaptiveSearch] Query corruption fixed: '{query}' → '{validated_query}'", flush=True)
                query = validated_query
                query_was_corrected = True

        print(f"[AdaptiveSearch] Called with query: {query[:50]}...", flush=True)
        logger.info(f"[AdaptiveSearch] Called with query: {query[:50]}...")

        if not query:
            return self.create_error_result("Query is required")

        try:
            # Get services
            adaptive_service = await self._get_adaptive_service()
            embedding_service = await self._get_embedding_service()

            if adaptive_service is None:
                return self.create_error_result(
                    "Adaptive search service is not available. "
                    "Use vector_search for general knowledge base queries."
                )

            if embedding_service is None:
                return self.create_error_result("Embedding service is not available")

            # Generate query embedding
            embeddings = await embedding_service.embed_texts([query])
            if not embeddings or not embeddings[0]:
                return self.create_error_result("Failed to generate query embedding")

            query_embedding = embeddings[0]

            # Search adaptive chunks
            results = await adaptive_service.search_chunks(
                query_embedding=query_embedding,
                limit=top_k,
                pdf_id=pdf_id,
                section_path_prefix=section_filter,
                min_similarity=0.3,
            )

            print(f"[AdaptiveSearch] Found {len(results) if results else 0} chunks", flush=True)
            logger.info(f"[AdaptiveSearch] Found {len(results) if results else 0} chunks")

            if not results:
                return self.create_success_result(
                    "No relevant content found in adaptive chunks. "
                    "Try vector_search for general knowledge base queries.",
                    metadata={"results_count": 0}
                )

            # Extract relevant page numbers from text chunk results
            # Images should only come from pages that matched the query
            relevant_pages = set()
            relevant_doc_id = None
            for result in results:
                page_start = result.get('page_start')
                page_end = result.get('page_end')
                if page_start:
                    relevant_pages.add(page_start)
                    # Also include adjacent pages (±1)
                    relevant_pages.add(page_start - 1)
                    relevant_pages.add(page_start + 1)
                if page_end and page_end != page_start:
                    relevant_pages.add(page_end)
                # Get document ID from results
                if not relevant_doc_id:
                    relevant_doc_id = result.get('pdf_id')

            print(f"[AdaptiveSearch] Relevant pages from chunks: {sorted(relevant_pages)}", flush=True)

            # Image search - only from pages that matched the query
            clip_images = []

            if include_images and relevant_pages:
                try:
                    from ...core.deps import get_postgres_pool
                    from ...infrastructure.postgres.image_repository import PostgresImageRepository

                    pool = await get_postgres_pool()
                    image_repo = PostgresImageRepository(pool)

                    # CLIP-based semantic image search (text-to-image only)
                    clip_service = await self._get_clip_service()
                    if clip_service:
                        try:
                            # Generate CLIP embedding for query text
                            clip_query_embedding = await clip_service.embed_text(query)

                            # Check if embedding is valid
                            if clip_query_embedding and sum(1 for v in clip_query_embedding if v != 0.0) > 0:
                                # Search similar images by CLIP embedding
                                # Use document ID from results if not specified
                                search_doc_id = pdf_id or relevant_doc_id
                                # Use 0.20 threshold (CLIP scores are lower for non-English text)
                                clip_results = await image_repo.search_by_clip_embedding(
                                    query_embedding=clip_query_embedding,
                                    document_id=search_doc_id,
                                    limit=image_limit * 3,
                                    min_similarity=0.20
                                )
                                print(f"[CLIP] Raw results: {len(clip_results)} images from doc={search_doc_id}", flush=True)
                                for r in clip_results[:5]:
                                    print(f"[CLIP]   raw: page={r.get('page_number')}, sim={r.get('similarity', 0):.3f}", flush=True)
                                # Filter by relevant pages and deduplicate
                                seen_pages = set()
                                for img in clip_results:
                                    if img.get('similarity', 0) < 0.20:
                                        continue
                                    page_num = img.get('page_number')
                                    # Only include images from pages that matched text chunks
                                    if page_num not in relevant_pages:
                                        print(f"[CLIP] Skipping image from page {page_num} (not in relevant pages)", flush=True)
                                        continue
                                    if page_num not in seen_pages:
                                        seen_pages.add(page_num)
                                        clip_images.append(img)
                                    if len(clip_images) >= image_limit:
                                        break
                                print(f"[CLIP] Found {len(clip_images)} images for query: {query[:30]}", flush=True)
                                for img in clip_images:
                                    print(f"[CLIP]   - {img.get('image_id')}: similarity={img.get('similarity', 0):.3f}, page={img.get('page_number')}", flush=True)
                                logger.info(f"[CLIP] Found {len(clip_images)} images for query: {query[:30]}")
                        except Exception as clip_err:
                            print(f"[CLIP] Error: {clip_err}", flush=True)
                            logger.debug(f"CLIP image search failed: {clip_err}")

                except Exception as img_err:
                    logger.debug(f"Could not fetch related images: {img_err}")

            # Format results with improved source display
            output_parts = [f"Found {len(results)} relevant chunk(s) from adaptive PDF search:\n"]

            for i, result in enumerate(results, 1):
                chunk_type = result.get('chunk_type', 'TEXT')
                similarity = result.get('similarity', 0)
                pdf_id_result = result.get('pdf_id', 'Unknown')
                document_name = result.get('document_name')
                page_start = result.get('page_start', '?')
                page_end = result.get('page_end', '?')
                section_title = result.get('section_title', '')
                section_path = result.get('section_path', '')
                content = result.get('content', '')

                # Format page range
                if page_start == page_end:
                    page_display = f"p.{page_start}"
                else:
                    page_display = f"p.{page_start}-{page_end}"

                # Format source display (document name + page)
                if document_name:
                    source_display = f"{document_name} ({page_display})"
                else:
                    source_display = f"{pdf_id_result} ({page_display})"

                chunk_info = (
                    f"\n{i}. [{chunk_type}] Similarity: {similarity:.2%}\n"
                    f"   📄 Source: {source_display}\n"
                )

                if section_title:
                    chunk_info += f"   📑 Section: {section_title}\n"
                if section_path:
                    chunk_info += f"   📍 Path: {section_path}\n"

                # Content preview (truncate if too long)
                if len(content) > 800:
                    content = content[:800] + "..."
                chunk_info += f"   Content:\n   {content}\n"

                # Relations info
                relations = result.get('relations', {})
                if isinstance(relations, str):
                    try:
                        relations = json.loads(relations)
                    except:
                        relations = {}

                related = []
                if relations.get('previous'):
                    related.append("has previous")
                if relations.get('next'):
                    related.append("has next")
                if relations.get('parent'):
                    related.append("has parent section")
                if relations.get('children'):
                    related.append(f"{len(relations['children'])} child chunks")

                if related:
                    chunk_info += f"   🔗 Related: {', '.join(related)}\n"

                output_parts.append(chunk_info)

            # Add CLIP-matched images at the end (after text results)
            if clip_images:
                output_parts.append(f"\n🔍 {len(clip_images)} query-matched image(s):")
                for img in clip_images[:image_limit]:
                    similarity = img.get('similarity', 0)
                    output_parts.append(
                        f"  - Image: {img['image_id']} (Page {img['page_number']}, "
                        f"Similarity: {similarity:.1%})"
                        f"\n    URL: /api/v1/documents/adaptive/images/{img['image_id']}/raw"
                    )

            # Build image URLs for metadata (CLIP-matched only)
            image_urls = [
                f"/api/v1/documents/adaptive/images/{img['image_id']}/raw"
                for img in clip_images[:image_limit]
            ]

            # Build metadata with query correction info for UI display
            # Extract unique sources from results (matching frontend AgentSource interface)
            sources = []
            seen_sources = set()
            for r in results:
                doc_name = r.get('document_name') or r.get('pdf_id', 'Unknown')
                page_start = r.get('page_start')
                page_end = r.get('page_end')
                similarity = r.get('similarity', 0)
                source_key = f"{doc_name}:{page_start}-{page_end}"
                if source_key not in seen_sources:
                    seen_sources.add(source_key)
                    # Format page display
                    if page_start == page_end:
                        page_display = f"p.{page_start}"
                    else:
                        page_display = f"p.{page_start}-{page_end}"
                    # Match frontend AgentSource interface: source, score, page_number
                    sources.append({
                        "source": f"{doc_name} ({page_display})",  # 문서명 + 페이지
                        "score": similarity,  # similarity -> score
                        "page_number": page_start,  # 시작 페이지
                        "content": r.get('content', '')[:200],  # 내용 미리보기
                        "doc_id": r.get('pdf_id')
                    })

            result_metadata = {
                "results_count": len(results),
                "query": query,
                "pdf_id": pdf_id,
                "section_filter": section_filter,
                "sources": sources,  # 출처 정보 추가
                "image_count": len(clip_images),
                "image_urls": image_urls,
                "images": [
                    {
                        "image_id": img.get("image_id"),
                        "document_id": img.get("document_id"),
                        "page_number": img.get("page_number"),
                        "similarity": img.get("similarity"),
                        "url": f"/api/v1/documents/adaptive/images/{img['image_id']}/raw"
                    }
                    for img in clip_images[:image_limit]
                ],
            }

            # Add query correction info if query was fixed
            if query_was_corrected:
                result_metadata["query_corrected"] = True
                result_metadata["original_llm_query"] = llm_query
                result_metadata["corrected_query"] = query

            return self.create_success_result(
                "\n".join(output_parts),
                metadata=result_metadata
            )

        except Exception as e:
            logger.error(f"Adaptive search error: {e}", exc_info=True)
            return self.create_error_result(f"Adaptive search error: {str(e)}")
