# Design: CJK 토크나이징 개선

## 1. 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           User Query                                         │
│                "OSCサーバーの起動画面"                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    KeywordExtractionService (NEW)                            │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ 1. Check Cache (LRU, max 1000 entries, TTL 1h)                         │ │
│  │    └─ Cache Key: MD5(query)                                            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                         │ miss                     │ hit                     │
│                         ▼                          │                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ 2. Detect Language (CJK check)                 │                        │ │
│  │    - has_cjk = regex[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]           │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                         │                          │                         │
│           ┌─────────────┴─────────────┐            │                         │
│           │ CJK                       │ Non-CJK    │                         │
│           ▼                           ▼            │                         │
│  ┌─────────────────────┐    ┌─────────────────────┐│                         │
│  │ 3a. LLM Extraction  │    │ 3b. Regex Fallback  ││                         │
│  │  - Timeout: 3s      │    │  - Fast path        ││                         │
│  │  - Model: Qwen2.5   │    │  - Stopwords filter ││                         │
│  └─────────────────────┘    └─────────────────────┘│                         │
│           │                           │            │                         │
│           └───────────┬───────────────┘            │                         │
│                       ▼                            ▼                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ 4. Update Cache & Return Keywords                                      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Consumer Services                                    │
│  ┌─────────────────────────┐    ┌─────────────────────────────────────────┐ │
│  │ executor.py             │    │ summary_bm25_service.py                 │ │
│  │ _analyze_query_keywords │    │ comprehensive_search                    │ │
│  │ → RAG Progress Modal    │    │ → BM25 tokenization                     │ │
│  └─────────────────────────┘    └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 데이터 모델

### 2.1 KeywordExtractionResult

```python
# app/api/services/keyword_extraction_service.py

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

class ExtractionMethod(Enum):
    LLM = "llm"
    REGEX = "regex"
    CACHE = "cache"

@dataclass
class KeywordExtractionResult:
    """키워드 추출 결과"""
    keywords: List[str]           # 추출된 키워드 목록
    method: ExtractionMethod      # 추출 방법
    language: str                 # 감지된 언어 (ja, ko, en, zh)
    extraction_time_ms: float     # 추출 소요 시간
    cache_hit: bool               # 캐시 히트 여부

    # LLM 전용 필드
    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int] = None
```

### 2.2 LLM 프롬프트 설계

```python
KEYWORD_EXTRACTION_PROMPT = """You are a keyword extraction expert for OpenFrame technical documentation.

Extract the main technical keywords from this query. Follow these rules strictly:

1. COMPOUND WORDS: Keep technical compound words together
   - "マッピング・サポート" → "マッピングサポート" (one keyword)
   - "OSCサーバー" → "OSC", "サーバー" (separate: English + Japanese)

2. PARTICLES: Split on Japanese particles (の、を、が、は、に、で)
   - "起動画面の設定" → "起動画面", "設定"

3. PRESERVE: Keep these intact
   - Error codes: -5212, -21001
   - Commands: tjesmgr, hidbmgr, oscboot
   - Acronyms: OSC, BMS, TJES, VSAM

4. REMOVE: Do not include
   - Particles: の、を、が、は、に、で、と、も
   - Question words: について、とは、ですか、ください
   - Common verbs: する、ある、いる、できる

Query: {query}

Output ONLY valid JSON (no explanation):
{{"keywords": ["keyword1", "keyword2", ...]}}
"""
```

---

## 3. 컴포넌트 설계

### 3.1 KeywordExtractionService (신규)

**파일**: `app/api/services/keyword_extraction_service.py`

