"""
Keyword Extraction Service

LLM-based multilingual keyword extraction service for CJK (Chinese/Japanese/Korean) text.
Provides accurate tokenization where regex-based methods fail due to lack of word boundaries.

Features:
- LLM-based extraction for CJK queries
- Regex fallback for non-CJK queries
- LRU cache with TTL for performance
- Async API with timeout handling
"""

import re
import json
import asyncio
import hashlib
import logging
import os
from typing import List, Tuple, Optional, Dict
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

import aiohttp

logger = logging.getLogger(__name__)


class ExtractionMethod(Enum):
    """Keyword extraction method"""
    LLM = "llm"
    REGEX = "regex"
    CACHE = "cache"


@dataclass
class KeywordExtractionResult:
    """Result of keyword extraction"""
    keywords: List[str]
    method: ExtractionMethod
    language: str
    extraction_time_ms: float
    cache_hit: bool
    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int] = None


# LLM prompt for keyword extraction
KEYWORD_EXTRACTION_PROMPT = """You are a keyword extraction expert for OpenFrame technical documentation.

Extract the main technical keywords from this query. Follow these rules strictly:

1. COMPOUND WORDS: Keep technical compound words together
   - "マッピング・サポート" → "マッピングサポート" (one keyword, remove middle dot)
   - "OSCサーバー" → "OSC", "サーバー" (separate: English + Japanese)
   - "起動画面" → "起動画面" (keep together)

2. PARTICLES: Split on Japanese particles (の、を、が、は、に、で、と)
   - "起動画面の設定" → "起動画面", "設定"
   - "サーバーについて" → "サーバー"

3. PRESERVE: Keep these intact
   - Error codes with minus: -5212, -21001 (KEEP THE MINUS SIGN!)
   - Commands: tjesmgr, hidbmgr, oscboot, tacfmgr, ndbmgr
   - Acronyms: OSC, BMS, TJES, VSAM, TACF, HIDB

4. REMOVE: Do not include
   - Particles: の、を、が、は、に、で、と、も
   - Question words: について、とは、ですか、ください、教えて、説明
   - Common verbs: する、ある、いる、できる、なる

Query: {query}

Output ONLY valid JSON (no explanation, no markdown):
{{"keywords": ["keyword1", "keyword2", ...]}}"""


