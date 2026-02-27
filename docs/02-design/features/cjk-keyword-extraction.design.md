# CJK Keyword Extraction Improvement Design

## Feature: cjk-keyword-extraction
## Version: v1.0
## Created: 2026-01-31
## Status: Draft

---

## 1. Problem Summary

Summary BM25 검색에서 **일본어/한국어 키워드가 추출되지 않아** OSI 문서가 검색되지 않는 문제.

**현재 상태:**
- `structure_parser.py:70-74` - 영문 대문자만 추출하는 `KEYWORD_PATTERNS`
- `index.json` - 175개 문서의 키워드가 모두 영문만 포함
- OSI Administrator Guide 키워드: `['ADMINSERVER', 'ALPHA', 'APPLCTN'...]` (일본어 없음)

**필요 상태:**
- OSI Administrator Guide 키워드: `['OSI', '起動', '終了', 'ログ', 'システム', '運用'...]`

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CJK Keyword Extraction Flow                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [PDF Processing Pipeline]                                          │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  structure_parser.py::_extract_keywords()                    │   │
│  │                                                              │   │
│  │  INPUT: raw_text, title                                      │   │
│  │                                                              │   │
│  │  ┌─────────────────┐  ┌─────────────────┐                   │   │
│  │  │ English         │  │ Japanese        │  ← NEW            │   │
│  │  │ KEYWORD_PATTERNS│  │ CJKTokenizer    │                   │   │
│  │  │ (regex)         │  │ (fugashi)       │                   │   │
│  │  └────────┬────────┘  └────────┬────────┘                   │   │
│  │           │                    │                             │   │
│  │           ▼                    ▼                             │   │
│  │     ┌─────────────────────────────┐                         │   │
│  │     │   Merged Keywords Set       │                         │   │
│  │     │   ['OSI', '起動', '終了'...]│                         │   │
│  │     └─────────────────────────────┘                         │   │
│  │                    │                                         │   │
│  │                    ▼                                         │   │
│  │  OUTPUT: node.keywords[:7]                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  [structure_generator.py::generate_batch_index()]                   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  uploads/summaries/structures/index.json                     │   │
│  │                                                              │   │
│  │  documents[].keywords: ['OSI', '起動', '終了', 'ログ'...]   │   │
│  │  all_keywords: ['OSI', '起動', '終了', ...]                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     BM25 Search Flow (Runtime)                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [User Query: "OSIシステムを起動する方法"]                          │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  summary_bm25_service.py::_tokenize()                        │   │
│  │                                                              │   │
│  │  Query Tokens: ['osi', 'システム', 'シス', 'ステ', 'テム',   │   │
│  │                 '起動', '起動す', '方法']                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│       │                                                             │
│       ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  BM25Okapi(tokenized_docs).get_scores(query_tokens)          │   │
│  │                                                              │   │
│  │  Document Keywords Include: ['起動', '終了', 'ログ'...]      │   │
│  │  → Token Match! → High BM25 Score                            │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Design

### 3.1 New Service: CJKTokenizerService

**파일:** `app/api/services/cjk_tokenizer_service.py`

