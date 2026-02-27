"""
Web Document Search Service

사전 크롤링한 docs.tmaxsoft.com 페이지 인덱스를 메모리에 로드하고,
쿼리에 대해 keyword + IDF 매칭을 수행합니다 (<10ms).

StructuredKnowledgeStore와 동일한 토큰화/IDF 알고리즘을 사용하되,
점수를 0-1로 정규화하여 threshold 기반 판단에 활용합니다.
"""
import logging
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WebDocSearchResult:
    """Web document 검색 결과"""
    url: str
    title: str
    component: str
    product_id: str
    language: str
    score: float  # Raw IDF-weighted score
    normalized_score: float  # 0.0-1.0 정규화
    headings: List[str]
    snippet: str


# StructuredKnowledgeStore와 동일한 불용어
_STOPWORDS = frozenset([
    "の", "は", "が", "を", "に", "で", "と", "も", "や", "か",
    "へ", "から", "まで", "より", "ね", "よ", "わ", "な", "け",
    "って", "ので", "のに", "けど", "だけ", "しか", "ばかり",
    "について", "してください", "ください", "とは", "ことが",
    "ている", "された", "される", "している", "できる",
    "ものです", "ことです", "あります", "ありません",
    "ですか", "ますか", "ません", "でしょう",
    "ました", "しました", "なります", "おける",
    "どのよう", "どうすれ", "なぜ", "いつ",
    "教えて", "説明して", "知りたい",
    "えてください", "してください", "してほしい",
    "教えてください", "説明してください", "知りたいです",
    "the", "a", "an", "of", "in", "on", "at", "to", "for",
    "is", "are", "was", "were", "be", "and", "or", "not",
    "it", "this", "that", "with", "from", "by", "as",
    "about", "what", "how", "do", "does",
    "tell", "me", "explain", "please", "describe",
])

# StructuredKnowledgeStore와 동일한 토큰 패턴
_TOKEN_RE = re.compile(
    r'[a-z0-9][a-z0-9_\-]*[a-z0-9]|[a-z0-9]'
    r'|[\u30a0-\u30ff]{2,}'
    r'|[\u4e00-\u9fff]+'
    r'|[\uac00-\ud7af]{2,}'
    r'|[\u3040-\u309f]{2,}',
)

# 유사도 threshold: 이 이상이면 web doc으로 응답
WEB_DOC_THRESHOLD = 0.9


def _tokenize(query: str) -> List[str]:
    """쿼리를 의미 토큰으로 분리 (StructuredKnowledgeStore와 동일)"""
    raw_tokens = _TOKEN_RE.findall(query.lower())
    tokens = []
    for t in raw_tokens:
        if t in _STOPWORDS:
            continue
        if len(t) == 1 and t.isascii():
            continue
        # 단일 한자(kanji)도 검색 키워드로 무의미
        if len(t) == 1 and '\u4e00' <= t <= '\u9fff':
            continue
        tokens.append(t)
    return tokens


class WebDocSearchService:
    """
    인메모리 keyword + IDF 검색

    점수 정규화:
      normalized = raw_score / max_possible
      max_possible = sum(idf[t] * title_weight) (모든 토큰이 title에 매칭)
      title_weight = 3.0, content_weight = 1.0
      coverage_factor = 0.5 + 0.5 * (matched_tokens / total_tokens)
    """

    TITLE_WEIGHT = 3.0
    CONTENT_WEIGHT = 1.0

    def __init__(self):
        self._pages: List[dict] = []
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        from .web_doc_crawler_service import get_web_doc_crawler_service
        crawler = get_web_doc_crawler_service()
        index = crawler.index
        if not index:
            index = crawler.load_index()
        if index and index.pages:
            self._pages = []
            for p in index.pages:
                # 검색용 텍스트 사전 결합 (소문자)
                searchable = (
                    p.title + " " + " ".join(p.headings) + " " + p.snippet
                ).lower()
                # 키워드 집합 (빠른 토큰 매칭용)
                kw_set = frozenset(p.keywords) if p.keywords else frozenset()
                self._pages.append({
                    "url": p.url,
                    "title": p.title,
                    "title_lower": p.title.lower(),
                    "headings": p.headings,
                    "snippet": p.snippet,
                    "component": p.component,
                    "product_id": p.product_id,
                    "language": p.language,
                    "searchable": searchable,
                    "kw_set": kw_set,
                })
            logger.info(f"WebDocSearchService loaded: {len(self._pages)} pages")
        self._loaded = True

    def reload(self):
        """인덱스 다시 로드 (크롤 후 호출)"""
        self._loaded = False
        self._pages = []
        self._ensure_loaded()

    def search(
        self,
        query: str,
        language: str = "ja",
        product_ids: Optional[List[str]] = None,
        top_k: int = 3,
    ) -> List[WebDocSearchResult]:
        """
        웹 문서 인덱스 검색.

        Returns:
            normalized_score 내림차순 정렬된 결과 리스트
        """
        self._ensure_loaded()

        if not self._pages:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        # 필터: 언어 + 제품
        candidates = self._pages
        if product_ids:
            candidates = [
                p for p in candidates
                if p["product_id"] in product_ids or not p["product_id"]
            ]
        # 요청 언어 우선, 없으면 전체
        lang_filtered = [p for p in candidates if p["language"] == language]
        if lang_filtered:
            candidates = lang_filtered

        if not candidates:
            return []

        # IDF 계산
        total = len(candidates)
        df_counts: Dict[str, int] = {t: 0 for t in tokens}
        for page in candidates:
            searchable = page["searchable"]
            for token in tokens:
                if token in searchable:
                    df_counts[token] += 1

        idf: Dict[str, float] = {}
        for token in tokens:
            idf[token] = math.log((total + 1) / (df_counts[token] + 1)) + 1.0

        # max_possible: 모든 토큰이 title에서 매칭된 경우
        max_possible = sum(idf[t] * self.TITLE_WEIGHT for t in tokens)
        if max_possible <= 0:
            return []

        # 스코어링
        scored = []
        for page in candidates:
            title_lower = page["title_lower"]
            searchable = page["searchable"]
            score = 0.0
            matched = 0

            for token in tokens:
                if token in title_lower:
                    score += self.TITLE_WEIGHT * idf[token]
                    matched += 1
                elif token in searchable:
                    score += self.CONTENT_WEIGHT * idf[token]
                    matched += 1

            if score <= 0:
                continue

            # Coverage factor (단일 토큰이면 1.0)
            if len(tokens) > 1:
                coverage = matched / len(tokens)
                score *= (0.5 + 0.5 * coverage)

            normalized = min(score / max_possible, 1.0)
            scored.append((normalized, score, page))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for norm_score, raw_score, page in scored[:top_k]:
            results.append(WebDocSearchResult(
                url=page["url"],
                title=page["title"],
                component=page["component"],
                product_id=page["product_id"],
                language=page["language"],
                score=raw_score,
                normalized_score=round(norm_score, 4),
                headings=page["headings"][:5],
                snippet=page.get("snippet", ""),
            ))

        return results


# Singleton
_instance: Optional[WebDocSearchService] = None


def get_web_doc_search_service() -> WebDocSearchService:
    global _instance
    if _instance is None:
        _instance = WebDocSearchService()
    return _instance