class KeywordExtractionService:
    """
    LLM-based multilingual keyword extraction service.

    For CJK (Chinese/Japanese/Korean) text, accurate tokenization requires
    understanding of language semantics. This service uses LLM for CJK queries
    and falls back to regex for non-CJK queries.

    Features:
    - LRU cache with TTL for repeated queries
    - Timeout handling with regex fallback
    - Language detection (ja, ko, zh, en)
    """

    # Cache settings
    CACHE_MAX_SIZE = 1000
    CACHE_TTL_SECONDS = 3600  # 1 hour

    # LLM settings
    LLM_TIMEOUT_SECONDS = 3.0
    LLM_MAX_TOKENS = 200

    def __init__(
        self,
        llm_url: Optional[str] = None,
        llm_model: Optional[str] = None
    ):
        self._llm_url = llm_url or os.getenv(
            "LLM_API_URL",
            "http://localhost:12800/v1/chat/completions"
        )
        self._llm_model = llm_model or os.getenv(
            "LLM_MODEL",
            "Qwen/Qwen2.5-7B-Instruct"
        )
        self._cache: Dict[str, Tuple[List[str], datetime]] = {}
        logger.info(f"KeywordExtractionService initialized: url={self._llm_url}, model={self._llm_model}")

    async def extract_keywords(
        self,
        query: str,
        force_llm: bool = False
    ) -> KeywordExtractionResult:
        """
        Extract keywords from a query.

        Args:
            query: User query string
            force_llm: If True, skip cache and always call LLM

        Returns:
            KeywordExtractionResult with keywords and metadata
        """
        start_time = datetime.now()
        cache_key = hashlib.md5(query.encode()).hexdigest()

        # 1. Check cache
        if not force_llm and cache_key in self._cache:
            keywords, cached_at = self._cache[cache_key]
            if datetime.now() - cached_at < timedelta(seconds=self.CACHE_TTL_SECONDS):
                elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
                logger.debug(f"[Keywords Cache Hit] '{query[:30]}...' -> {keywords}")
                return KeywordExtractionResult(
                    keywords=keywords,
                    method=ExtractionMethod.CACHE,
                    language=self._detect_language(query),
                    extraction_time_ms=elapsed_ms,
                    cache_hit=True
                )

        # 2. Detect language
        language = self._detect_language(query)
        has_cjk = language in ("ja", "ko", "zh")

        # 3. Choose extraction method
        llm_model = None
        if has_cjk:
            keywords, method, llm_model = await self._extract_llm(query)
            if not keywords:  # LLM failed, fallback to regex
                logger.debug(f"[Keywords] LLM failed, using regex fallback for: {query[:30]}")
                keywords = self._extract_regex(query, language)
                method = ExtractionMethod.REGEX
                llm_model = None
        else:
            keywords = self._extract_regex(query, language)
            method = ExtractionMethod.REGEX

        # 4. Update cache
        if keywords:
            self._cache[cache_key] = (keywords, datetime.now())
            self._cleanup_cache()

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        logger.debug(f"[Keywords {method.value}] '{query[:30]}...' -> {keywords} ({elapsed_ms:.1f}ms)")

        return KeywordExtractionResult(
            keywords=keywords,
            method=method,
            language=language,
            extraction_time_ms=elapsed_ms,
            cache_hit=False,
            llm_model=llm_model if method == ExtractionMethod.LLM else None
        )

    def _detect_language(self, text: str) -> str:
        """Detect primary language of text"""
        # Check for Japanese (hiragana/katakana)
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
            return "ja"
        # Check for Korean (hangul)
        if re.search(r'[\uac00-\ud7af]', text):
            return "ko"
        # Check for Chinese (CJK ideographs only, no kana)
        if re.search(r'[\u4e00-\u9fff]', text):
            return "zh"
        return "en"

    async def _extract_llm(self, query: str) -> Tuple[List[str], ExtractionMethod, Optional[str]]:
        """Extract keywords using LLM"""
        prompt = KEYWORD_EXTRACTION_PROMPT.format(query=query)

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self._llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": self.LLM_MAX_TOKENS,
                    "temperature": 0.1,
                }

                async with session.post(
                    self._llm_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.LLM_TIMEOUT_SECONDS)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                        # Parse JSON from response
                        json_match = re.search(r'\{[^{}]*\}', content)
                        if json_match:
                            try:
                                result = json.loads(json_match.group())
                                keywords = result.get("keywords", [])
                                if keywords and isinstance(keywords, list):
                                    # Clean and validate keywords
                                    cleaned = [str(kw).strip() for kw in keywords if kw and str(kw).strip()]
                                    if cleaned:
                                        return cleaned, ExtractionMethod.LLM, self._llm_model
                            except json.JSONDecodeError:
                                logger.warning(f"[Keywords LLM] JSON parse error: {content[:100]}")
                    else:
                        logger.warning(f"[Keywords LLM] HTTP {response.status}: {await response.text()[:200]}")

        except asyncio.TimeoutError:
            logger.warning(f"[Keywords LLM] Timeout ({self.LLM_TIMEOUT_SECONDS}s) for: {query[:50]}")
        except aiohttp.ClientConnectorError as e:
            logger.warning(f"[Keywords LLM] Connection error: {e}")
        except Exception as e:
            logger.warning(f"[Keywords LLM] Error: {type(e).__name__}: {e}")

        return [], ExtractionMethod.REGEX, None

    def _extract_regex(self, query: str, language: str = "en") -> List[str]:
        """Extract keywords using regex (fallback)"""
        keywords = []

        # 1. Extract error codes first (preserve minus sign)
        error_codes = re.findall(r'-\d{4,5}', query)
        keywords.extend(error_codes)

        # 2. Extract alphanumeric tokens (commands, acronyms)
        alpha_tokens = re.findall(r'[a-zA-Z][a-zA-Z0-9_]*', query)
        for token in alpha_tokens:
            if len(token) >= 2 and token.lower() not in self._get_stopwords():
                keywords.append(token)

        # 3. Extract CJK tokens
        if language == "ja":
            # Japanese: split on particles, keep compound words
            # Remove particles first
            cleaned = re.sub(r'[のをがはにでともやへ]', ' ', query)
            # Remove question patterns
            cleaned = re.sub(r'について|とは|ですか|ください|教えて|説明して', ' ', cleaned)
            # Extract remaining CJK sequences
            cjk_tokens = re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+', cleaned)
            for token in cjk_tokens:
                if len(token) >= 2:
                    keywords.append(token)
        elif language == "ko":
            # Korean: extract noun-like tokens
            # Remove particles
            cleaned = re.sub(r'[이가은는을를의에서로으로와과도만까지부터]', ' ', query)
            # Remove question patterns
            cleaned = re.sub(r'대해|대한|관한|어떻게|무엇|입니다|합니다', ' ', cleaned)
            ko_tokens = re.findall(r'[\uac00-\ud7af]+', cleaned)
            for token in ko_tokens:
                if len(token) >= 2 and token not in self._get_stopwords():
                    keywords.append(token)
        elif language == "zh":
            # Chinese: extract character sequences
            zh_tokens = re.findall(r'[\u4e00-\u9fff]+', query)
            for token in zh_tokens:
                if len(token) >= 2:
                    keywords.append(token)

        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower() if kw[0].isascii() else kw
            if kw_lower not in seen:
                seen.add(kw_lower)
                unique_keywords.append(kw)

        return unique_keywords[:10]

    def _get_stopwords(self) -> set:
        """Get multilingual stopwords"""
        return {
            # Japanese particles and common words
            'の', 'に', 'は', 'を', 'た', 'が', 'で', 'て', 'と', 'し', 'も',
            'する', 'から', 'な', 'こと', 'など', 'ない', 'この', 'その',
            'また', 'もの', 'という', 'より', 'ため', 'について', 'とは',
            'ください', 'できる', 'ある', 'いる', 'なる', 'れる', 'られる',
            'です', 'ます', 'した', 'される', 'させる', 'ようになる',
            # Korean particles
            '이', '가', '은', '는', '을', '를', '의', '에', '에서', '로',
            '으로', '와', '과', '도', '만', '까지', '부터', '대해', '대한',
            '있다', '없다', '하다', '되다', '이다',
            # English stopwords
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'about', 'what',
            'how', 'why', 'when', 'where', 'which', 'who', 'whom', 'this',
            'that', 'these', 'those', 'it', 'its', 'and', 'or', 'but', 'if',
        }

    def _cleanup_cache(self):
        """Clean up old cache entries"""
        if len(self._cache) > self.CACHE_MAX_SIZE:
            # Remove oldest 50% of entries
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1][1])
            remove_count = len(self._cache) // 2
            for key, _ in sorted_items[:remove_count]:
                del self._cache[key]
            logger.debug(f"[Keywords Cache] Cleaned up {remove_count} entries")

    def clear_cache(self):
        """Clear all cache entries"""
        self._cache.clear()
        logger.info("[Keywords Cache] Cleared all entries")


# Singleton instance
_service: Optional[KeywordExtractionService] = None


def get_keyword_extraction_service() -> KeywordExtractionService:
    """Get or create singleton KeywordExtractionService instance"""
    global _service
    if _service is None:
        _service = KeywordExtractionService()
    return _service


async def extract_keywords(query: str) -> List[str]:
    """
    Convenience function to extract keywords from a query.

    Args:
        query: User query string

    Returns:
        List of extracted keywords
    """
    service = get_keyword_extraction_service()
    result = await service.extract_keywords(query)
    return result.keywords