```python
"""
CJK Tokenizer Service

일본어/한국어/중국어 텍스트의 형태소 분석 및 키워드 추출 서비스.
fugashi(MeCab wrapper)를 사용하여 일본어 명사/동사를 추출합니다.
"""

import re
import logging
from typing import List, Optional, Set
from functools import lru_cache

logger = logging.getLogger(__name__)

# Lazy import for fugashi (optional dependency)
_tagger = None

def _get_tagger():
    """Lazy initialization of fugashi tagger"""
    global _tagger
    if _tagger is None:
        try:
            import fugashi
            _tagger = fugashi.Tagger()
            logger.info("[CJKTokenizer] fugashi initialized successfully")
        except ImportError:
            logger.warning("[CJKTokenizer] fugashi not installed, Japanese tokenization disabled")
            _tagger = False
        except Exception as e:
            logger.warning(f"[CJKTokenizer] Failed to initialize fugashi: {e}")
            _tagger = False
    return _tagger if _tagger else None


class CJKTokenizerService:
    """
    CJK 텍스트 토크나이저 및 키워드 추출기

    Features:
    - 일본어: fugashi(MeCab) 기반 형태소 분석
    - 한국어: 2자 이상 연속 한글 추출
    - 영문: 기존 regex 패턴 유지

    Note:
    - fugashi가 설치되지 않은 환경에서는 일본어 토크나이징이 제한됨
    - fallback으로 bi-gram 추출 사용
    """

    # 일본어 품사 태그 (명사, 동사, 형용사)
    JA_TARGET_POS = {'名詞', '動詞', '形容詞'}

    # 일본어 제외 품사 (조사, 기호 등)
    JA_EXCLUDE_POS = {'助詞', '助動詞', '記号', '補助記号'}

    # 일본어 불용어 (너무 일반적인 단어)
    JA_STOPWORDS = {
        'こと', 'もの', 'それ', 'これ', 'あれ', 'よう', 'ため',
        'とき', 'ところ', 'さん', 'など', 'ほか', 'まま', 'わけ',
        'する', 'なる', 'ある', 'いる', 'れる', 'られる',
        '場合', '方法', '内容', '説明', '参照', '使用', '設定',
    }

    # 한국어 불용어
    KO_STOPWORDS = {
        '것', '수', '등', '및', '또는', '그', '이', '저', '때문',
        '경우', '방법', '내용', '설명', '참조', '사용', '설정',
    }

    def __init__(self, min_word_length: int = 2, max_keywords: int = 15):
        self.min_word_length = min_word_length
        self.max_keywords = max_keywords

    def extract_japanese_keywords(self, text: str) -> List[str]:
        """
        일본어 텍스트에서 키워드 추출 (명사/동사/형용사)

        Args:
            text: 일본어 텍스트

        Returns:
            추출된 키워드 리스트 (빈도순 정렬)
        """
        tagger = _get_tagger()

        if tagger is None:
            # fugashi 미설치 시 fallback
            return self._extract_japanese_fallback(text)

        keywords = {}

        try:
            for word in tagger(text):
                # 품사 확인
                pos1 = word.feature.pos1 if hasattr(word.feature, 'pos1') else ''

                if pos1 not in self.JA_TARGET_POS:
                    continue

                surface = word.surface

                # 길이 체크
                if len(surface) < self.min_word_length:
                    continue

                # 불용어 체크
                if surface in self.JA_STOPWORDS:
                    continue

                # 숫자만 있는 경우 제외
                if surface.isdigit():
                    continue

                # 빈도 카운트
                keywords[surface] = keywords.get(surface, 0) + 1

        except Exception as e:
            logger.warning(f"[CJKTokenizer] Japanese tokenization error: {e}")
            return self._extract_japanese_fallback(text)

        # 빈도순 정렬 후 반환
        sorted_keywords = sorted(keywords.items(), key=lambda x: -x[1])
        return [kw for kw, _ in sorted_keywords[:self.max_keywords]]

    def _extract_japanese_fallback(self, text: str) -> List[str]:
        """
        fugashi 미설치 시 fallback - 히라가나/가타카나/한자 연속 문자열 추출
        """
        # 일본어 문자 패턴 (히라가나 + 가타카나 + 한자)
        pattern = r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]{2,}'

        keywords = {}
        matches = re.findall(pattern, text)

        for match in matches:
            if match in self.JA_STOPWORDS:
                continue
            keywords[match] = keywords.get(match, 0) + 1

        sorted_keywords = sorted(keywords.items(), key=lambda x: -x[1])
        return [kw for kw, _ in sorted_keywords[:self.max_keywords]]

    def extract_korean_keywords(self, text: str) -> List[str]:
        """
        한국어 텍스트에서 키워드 추출 (2자 이상 연속 한글)

        Args:
            text: 한국어 텍스트

        Returns:
            추출된 키워드 리스트 (빈도순 정렬)
        """
        # 한글 연속 문자열 패턴
        pattern = r'[가-힣]{2,}'

        keywords = {}
        matches = re.findall(pattern, text)

        for match in matches:
            if match in self.KO_STOPWORDS:
                continue
            keywords[match] = keywords.get(match, 0) + 1

        sorted_keywords = sorted(keywords.items(), key=lambda x: -x[1])
        return [kw for kw, _ in sorted_keywords[:self.max_keywords]]

    def extract_english_keywords(self, text: str) -> List[str]:
        """
        영문 텍스트에서 키워드 추출 (대문자 약어 + 명령어 패턴)

        Args:
            text: 영문 텍스트

        Returns:
            추출된 키워드 리스트
        """
        keywords = {}

        patterns = [
            r'\b([A-Z]{2,}[A-Z0-9]*)\b',  # 대문자 약어
            r'\b([a-z]+(?:init|boot|down|start|stop|mgr|ctl|cmd))\b',  # 명령어
            r'\b(tjes[a-z]*|osc[a-z]*|tac[a-z]*|hidb[a-z]*|ndb[a-z]*)\b',  # OpenFrame 명령어
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                m_upper = m.upper()
                if len(m_upper) >= 2:
                    keywords[m_upper] = keywords.get(m_upper, 0) + 1

        # 불용어 제거
        stopwords = {'THE', 'AND', 'FOR', 'NOT', 'ARE', 'ALL', 'WITH', 'THIS', 'THAT', 'PDF'}
        for sw in stopwords:
            keywords.pop(sw, None)

        sorted_keywords = sorted(keywords.items(), key=lambda x: -x[1])
        return [kw for kw, _ in sorted_keywords[:self.max_keywords]]

    def extract_all_keywords(
        self,
        text: str,
        title: str = "",
        min_frequency: int = 1
    ) -> List[str]:
        """
        텍스트에서 모든 언어의 키워드 통합 추출

        Args:
            text: 원본 텍스트
            title: 제목 (제목에서 추출된 키워드 우선)
            min_frequency: 최소 출현 빈도 (기본값 1, 긴 문서에서는 2 권장)

        Returns:
            통합 키워드 리스트 (최대 max_keywords개)
        """
        all_keywords: Set[str] = set()

        # 1. 제목에서 키워드 추출 (우선순위 높음)
        if title:
            title_en = self.extract_english_keywords(title)
            title_ja = self.extract_japanese_keywords(title)
            title_ko = self.extract_korean_keywords(title)
            all_keywords.update(title_en[:3])  # 제목에서 최대 3개씩
            all_keywords.update(title_ja[:3])
            all_keywords.update(title_ko[:3])

        # 2. 본문에서 키워드 추출
        en_keywords = self.extract_english_keywords(text)
        ja_keywords = self.extract_japanese_keywords(text)
        ko_keywords = self.extract_korean_keywords(text)

        # 3. 통합 (영문, 일본어, 한국어 균형있게)
        all_keywords.update(en_keywords[:5])
        all_keywords.update(ja_keywords[:5])
        all_keywords.update(ko_keywords[:5])

        # 4. 정렬 및 반환
        return sorted(list(all_keywords))[:self.max_keywords]


# Singleton instance
_cjk_tokenizer_service: Optional[CJKTokenizerService] = None


def get_cjk_tokenizer_service() -> CJKTokenizerService:
    """Get or create singleton CJKTokenizerService instance"""
    global _cjk_tokenizer_service
    if _cjk_tokenizer_service is None:
        _cjk_tokenizer_service = CJKTokenizerService()
    return _cjk_tokenizer_service
```