```python
import re
import json
import asyncio
import hashlib
import logging
from typing import List, Tuple, Optional, Dict
from functools import lru_cache
from datetime import datetime, timedelta
import aiohttp

logger = logging.getLogger(__name__)

class KeywordExtractionService:
    """
    LLM 기반 다국어 키워드 추출 서비스.

    CJK(중국어/일본어/한국어) 텍스트의 정확한 토큰화를 위해
    LLM을 활용하며, 캐싱으로 성능을 최적화합니다.
    """

    # 캐시 설정
    CACHE_MAX_SIZE = 1000
    CACHE_TTL_SECONDS = 3600  # 1시간

    # LLM 설정
    LLM_TIMEOUT_SECONDS = 3.0
    LLM_MAX_TOKENS = 200

    def __init__(
        self,
        llm_url: str = "http://localhost:12800/v1/chat/completions",
        llm_model: str = "Qwen/Qwen2.5-7B-Instruct"
    ):
        self._llm_url = llm_url
        self._llm_model = llm_model
        self._cache: Dict[str, Tuple[List[str], datetime]] = {}

    async def extract_keywords(
        self,
        query: str,
        force_llm: bool = False
    ) -> KeywordExtractionResult:
        """
        쿼리에서 키워드를 추출합니다.

        Args:
            query: 사용자 쿼리
            force_llm: True면 캐시 무시하고 항상 LLM 호출

        Returns:
            KeywordExtractionResult
        """
        start_time = datetime.now()
        cache_key = hashlib.md5(query.encode()).hexdigest()

        # 1. 캐시 체크
        if not force_llm and cache_key in self._cache:
            keywords, cached_at = self._cache[cache_key]
            if datetime.now() - cached_at < timedelta(seconds=self.CACHE_TTL_SECONDS):
                return KeywordExtractionResult(
                    keywords=keywords,
                    method=ExtractionMethod.CACHE,
                    language=self._detect_language(query),
                    extraction_time_ms=0.0,
                    cache_hit=True
                )

        # 2. 언어 감지
        language = self._detect_language(query)
        has_cjk = language in ("ja", "ko", "zh")

        # 3. 추출 방법 선택
        if has_cjk:
            keywords, method, llm_model = await self._extract_llm(query)
            if not keywords:  # LLM 실패 시 폴백
                keywords = self._extract_regex(query)
                method = ExtractionMethod.REGEX
                llm_model = None
        else:
            keywords = self._extract_regex(query)
            method = ExtractionMethod.REGEX
            llm_model = None

        # 4. 캐시 업데이트
        self._cache[cache_key] = (keywords, datetime.now())
        self._cleanup_cache()

        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

        return KeywordExtractionResult(
            keywords=keywords,
            method=method,
            language=language,
            extraction_time_ms=elapsed_ms,
            cache_hit=False,
            llm_model=llm_model if method == ExtractionMethod.LLM else None
        )

    def _detect_language(self, text: str) -> str:
        """언어 감지"""
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', text):
            return "ja"  # 히라가나/카타카나 → 일본어
        if re.search(r'[\uac00-\ud7af]', text):
            return "ko"  # 한글 → 한국어
        if re.search(r'[\u4e00-\u9fff]', text):
            return "zh"  # 한자만 → 중국어
        return "en"

    async def _extract_llm(self, query: str) -> Tuple[List[str], ExtractionMethod, Optional[str]]:
        """LLM 기반 키워드 추출"""
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

                        # JSON 파싱
                        json_match = re.search(r'\{[^{}]*\}', content)
                        if json_match:
                            result = json.loads(json_match.group())
                            keywords = result.get("keywords", [])
                            if keywords:
                                logger.debug(f"[LLM Keywords] '{query}' -> {keywords}")
                                return keywords, ExtractionMethod.LLM, self._llm_model

        except asyncio.TimeoutError:
            logger.warning(f"[LLM Keywords] Timeout ({self.LLM_TIMEOUT_SECONDS}s) for: {query[:50]}")
        except Exception as e:
            logger.warning(f"[LLM Keywords] Error: {type(e).__name__}: {e}")

        return [], ExtractionMethod.REGEX, None

    def _extract_regex(self, query: str) -> List[str]:
        """Regex 기반 키워드 추출 (폴백)"""
        # 에러 코드 먼저 추출
        error_codes = re.findall(r'-\d{4,5}', query)

        # 토큰 추출
        tokens = re.findall(r'[a-zA-Z0-9_\-]+|[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\uac00-\ud7af]+', query)

        # Stopwords 제거
        stopwords = self._get_stopwords()
        keywords = [t for t in tokens if t.lower() not in stopwords and len(t) >= 2]

        return error_codes + keywords[:10]

    def _get_stopwords(self) -> set:
        """다국어 불용어 목록"""
        return {
            # 일본어 조사/조동사
            'の', 'に', 'は', 'を', 'た', 'が', 'で', 'て', 'と', 'し', 'も',
            'する', 'から', 'な', 'こと', 'など', 'ない', 'この', 'その',
            'また', 'もの', 'という', 'より', 'ため', 'について', 'とは',
            'ください', 'できる', 'ある', 'いる', 'なる', 'れる', 'られる',
            # 한국어 조사
            '이', '가', '은', '는', '을', '를', '의', '에', '에서', '로',
            '으로', '와', '과', '도', '만', '까지', '부터', '대해', '대한',
            # 영어
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'about', 'what',
            'how', 'why', 'when', 'where', 'which', 'who', 'whom',
        }

    def _cleanup_cache(self):
        """오래된 캐시 항목 정리"""
        if len(self._cache) > self.CACHE_MAX_SIZE:
            # 오래된 항목 50% 제거
            sorted_items = sorted(self._cache.items(), key=lambda x: x[1][1])
            remove_count = len(self._cache) // 2
            for key, _ in sorted_items[:remove_count]:
                del self._cache[key]


# 싱글톤 인스턴스
_service: Optional[KeywordExtractionService] = None

def get_keyword_extraction_service() -> KeywordExtractionService:
    """싱글톤 서비스 인스턴스 반환"""
    global _service
    if _service is None:
        import os
        _service = KeywordExtractionService(
            llm_url=os.getenv("LLM_API_URL", "http://localhost:12800/v1/chat/completions"),
            llm_model=os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        )
    return _service
```

