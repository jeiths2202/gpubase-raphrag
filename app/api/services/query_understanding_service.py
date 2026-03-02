"""
Query Understanding Service for Semantic Search

LLM 기반 쿼리 분석 서비스
- Intent 분류
- Entity 추출
- Query Rewriting
- 캐싱 지원
"""

import os
import json
import time
import hashlib
import logging
import re
from typing import Optional, Dict, Any, List
from functools import lru_cache

from app.api.models.query_analysis import (
    QueryAnalysis,
    QueryIntent,
    ExtractedEntity,
)

logger = logging.getLogger(__name__)


# Known entities for fallback extraction
KNOWN_PRODUCTS = [
    "TJES", "TACF", "OSC", "OFASM", "HIDB", "OpenFrame", "OFMiner",
    "OFManager", "JEUS", "Tibero", "ProObject", "OFCOBOL", "OFPLI",
    "PROSORT", "PROTRIEVE", "AIM", "BASE", "NDB", "TSAM", "VSAM"
]

KNOWN_COMMANDS = [
    "tjesmgr", "tacfmgr", "oscmgr", "ofasmif", "hidbmgr", "ndbmgr",
    "volmgr", "catmgr", "idcams", "dfsort", "iebgener", "iebcopy",
    "dsmigin", "dsmigout", "tmboot", "tmdown", "ofboot", "ofdown",
    "jesinit", "jesdown", "osmgr", "osimgr", "cobrun", "plirun"
]

# Intent detection patterns
INTENT_PATTERNS = {
    QueryIntent.EXPLANATION: [
        r"について説明", r"説明して", r"説明してください",
        r"가\s*뭐", r"이\s*뭐", r"뭐야", r"뭔가요", r"무엇인가요",
        r"explain", r"what is", r"tell me about"
    ],
    QueryIntent.DEFINITION: [
        r"とは[？?]?$", r"とは何", r"의\s*정의", r"정의가",
        r"define", r"definition of"
    ],
    QueryIntent.USAGE: [
        r"使い方", r"使用方法", r"사용법", r"사용 방법", r"어떻게 사용",
        r"how to use", r"usage"
    ],
    QueryIntent.ERROR_RESOLUTION: [
        r"エラー", r"에러", r"오류", r"error", r"解決", r"해결",
        r"ABEND", r"S0C[0-9]", r"-\d{4,5}"
    ],
    QueryIntent.COMPARISON: [
        r"違い", r"比較", r"차이", r"비교", r"vs", r"versus",
        r"difference", r"compare"
    ],
    QueryIntent.PROCEDURE: [
        r"手順", r"절차", r"순서", r"steps", r"procedure", r"how to"
    ],
    QueryIntent.CONFIGURATION: [
        r"設定", r"설정", r"構成", r"구성", r"config", r"configuration"
    ],
}