### 3.2 Modification: structure_parser.py

**파일:** `scripts/manual_processor/parsers/structure_parser.py`

**변경 위치:** `_extract_keywords()` 메서드 (447-473라인)

```python
def _extract_keywords(self, text: str, title: str) -> List[str]:
    """텍스트에서 키워드 추출 (CJK 지원)

    변경: 영문만 추출하던 로직을 CJK 언어 지원으로 확장
    """
    from app.api.services.cjk_tokenizer_service import get_cjk_tokenizer_service

    try:
        tokenizer = get_cjk_tokenizer_service()
        keywords = tokenizer.extract_all_keywords(
            text=text,
            title=title,
            min_frequency=2 if len(text) > 1000 else 1
        )
        return keywords[:7]  # 최대 7개

    except ImportError:
        # Fallback: 기존 영문만 추출 로직
        logger.warning("[StructureParser] CJKTokenizerService not available, using English-only extraction")
        return self._extract_keywords_english_only(text, title)


def _extract_keywords_english_only(self, text: str, title: str) -> List[str]:
    """기존 영문 전용 키워드 추출 (fallback)"""
    keywords = set()

    # 제목에서 키워드 추출
    title_words = re.findall(r'\b[A-Z][a-z]+\b|\b[A-Z]{2,}\b', title)
    keywords.update(title_words)

    # 텍스트에서 키워드 추출
    for pattern in self.KEYWORD_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        freq = {}
        for m in matches:
            m_upper = m.upper()
            freq[m_upper] = freq.get(m_upper, 0) + 1

        for kw, count in sorted(freq.items(), key=lambda x: -x[1])[:5]:
            if len(kw) >= 2 and count >= 2:
                keywords.add(kw)

    # 일반적인 단어 제거
    common_words = {"THE", "AND", "FOR", "NOT", "ARE", "ALL", "WITH", "THIS", "THAT"}
    keywords = keywords - common_words

    return sorted(list(keywords))[:7]
```

