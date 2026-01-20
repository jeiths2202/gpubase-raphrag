"""
LLM-based Query Expansion Service

Dynamically expands queries using LLM to generate equivalent terms in target languages.
This replaces manual term mappings with AI-powered translation and expansion.

Key features:
- Automatic query language detection
- Cross-language expansion (Korean → Japanese, English → Japanese)
- Technical term preservation
- Caching for performance
- Uses NVIDIA NIM (OpenAI-compatible API)
"""
import asyncio
import os
import re
import logging
import hashlib
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)


@dataclass
class LLMExpandedQuery:
    """Result of LLM-based query expansion"""
    original: str
    expanded_terms: List[str]
    japanese_query: Optional[str]
    source_language: str
    target_language: str
    cached: bool = False

    def get_expanded_query(self) -> str:
        """Get query optimized for Japanese document retrieval"""
        parts = [self.original]

        # Add Japanese query if available
        if self.japanese_query and self.japanese_query != self.original:
            parts.append(self.japanese_query)

        # Add expanded terms (limit to avoid query bloat)
        if self.expanded_terms:
            parts.extend(self.expanded_terms[:5])

        return " ".join(parts)


class LLMQueryExpansionService:
    """
    LLM-powered query expansion for cross-language RAG retrieval.

    Uses NVIDIA NIM (OpenAI-compatible API) to dynamically translate and expand queries,
    eliminating the need for manual term mappings.
    """

    # Simple in-memory cache with TTL
    _cache: Dict[str, Tuple[LLMExpandedQuery, float]] = {}
    _cache_ttl: int = 3600  # 1 hour
    _cache_max_size: int = 1000

    def __init__(
        self,
        nim_api_url: str = None,
        nim_model: str = None,
        target_language: str = "ja",
        timeout: int = 15
    ):
        """
        Initialize LLM Query Expansion Service.

        Args:
            nim_api_url: NIM API URL (OpenAI-compatible chat completions endpoint)
            nim_model: Model to use for expansion
            target_language: Target language for documents (ja, en, ko)
            timeout: Request timeout in seconds
        """
        # Default NIM settings from environment or fallback
        self.nim_api_url = nim_api_url or os.getenv(
            "LLM_API_URL",
            "http://localhost:12800/v1/chat/completions"
        )
        self.nim_model = nim_model or os.getenv(
            "LLM_MODEL",
            "nvidia/nvidia-nemotron-nano-9b-v2"
        )
        self.target_language = target_language
        self.timeout = timeout

        logger.info(f"[LLMQueryExpansion] Initialized with NIM model={self.nim_model}, target={target_language}")

    def _detect_language(self, text: str) -> str:
        """Detect primary language of text"""
        # Count character types
        ja_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text))  # Hiragana + Katakana
        ko_chars = len(re.findall(r'[\uac00-\ud7af]', text))  # Hangul
        cjk_chars = len(re.findall(r'[\u4e00-\u9fff]', text))  # CJK (shared)

        total_cjk = ja_chars + ko_chars + cjk_chars

        if total_cjk == 0:
            return "en"

        if ko_chars > ja_chars:
            return "ko"
        elif ja_chars > 0:
            return "ja"
        else:
            # CJK only - could be Chinese or Japanese Kanji
            return "ja"  # Assume Japanese for this system

    def _get_cache_key(self, query: str) -> str:
        """Generate cache key for query"""
        return hashlib.md5(f"{query}:{self.target_language}".encode()).hexdigest()

    def _get_from_cache(self, query: str) -> Optional[LLMExpandedQuery]:
        """Get cached result if available and not expired"""
        key = self._get_cache_key(query)
        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                result.cached = True
                return result
            else:
                del self._cache[key]
        return None

    def _save_to_cache(self, query: str, result: LLMExpandedQuery):
        """Save result to cache with TTL"""
        # Evict old entries if cache is full
        if len(self._cache) >= self._cache_max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

        key = self._get_cache_key(query)
        self._cache[key] = (result, time.time())

    async def expand(self, query: str) -> LLMExpandedQuery:
        """
        Expand query using LLM for cross-language retrieval.

        Args:
            query: Original user query

        Returns:
            LLMExpandedQuery with original and expanded terms
        """
        # Check cache first
        cached = self._get_from_cache(query)
        if cached:
            logger.debug(f"[LLMQueryExpansion] Cache hit for: {query[:50]}...")
            return cached

        source_lang = self._detect_language(query)

        # If already in target language, minimal expansion needed
        if source_lang == self.target_language:
            result = LLMExpandedQuery(
                original=query,
                expanded_terms=[],
                japanese_query=query if self.target_language == "ja" else None,
                source_language=source_lang,
                target_language=self.target_language
            )
            self._save_to_cache(query, result)
            return result

        # Use LLM to expand query
        try:
            expanded_terms, japanese_query = await self._llm_expand(query, source_lang)

            result = LLMExpandedQuery(
                original=query,
                expanded_terms=expanded_terms,
                japanese_query=japanese_query,
                source_language=source_lang,
                target_language=self.target_language
            )

            self._save_to_cache(query, result)
            logger.info(f"[LLMQueryExpansion] Expanded '{query[:30]}...' -> {len(expanded_terms)} terms, ja='{japanese_query[:30] if japanese_query else 'None'}...'")

            return result

        except Exception as e:
            logger.warning(f"[LLMQueryExpansion] LLM expansion failed: {e}, using fallback")
            # Fallback: return original query without expansion
            return LLMExpandedQuery(
                original=query,
                expanded_terms=[],
                japanese_query=None,
                source_language=source_lang,
                target_language=self.target_language
            )

    async def _llm_expand(self, query: str, source_lang: str) -> Tuple[List[str], Optional[str]]:
        """
        Use NIM LLM to generate expanded terms and translation.

        Args:
            query: Original query
            source_lang: Detected source language

        Returns:
            Tuple of (expanded_terms, japanese_translation)
        """
        import aiohttp

        # Build prompt based on source language
        if source_lang == "ko":
            prompt = f"""You are a technical translator for enterprise software documentation.
Convert the following Korean query to Japanese for document search.

Korean query: {query}

Output ONLY a JSON object with this format:
{{"japanese": "日本語翻訳", "keywords": ["キーワード1", "keyword2", "キーワード3"]}}

Requirements:
1. "japanese" must be the complete Japanese translation of the query
2. "keywords" should include:
   - Key Japanese terms from the translation
   - Technical acronyms unchanged (OSC, OSI, MFS, BMS, IMS, CICS, etc.)
   - Related Japanese technical terms

Output JSON only, no explanation:"""
        else:  # English
            prompt = f"""You are a technical translator for enterprise software documentation.
Convert the following English query to Japanese for document search.

English query: {query}

Output ONLY a JSON object with this format:
{{"japanese": "日本語翻訳", "keywords": ["キーワード1", "keyword2", "キーワード3"]}}

Requirements:
1. "japanese" must be the complete Japanese translation of the query
2. "keywords" should include:
   - Key Japanese terms from the translation
   - Technical acronyms unchanged (OSC, OSI, MFS, BMS, IMS, CICS, etc.)
   - Related Japanese technical terms

Output JSON only, no explanation:"""

        # OpenAI-compatible payload for NIM
        payload = {
            "model": self.nim_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a technical translator specializing in mainframe, OpenFrame, and enterprise software terminology. You translate between Korean, English, and Japanese. Always output valid JSON only."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 256,
            "stream": False
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.nim_api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"NIM API error: {response.status} - {error_text[:200]}")

                    result = await response.json()

                    # OpenAI-compatible response format
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                    # Parse JSON response
                    return self._parse_llm_response(content)

        except asyncio.TimeoutError:
            logger.warning(f"[LLMQueryExpansion] Timeout after {self.timeout}s")
            raise
        except Exception as e:
            logger.warning(f"[LLMQueryExpansion] API call failed: {e}")
            raise

    def _parse_llm_response(self, content: str) -> Tuple[List[str], Optional[str]]:
        """Parse LLM response to extract Japanese query and keywords"""
        import json

        # Try to extract JSON from response
        try:
            # Clean up response - find JSON in the content
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                japanese = data.get("japanese", "")
                keywords = data.get("keywords", [])

                # Ensure keywords is a list of strings
                if isinstance(keywords, list):
                    keywords = [str(k) for k in keywords if k]
                else:
                    keywords = []

                return keywords, japanese if japanese else None
        except json.JSONDecodeError:
            pass

        # Fallback: try to extract any Japanese text
        ja_text = re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+', content)
        return ja_text[:5], ja_text[0] if ja_text else None

    def expand_sync(self, query: str) -> LLMExpandedQuery:
        """Synchronous wrapper for expand()"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, create a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.expand(query))
                    return future.result(timeout=self.timeout + 5)
            else:
                return loop.run_until_complete(self.expand(query))
        except RuntimeError:
            return asyncio.run(self.expand(query))


# Singleton instance
_service: Optional[LLMQueryExpansionService] = None


def get_llm_query_expansion_service() -> LLMQueryExpansionService:
    """Get or create LLMQueryExpansionService singleton"""
    global _service
    if _service is None:
        _service = LLMQueryExpansionService(
            nim_api_url=os.getenv("LLM_API_URL", "http://localhost:12800/v1/chat/completions"),
            nim_model=os.getenv("LLM_MODEL", "nvidia/nvidia-nemotron-nano-9b-v2"),
            target_language="ja"
        )
    return _service