### 3.2 executor.py 수정

**파일**: `app/api/agents/executor.py`

**변경 위치**: Line 355-432 (`_analyze_query_keywords` 함수)

```python
# 기존 함수를 async로 변경하고 KeywordExtractionService 사용

async def _analyze_query_keywords(query: str, language: str = "ko") -> Dict[str, Any]:
    """
    LLM 기반 키워드 분석으로 쿼리의 키워드와 의도를 추출합니다.

    Args:
        query: User query string
        language: User's configured language (ko, en, ja)

    Returns:
        Dict with keywords, intent, search_strategy (localized)
    """
    from app.api.services.keyword_extraction_service import get_keyword_extraction_service

    # Localized labels (기존 코드 유지)
    INTENT_LABELS = { ... }
    STRATEGY_LABELS = { ... }

    # 키워드 추출 서비스 호출
    service = get_keyword_extraction_service()
    result = await service.extract_keywords(query)

    keywords = result.keywords

    # 의도 분류 (기존 로직 유지)
    intent_key = _classify_intent(query)

    # 검색 전략 결정 (기존 로직 유지)
    strategy_keys = _determine_strategy(query, keywords)

    return {
        "original_query": query,
        "keywords": keywords[:10],
        "intent": get_label(INTENT_LABELS, intent_key),
        "search_strategy": [get_label(STRATEGY_LABELS, sk) for sk in strategy_keys],
        "token_count": len(keywords),
        "extraction_method": result.method.value,  # NEW: 추출 방법 표시
        "extraction_time_ms": result.extraction_time_ms,  # NEW: 추출 시간
    }
```

**호출 지점 수정** (Line 2197):

```python
# 기존 (동기)
query_analysis = _analyze_query_keywords(task, language=user_language)

# 변경 (비동기)
query_analysis = await _analyze_query_keywords(task, language=user_language)
```

### 3.3 summary_bm25_service.py 수정

**파일**: `app/api/services/summary_bm25_service.py`

**변경 위치**: `_extract_keywords_llm()` 메서드 (Line 1192-1285)

```python
# 기존 _extract_keywords_llm을 KeywordExtractionService로 대체

async def _extract_keywords_llm(self, query: str) -> Tuple[List[str], List[str], List[str]]:
    """
    LLM 기반 키워드 추출 (KeywordExtractionService 사용).

    Returns:
        Tuple of (commands, error_codes, terms)
    """
    from app.api.services.keyword_extraction_service import get_keyword_extraction_service

    service = get_keyword_extraction_service()
    result = await service.extract_keywords(query)

    # 키워드를 타입별로 분류
    commands = []
    error_codes = []
    terms = []

    for kw in result.keywords:
        if re.match(r'^-?\d{4,5}$', kw):
            error_codes.append(kw)
        elif re.match(r'^[a-z][a-z0-9]*(?:mgr|init|boot|ctl)$', kw.lower()):
            commands.append(kw.lower())
        elif re.match(r'^[A-Z]{2,}[A-Z0-9]*$', kw):
            terms.append(kw.upper())
        else:
            # 일반 키워드는 terms에 추가
            terms.append(kw)

    return commands, error_codes, terms
```

---

## 4. API 흐름

### 4.1 RAG Progress Modal 키워드 표시

```
User Query: "OSCサーバーの起動画面"
    │
    ▼
executor.py: _analyze_query_keywords()
    │
    ▼
KeywordExtractionService.extract_keywords()
    │
    ├─ Cache Miss → LLM 호출
    │   Prompt: "Extract keywords from: OSCサーバーの起動画面"
    │   Response: {"keywords": ["OSC", "サーバー", "起動画面"]}
    │
    ▼
Return: {
    "keywords": ["OSC", "サーバー", "起動画面"],
    "intent": "情報検索",
    "extraction_method": "llm",
    "extraction_time_ms": 450
}
    │
    ▼
SSE Stream: chunk_type="rag_analysis"
    │
    ▼
Frontend: SearchProgressModal 표시
    抽出されたキーワード: OSC, サーバー, 起動画面
```

### 4.2 BM25 검색 토큰화