### 3.3 Index Rebuild Script

**파일:** `scripts/rebuild_structure_keywords.py`

```python
#!/usr/bin/env python3
"""
STRUCTURES 인덱스 키워드 재생성 스크립트

기존 _structure.json 파일들의 키워드를 CJK 토크나이저로 재추출하고
index.json을 업데이트합니다.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def rebuild_keywords(summaries_dir: Path = Path("uploads/summaries")) -> Dict[str, Any]:
    """
    STRUCTURES 디렉토리의 모든 문서 키워드 재생성

    Args:
        summaries_dir: summaries 디렉토리 경로

    Returns:
        처리 결과 통계
    """
    from app.api.services.cjk_tokenizer_service import get_cjk_tokenizer_service

    structures_dir = summaries_dir / "structures"
    if not structures_dir.exists():
        logger.error(f"structures 디렉토리가 없습니다: {structures_dir}")
        return {"error": "Directory not found"}

    tokenizer = get_cjk_tokenizer_service()

    stats = {
        "processed": 0,
        "updated": 0,
        "errors": 0,
        "total_keywords_before": 0,
        "total_keywords_after": 0,
    }

    # 1. 모든 _structure.json 파일 처리
    json_files = list(structures_dir.glob("*_structure.json"))
    logger.info(f"처리할 파일 수: {len(json_files)}")

    documents = []
    all_keywords = set()

    for json_file in json_files:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            stats["processed"] += 1

            # 기존 키워드 수집
            old_keywords = _collect_keywords_recursive(data.get("hierarchy", []))
            stats["total_keywords_before"] += len(old_keywords)

            # 새 키워드 추출
            new_keywords = set()
            _update_keywords_recursive(
                nodes=data.get("hierarchy", []),
                tokenizer=tokenizer,
                new_keywords=new_keywords
            )

            stats["total_keywords_after"] += len(new_keywords)

            # 변경사항이 있으면 저장
            if new_keywords != old_keywords:
                stats["updated"] += 1
                json_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                logger.info(f"  Updated: {json_file.name} ({len(old_keywords)} -> {len(new_keywords)} keywords)")

            # index.json용 데이터 수집
            doc_info = {
                "file_name": data.get("file_name", json_file.stem),
                "title": data.get("title", ""),
                "pages": data.get("total_pages", 0),
                "nodes": _count_nodes(data.get("hierarchy", [])),
                "images": len(data.get("images_index", [])),
                "valid": data.get("validation", {}).get("valid", True),
                "coverage": data.get("validation", {}).get("coverage_ratio", 1.0),
                "keywords": sorted(list(new_keywords))[:10],
            }
            documents.append(doc_info)
            all_keywords.update(new_keywords)

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"  Error processing {json_file.name}: {e}")

    # 2. index.json 업데이트
    index_path = structures_dir / "index.json"
    index_data = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_documents": len(documents),
            "total_pages": sum(d["pages"] for d in documents),
            "total_nodes": sum(d["nodes"] for d in documents),
            "total_images": sum(d["images"] for d in documents),
            "valid_documents": len([d for d in documents if d["valid"]]),
        },
        "documents": documents,
        "all_keywords": sorted(list(all_keywords))[:100],
    }

    index_path.write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    logger.info(f"\n=== 처리 완료 ===")
    logger.info(f"  처리: {stats['processed']}")
    logger.info(f"  업데이트: {stats['updated']}")
    logger.info(f"  에러: {stats['errors']}")
    logger.info(f"  키워드 (전): {stats['total_keywords_before']}")
    logger.info(f"  키워드 (후): {stats['total_keywords_after']}")
    logger.info(f"  전체 고유 키워드: {len(all_keywords)}")

    return stats


def _collect_keywords_recursive(nodes: List[Dict]) -> set:
    """노드에서 기존 키워드 수집 (재귀)"""
    keywords = set()
    for node in nodes:
        keywords.update(node.get("keywords", []))
        keywords.update(_collect_keywords_recursive(node.get("children", [])))
    return keywords


def _update_keywords_recursive(
    nodes: List[Dict],
    tokenizer,
    new_keywords: set
) -> None:
    """노드의 키워드 업데이트 (재귀)"""
    for node in nodes:
        # raw_text 또는 summary에서 키워드 추출
        text = node.get("raw_text", "") or node.get("summary", "")
        title = node.get("title", "")

        if text or title:
            extracted = tokenizer.extract_all_keywords(text, title)
            node["keywords"] = extracted[:7]
            new_keywords.update(extracted)

        # 자식 노드 처리
        _update_keywords_recursive(
            node.get("children", []),
            tokenizer,
            new_keywords
        )


def _count_nodes(nodes: List[Dict]) -> int:
    """노드 수 계산 (재귀)"""
    count = len(nodes)
    for node in nodes:
        count += _count_nodes(node.get("children", []))
    return count


if __name__ == "__main__":
    import sys

    summaries_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("uploads/summaries")
    rebuild_keywords(summaries_dir)
```