class QueryUnderstandingService:
    """LLM 기반 쿼리 이해 서비스"""

    def __init__(
        self,
        llm_client=None,
        use_cache: bool = True,
        cache_ttl: int = 3600,
    ):
        self.llm_client = llm_client
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}  # {hash: (result, timestamp)}

        # LLM 설정
        self.llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:12803/v1")
        self.llm_model = os.getenv("LLM_MODEL", "openbmb/MiniCPM-V-2_6")

        # 프롬프트 로드
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """프롬프트 템플릿 로드"""
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            "..", "prompts", "query_understanding.txt"
        )
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()

        # 기본 프롬프트
        return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """기본 프롬프트 템플릿"""
        return """You are a query analyzer for OpenFrame technical documentation search.
Analyze the following query and extract structured information.

Query: {query}

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "intent": "<one of: explanation, definition, usage, error, comparison, procedure, configuration, search>",
  "entities": [
    {{"type": "<command|error_code|product|config|term>", "value": "<extracted value>", "confidence": <0.0-1.0>}}
  ],
  "language": "<ja|ko|en>",
  "rewritten_query": "<search-optimized English query with key terms, remove filler phrases>",
  "keywords": ["<keyword1>", "<keyword2>"]
}}

Known Products: TJES, TACF, OSC, OFASM, HIDB, OpenFrame, OFMiner, OFManager
Known Commands: tjesmgr, tacfmgr, oscmgr, ofasmif, hidbmgr, ndbmgr, volmgr, catmgr, idcams

Rules:
1. Remove Japanese/Korean filler phrases (について説明してください, 가 뭐야, etc.) in rewritten_query
2. Include both original language keywords and English equivalents
3. For commands, always include the product name (e.g., ofasmif → OFASM)
4. Error codes: -5212, ABEND S0C7, etc.
"""

    async def analyze(self, query: str) -> QueryAnalysis:
        """쿼리 분석 메인 함수"""
        start_time = time.time()

        # 1. 캐시 확인
        if self.use_cache:
            cached = self._get_from_cache(query)
            if cached:
                cached.analysis_source = "cache"
                return cached

        # 2. LLM 분석 시도
        try:
            if self.llm_client:
                analysis = await self._llm_analyze(query)
            else:
                # LLM 없으면 Fallback
                analysis = self._fallback_analyze(query)
        except Exception as e:
            logger.warning(f"LLM analysis failed, using fallback: {e}")
            analysis = self._fallback_analyze(query)

        # 3. 처리 시간 기록
        analysis.processing_time_ms = (time.time() - start_time) * 1000

        # 4. 캐시 저장
        if self.use_cache:
            self._save_to_cache(query, analysis)

        return analysis

    def analyze_sync(self, query: str) -> QueryAnalysis:
        """동기 버전 쿼리 분석 (Fallback만 사용)"""
        start_time = time.time()

        # 캐시 확인
        if self.use_cache:
            cached = self._get_from_cache(query)
            if cached:
                cached.analysis_source = "cache"
                return cached

        # Fallback 분석
        analysis = self._fallback_analyze(query)
        analysis.processing_time_ms = (time.time() - start_time) * 1000

        # 캐시 저장
        if self.use_cache:
            self._save_to_cache(query, analysis)

        return analysis

    async def _llm_analyze(self, query: str) -> QueryAnalysis:
        """LLM을 통한 쿼리 분석"""
        prompt = self.prompt_template.format(query=query)

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                max_tokens=500,
                temperature=0.1
            )

            # JSON 파싱
            result = self._parse_llm_response(query, response)
            result.analysis_source = "llm"
            return result

        except Exception as e:
            logger.error(f"LLM analysis error: {e}")
            raise

    def _parse_llm_response(self, query: str, response: str) -> QueryAnalysis:
        """LLM 응답 파싱"""
        try:
            # JSON 블록 추출
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                raise ValueError("No JSON found in response")

            data = json.loads(json_match.group())

            # Intent 파싱
            intent_str = data.get("intent", "search")
            try:
                intent = QueryIntent(intent_str)
            except ValueError:
                intent = QueryIntent.SEARCH

            # Entities 파싱
            entities = []
            for e in data.get("entities", []):
                entities.append(ExtractedEntity(
                    type=e.get("type", "term"),
                    value=e.get("value", ""),
                    confidence=float(e.get("confidence", 0.8))
                ))

            return QueryAnalysis(
                original_query=query,
                intent=intent,
                entities=entities,
                language=data.get("language", self._detect_language(query)),
                rewritten_query=data.get("rewritten_query", query),
                keywords=data.get("keywords", [])
            )

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}, response: {response[:200]}")
            return self._fallback_analyze(query)

    def _fallback_analyze(self, query: str) -> QueryAnalysis:
        """LLM 없이 규칙 기반 분석 (Fallback)"""
        # 언어 감지
        language = self._detect_language(query)

        # Intent 감지
        intent = self._detect_intent(query)

        # Entity 추출
        entities = self._extract_entities(query)

        # Query Rewriting
        rewritten = self._rewrite_query(query, entities)

        # 키워드 추출
        keywords = self._extract_keywords(query, entities)

        return QueryAnalysis(
            original_query=query,
            intent=intent,
            entities=entities,
            language=language,
            rewritten_query=rewritten,
            keywords=keywords,
            analysis_source="fallback"
        )

    def _detect_language(self, query: str) -> str:
        """언어 감지"""
        # 일본어 문자 (히라가나, 가타카나, 한자)
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', query):
            return "ja"
        # 한국어 문자
        if re.search(r'[\uAC00-\uD7AF]', query):
            return "ko"
        # 중국어 문자 (한자만)
        if re.search(r'[\u4E00-\u9FFF]', query) and not re.search(r'[\u3040-\u30FF]', query):
            return "zh"
        return "en"

    def _detect_intent(self, query: str) -> QueryIntent:
        """Intent 감지"""
        query_lower = query.lower()

        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    return intent

        return QueryIntent.SEARCH

    def _extract_entities(self, query: str) -> List[ExtractedEntity]:
        """Entity 추출"""
        entities = []
        query_lower = query.lower()

        # 명령어 추출
        for cmd in KNOWN_COMMANDS:
            if cmd.lower() in query_lower:
                entities.append(ExtractedEntity(
                    type="command",
                    value=cmd,
                    confidence=0.95
                ))

        # 제품명 추출
        for product in KNOWN_PRODUCTS:
            if product.lower() in query_lower:
                entities.append(ExtractedEntity(
                    type="product",
                    value=product,
                    confidence=0.9
                ))

        # 에러 코드 추출 (숫자형)
        error_match = re.search(r'-(\d{4,5})', query)
        if error_match:
            entities.append(ExtractedEntity(
                type="error_code",
                value=f"-{error_match.group(1)}",
                confidence=0.95
            ))

        # ABEND 코드 추출
        abend_match = re.search(r'(S[0-9A-F]{3,4}|U\d{4})', query, re.IGNORECASE)
        if abend_match:
            entities.append(ExtractedEntity(
                type="error_code",
                value=abend_match.group(1).upper(),
                confidence=0.95
            ))

        return entities

    def _rewrite_query(self, query: str, entities: List[ExtractedEntity]) -> str:
        """Query Rewriting - 검색 최적화"""
        rewritten = query

        # 일본어 필러 제거
        ja_fillers = [
            r'について説明してください[。]?',
            r'について教えてください[。]?',
            r'について詳しく教えて[。]?',
            r'とは何ですか[？?]?',
            r'はどう使いますか[？?]?',
            r'の使い方を教えて[。]?',
            r'って何[？?]?',
        ]
        for filler in ja_fillers:
            rewritten = re.sub(filler, '', rewritten)

        # 한국어 필러 제거
        ko_fillers = [
            r'에\s*대해\s*설명해\s*줘[요]?',
            r'에\s*대해\s*알려\s*줘[요]?',
            r'[이가]\s*뭐[야에요]?[?？]?',
            r'[이가]\s*무엇인가요[?？]?',
            r'사용법을?\s*알려\s*줘[요]?',
        ]
        for filler in ko_fillers:
            rewritten = re.sub(filler, '', rewritten)

        # Entity 기반 키워드 추가
        entity_keywords = []
        for entity in entities:
            if entity.type == "command":
                # 명령어 → 관련 제품 추가
                cmd = entity.value.lower()
                if "tjes" in cmd or cmd == "tjesmgr":
                    entity_keywords.extend(["TJES", "job", "batch"])
                elif "tacf" in cmd or cmd == "tacfmgr":
                    entity_keywords.extend(["TACF", "security", "access"])
                elif "osc" in cmd or cmd == "oscmgr":
                    entity_keywords.extend(["OSC", "online", "transaction"])
                elif "ofasm" in cmd or cmd == "ofasmif":
                    entity_keywords.extend(["OFASM", "assembler", "macro"])
                elif "hidb" in cmd or cmd == "hidbmgr":
                    entity_keywords.extend(["HIDB", "IMS", "database"])

                entity_keywords.append(f"{entity.value} command")

        # 최종 쿼리 구성
        rewritten = rewritten.strip()
        if entity_keywords:
            rewritten = f"{rewritten} {' '.join(entity_keywords)}"

        return rewritten.strip()

    def _extract_keywords(self, query: str, entities: List[ExtractedEntity]) -> List[str]:
        """키워드 추출"""
        keywords = []

        # Entity 값들 추가
        for entity in entities:
            keywords.append(entity.value)

        # 영어 단어 추출
        english_words = re.findall(r'[a-zA-Z_]{3,}', query)
        keywords.extend(english_words)

        # 중복 제거
        return list(dict.fromkeys(keywords))

    def _get_cache_key(self, query: str) -> str:
        """캐시 키 생성"""
        return hashlib.md5(query.encode()).hexdigest()

    def _get_from_cache(self, query: str) -> Optional[QueryAnalysis]:
        """캐시에서 조회"""
        key = self._get_cache_key(query)
        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return result
            else:
                del self._cache[key]
        return None

    def _save_to_cache(self, query: str, analysis: QueryAnalysis):
        """캐시에 저장"""
        key = self._get_cache_key(query)
        self._cache[key] = (analysis, time.time())

        # 캐시 크기 제한 (최대 1000개)
        if len(self._cache) > 1000:
            # 가장 오래된 항목 제거
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]


# 싱글톤 인스턴스
_service_instance: Optional[QueryUnderstandingService] = None


def get_query_understanding_service() -> QueryUnderstandingService:
    """QueryUnderstandingService 싱글톤 반환"""
    global _service_instance
    if _service_instance is None:
        _service_instance = QueryUnderstandingService()
    return _service_instance