```
Query: "マッピング・サポートの構造"
    │
    ▼
summary_bm25_service.py: comprehensive_search()
    │
    ▼
_extract_keywords_llm() → KeywordExtractionService
    │
    ▼
Keywords: ["マッピングサポート", "構造"]
    │
    ▼
BM25 검색 실행 (정확한 토큰으로)
```

---

## 5. 성능 최적화

### 5.1 캐시 전략

| 항목 | 값 | 설명 |
|------|-----|------|
| 캐시 크기 | 1000개 | LRU 방식 |
| TTL | 1시간 | 오래된 항목 자동 만료 |
| 키 생성 | MD5(query) | 빠른 해시 |

### 5.2 타임아웃 처리

```python
try:
    keywords = await asyncio.wait_for(
        service.extract_keywords(query),
        timeout=3.0
    )
except asyncio.TimeoutError:
    # Regex 폴백
    keywords = _extract_regex_fallback(query)
```

### 5.3 예상 성능

| 시나리오 | 예상 지연 |
|----------|----------|
| 캐시 히트 | < 1ms |
| LLM 호출 (정상) | 300-500ms |
| LLM 타임아웃 | 3000ms + 폴백 |
| Regex 폴백 | < 5ms |

---

## 6. 에러 처리

### 6.1 LLM 서버 불가용

```python
async def _extract_llm(self, query: str):
    try:
        # LLM 호출
        ...
    except aiohttp.ClientConnectorError:
        logger.warning("LLM server unavailable, using regex fallback")
        return self._extract_regex(query), ExtractionMethod.REGEX, None
```

### 6.2 잘못된 LLM 응답

```python
# JSON 파싱 실패 시
json_match = re.search(r'\{[^{}]*\}', content)
if not json_match:
    logger.warning(f"Invalid LLM response: {content[:100]}")
    return [], ExtractionMethod.REGEX, None

# keywords 필드 없음
result = json.loads(json_match.group())
keywords = result.get("keywords", [])
if not keywords or not isinstance(keywords, list):
    return [], ExtractionMethod.REGEX, None
```

---

## 7. 테스트 케이스

### 7.1 일본어 쿼리

| 입력 | 예상 출력 |
|------|----------|
| マッピング・サポート・システムのフローチャート | ["マッピングサポート", "システム", "フローチャート"] |
| OSCサーバーの起動画面 | ["OSC", "サーバー", "起動画面"] |
| tjesmgrについて教えてください | ["tjesmgr"] |
| -5212エラーの原因 | ["-5212", "エラー", "原因"] |

### 7.2 한국어 쿼리

| 입력 | 예상 출력 |
|------|----------|
| tjesmgr 명령어 사용법 | ["tjesmgr", "명령어", "사용법"] |
| -5212 에러 해결 방법 | ["-5212", "에러", "해결", "방법"] |
| OSC와 TJES의 차이점 | ["OSC", "TJES", "차이점"] |

### 7.3 영어 쿼리

| 입력 | 예상 출력 |
|------|----------|
| How to configure tjesmgr | ["configure", "tjesmgr"] |
| Error -5212 resolution | ["-5212", "resolution"] |

---

## 8. 구현 순서

| Step | 작업 | 파일 | 우선순위 |
|------|------|------|----------|
| 1 | KeywordExtractionService 생성 | `app/api/services/keyword_extraction_service.py` | 필수 |
| 2 | executor.py 수정 | `app/api/agents/executor.py:355-432` | 필수 |
| 3 | summary_bm25_service.py 수정 | `app/api/services/summary_bm25_service.py:1192` | 필수 |
| 4 | 단위 테스트 | `tests/api/test_keyword_extraction.py` | 권장 |
| 5 | E2E 테스트 | `e2e/e2e_cjk_tokenization.js` | 권장 |

---

## 9. 의존성

### 9.1 기존 의존성 (추가 설치 없음)

- `aiohttp`: HTTP 클라이언트 (이미 설치됨)
- `re`: 정규식 (표준 라이브러리)
- `hashlib`: 해시 생성 (표준 라이브러리)

### 9.2 환경 변수

```bash
# .env
LLM_API_URL=http://localhost:12800/v1/chat/completions
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
```

---

## 10. 롤백 계획

문제 발생 시 즉시 롤백 가능:

1. `KeywordExtractionService` 제거
2. `executor.py`의 `_analyze_query_keywords`를 동기 함수로 복원
3. `summary_bm25_service.py`의 `_extract_keywords_llm`을 원본으로 복원

**롤백 트리거 조건**:
- LLM 응답 오류율 > 10%
- 평균 응답 지연 > 2초
- 키워드 품질 저하 (수동 검증)