---

## 4. Dependencies

### 4.1 New Python Dependencies

**파일:** `requirements-api.txt` (추가)

```
# CJK Tokenization
fugashi[unidic-lite]>=1.3.0  # Japanese morphological analysis
```

**Docker 설정:** `Dockerfile` (필요시)

```dockerfile
# fugashi를 위한 C++ 빌드 도구 (이미 설치된 경우 불필요)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
```

### 4.2 Optional Dependencies

- `konlpy`: 한국어 형태소 분석 (현재는 regex로 대체)
- `jieba`: 중국어 형태소 분석 (향후 확장용)

---

## 5. File Changes Summary

| File | Type | Changes |
|------|------|---------|
| `app/api/services/cjk_tokenizer_service.py` | NEW | CJK 토크나이저 서비스 |
| `scripts/manual_processor/parsers/structure_parser.py` | MODIFY | `_extract_keywords()` 수정 |
| `scripts/rebuild_structure_keywords.py` | NEW | 인덱스 재생성 스크립트 |
| `requirements-api.txt` | MODIFY | fugashi 의존성 추가 |
| `uploads/summaries/structures/index.json` | REGENERATE | 키워드 재생성 |
| `uploads/summaries/structures/*_structure.json` | REGENERATE | 각 문서 키워드 재생성 |

---

## 6. Test Specifications

### 6.1 Unit Tests

**파일:** `tests/api/services/test_cjk_tokenizer_service.py`

```python
import pytest
from app.api.services.cjk_tokenizer_service import CJKTokenizerService


class TestCJKTokenizerService:
    @pytest.fixture
    def tokenizer(self):
        return CJKTokenizerService()

    def test_extract_japanese_keywords(self, tokenizer):
        """일본어 키워드 추출 테스트"""
        text = "OSIシステムを起動する方法について説明します。ログファイルの管理も重要です。"
        keywords = tokenizer.extract_japanese_keywords(text)

        assert "起動" in keywords or "システム" in keywords
        assert "ログ" in keywords or "ファイル" in keywords

    def test_extract_korean_keywords(self, tokenizer):
        """한국어 키워드 추출 테스트"""
        text = "시스템을 기동하는 방법에 대해 설명합니다. 로그 파일 관리도 중요합니다."
        keywords = tokenizer.extract_korean_keywords(text)

        assert "시스템" in keywords
        assert "기동" in keywords or "방법" in keywords

    def test_extract_english_keywords(self, tokenizer):
        """영문 키워드 추출 테스트"""
        text = "The OSI system provides VSAM and TJES features. Use tjesmgr to manage jobs."
        keywords = tokenizer.extract_english_keywords(text)

        assert "OSI" in keywords
        assert "VSAM" in keywords or "TJES" in keywords
        assert "TJESMGR" in keywords

    def test_extract_all_keywords_mixed(self, tokenizer):
        """다국어 혼합 텍스트 키워드 추출 테스트"""
        text = "OSIシステムの起動方法。TJES provides job scheduling."
        title = "OSI Administrator Guide"

        keywords = tokenizer.extract_all_keywords(text, title)

        # 영문 키워드
        assert any(kw in keywords for kw in ["OSI", "TJES"])
        # 일본어 키워드
        assert any(kw in keywords for kw in ["起動", "システム", "方法"])

    def test_stopwords_filtered(self, tokenizer):
        """불용어 필터링 테스트"""
        text = "これはシステムの説明です。それについて参照してください。"
        keywords = tokenizer.extract_japanese_keywords(text)

        # 불용어는 제외되어야 함
        assert "これ" not in keywords
        assert "それ" not in keywords
        assert "説明" not in keywords  # 불용어 리스트에 포함
```

### 6.2 Integration Tests

**파일:** `tests/integration/test_bm25_cjk_search.py`

```python
import pytest
from app.api.services.summary_bm25_service import get_summary_bm25_service


@pytest.mark.asyncio
class TestBM25CJKSearch:
    async def test_japanese_query_finds_osi_document(self):
        """일본어 쿼리로 OSI 문서 검색 테스트"""
        service = get_summary_bm25_service()
        await service.initialize()

        # 일본어 쿼리
        results = await service.search(
            "OSIシステムを起動する方法",
            top_k=5
        )

        # OSI 관련 문서가 상위에 반환되어야 함
        assert len(results) > 0

        # 상위 3개 중 OSI 문서가 있어야 함
        top_docs = [r.document for r in results[:3]]
        osi_found = any("OSI" in doc.name.upper() for doc in top_docs)
        assert osi_found, f"OSI document not found in top 3: {[d.name for d in top_docs]}"

    async def test_korean_query_search(self):
        """한국어 쿼리 검색 테스트"""
        service = get_summary_bm25_service()
        await service.initialize()

        results = await service.search(
            "시스템 기동 방법",
            top_k=5
        )

        # 결과가 반환되어야 함
        assert len(results) > 0
```

### 6.3 E2E Tests

**파일:** `e2e/e2e_sentence_test.js` (추가)

```javascript
// CJK Keyword Search Test Cases
const CJK_KEYWORD_TESTS = [
    {
        query: "OSIシステムを起動する方法",
        expected: ["OSI", "Administrator"],
        notExpected: ["XSP", "MSP", "Utility"],
        category: "STRUCTURES"
    },
    {
        query: "ログファイルの管理方法",
        expected: ["ログ", "管理", "OSI"],
        notExpected: [],
        category: "STRUCTURES"
    },
    {
        query: "VSAMデータセットの定義",
        expected: ["VSAM", "データセット"],
        notExpected: [],
        category: "STRUCTURES"
    }
];
```

---

## 7. Migration Plan

### 7.1 Phase 1: Service Implementation

1. `cjk_tokenizer_service.py` 생성
2. `requirements-api.txt`에 fugashi 추가
3. Unit tests 작성 및 통과 확인

### 7.2 Phase 2: Parser Integration

1. `structure_parser.py` 수정
2. Integration tests 작성 및 통과 확인

### 7.3 Phase 3: Index Rebuild

```bash
# 1. 백업
cp -r uploads/summaries/structures uploads/summaries/structures_backup_$(date +%Y%m%d)

# 2. 키워드 재생성
python scripts/rebuild_structure_keywords.py uploads/summaries

# 3. 검증
python -c "
import json
from pathlib import Path

index = json.loads(Path('uploads/summaries/structures/index.json').read_text())
keywords = index.get('all_keywords', [])

# CJK 키워드 존재 확인
ja_keywords = [k for k in keywords if any(ord(c) > 0x3000 for c in k)]
print(f'Total keywords: {len(keywords)}')
print(f'Japanese keywords: {len(ja_keywords)}')
print(f'Sample JA keywords: {ja_keywords[:10]}')
"
```

### 7.4 Phase 4: E2E Verification

```bash
# E2E 테스트 실행
cd e2e && node e2e_sentence_test.js

# OSI 검색 결과 확인
curl -s -X POST http://localhost:9000/api/v1/agents/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"task": "OSIシステムを起動する方法", "agent_type": "rag"}' | jq .
```

---

## 8. Rollback Plan

```bash
# 1. fugashi 제거
pip uninstall fugashi unidic-lite

# 2. index.json 복원
cp uploads/summaries/structures_backup_*/index.json uploads/summaries/structures/

# 3. structure_parser.py 복원
git checkout scripts/manual_processor/parsers/structure_parser.py

# 4. cjk_tokenizer_service.py 제거
rm app/api/services/cjk_tokenizer_service.py

# 5. Docker 재빌드
docker-compose build --no-cache backend
```

---

## 9. Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| OSI 검색 정확도 | 0% (미검색) | 100% (상위 3위 이내) |
| index.json CJK 키워드 | 0개 | 500개 이상 |
| BM25 검색 응답 시간 | <50ms | <100ms (증가 허용) |
| E2E 테스트 통과율 | - | 100% |
| Hallucination 감소 | XSP/MSP 반환 | OSI 반환 |

---

## Appendix A: Example Keyword Extraction

**Before (English only):**
```json
{
  "file_name": "OF_OSI_7.2_Administrator-Guide_v3.1.2_jp.pdf",
  "keywords": ["ADMINSERVER", "ALPHA", "APPLCTN", "BOOTING", "CACHE"]
}
```

**After (CJK included):**
```json
{
  "file_name": "OF_OSI_7.2_Administrator-Guide_v3.1.2_jp.pdf",
  "keywords": ["OSI", "起動", "終了", "ログ", "システム", "運用", "ADMINSERVER"]
}
```

## Appendix B: Related Documents

- Plan: `docs/01-plan/features/cjk-keyword-extraction.plan.md`
- Archive: `docs/archive/2026-01/cjk-tokenization-improvement/`
- Current BM25: `app/api/services/summary_bm25_service.py`
- Structure Parser: `scripts/manual_processor/parsers/structure_parser.py`
