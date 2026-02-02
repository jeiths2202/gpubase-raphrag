"""
CJK Tokenizer Service

일본어/한국어/중국어 텍스트의 형태소 분석 및 키워드 추출 서비스.
fugashi(MeCab wrapper)를 사용하여 일본어 명사/동사를 추출합니다.

Usage:
    from app.api.services.cjk_tokenizer_service import get_cjk_tokenizer_service

    tokenizer = get_cjk_tokenizer_service()
    keywords = tokenizer.extract_all_keywords(text, title)
"""

import re
import logging
from typing import List, Optional, Set

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
    - fallback으로 연속 문자열 추출 사용
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
        '以下', '以上', '必要', '可能', '指定', '実行', '処理',
        '次', '前', '後', '間', '中', '上', '下', '表示',
    }

    # 한국어 불용어
    KO_STOPWORDS = {
        '것', '수', '등', '및', '또는', '그', '이', '저', '때문',
        '경우', '방법', '내용', '설명', '참조', '사용', '설정',
        '이하', '이상', '필요', '가능', '지정', '실행', '처리',
    }

    # 영문 불용어
    EN_STOPWORDS = {
        'THE', 'AND', 'FOR', 'NOT', 'ARE', 'ALL', 'WITH', 'THIS', 'THAT',
        'FROM', 'BUT', 'HAVE', 'HAS', 'HAD', 'WILL', 'CAN', 'MAY',
        'PDF', 'DOC', 'PAGE', 'CHAPTER', 'SECTION', 'TABLE', 'FIGURE',
    }

    def __init__(self, min_word_length: int = 2, max_keywords: int = 15):
        """
        Initialize CJK Tokenizer Service.

        Args:
            min_word_length: 최소 키워드 길이 (기본 2자)
            max_keywords: 추출할 최대 키워드 수 (기본 15개)
        """
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
                # 품사 확인 (feature 객체에서 pos1 추출)
                pos1 = ""
                if hasattr(word, 'feature') and hasattr(word.feature, 'pos1'):
                    pos1 = word.feature.pos1
                elif hasattr(word, 'pos'):
                    # Alternative: pos 속성 사용
                    pos1 = word.pos.split(',')[0] if word.pos else ""

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

                # 히라가나만 있는 경우 제외 (조사 등)
                if re.match(r'^[\u3040-\u309F]+$', surface):
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
        fugashi 미설치 시 fallback - 가타카나/한자 연속 문자열 추출

        히라가나만 있는 경우는 제외 (조사, 접속사 등)
        """
        keywords = {}

        # 가타카나 연속 문자열 (외래어, 기술용어)
        katakana_pattern = r'[\u30A0-\u30FF]{2,}'
        for match in re.findall(katakana_pattern, text):
            if match not in self.JA_STOPWORDS:
                keywords[match] = keywords.get(match, 0) + 1

        # 한자 연속 문자열 (명사, 동사 어간)
        kanji_pattern = r'[\u4E00-\u9FFF]{2,}'
        for match in re.findall(kanji_pattern, text):
            if match not in self.JA_STOPWORDS:
                keywords[match] = keywords.get(match, 0) + 1

        # 한자+히라가나 조합 (동사/형용사 포함)
        mixed_pattern = r'[\u4E00-\u9FFF]+[\u3040-\u309F]{1,2}'
        for match in re.findall(mixed_pattern, text):
            # 어간만 추출 (히라가나 제거)
            stem = re.sub(r'[\u3040-\u309F]+$', '', match)
            if len(stem) >= 2 and stem not in self.JA_STOPWORDS:
                keywords[stem] = keywords.get(stem, 0) + 1

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
            if len(match) < self.min_word_length:
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
            r'\b([A-Z]{2,}[A-Z0-9]*)\b',  # 대문자 약어 (OSI, VSAM, TJES)
            r'\b([a-z]+(?:init|boot|down|start|stop|mgr|ctl|cmd|run))\b',  # 명령어 패턴
            r'\b(tjes[a-z]*|osc[a-z]*|tac[a-z]*|hidb[a-z]*|ndb[a-z]*|osci[a-z]*)\b',  # OpenFrame 명령어
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                m_upper = m.upper()
                if len(m_upper) >= 2:
                    keywords[m_upper] = keywords.get(m_upper, 0) + 1

        # 불용어 제거
        for sw in self.EN_STOPWORDS:
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

        # 4. 추가 키워드 (빈도 높은 것 우선)
        remaining = self.max_keywords - len(all_keywords)
        if remaining > 0:
            additional = en_keywords[5:] + ja_keywords[5:] + ko_keywords[5:]
            all_keywords.update(additional[:remaining])

        # 5. 정렬 및 반환
        return sorted(list(all_keywords))[:self.max_keywords]

    def tokenize_for_search(self, text: str) -> List[str]:
        """
        검색용 토큰화 (BM25 쿼리 토크나이징)

        기존 summary_bm25_service._tokenize()와 호환되는 출력 생성

        Args:
            text: 검색 쿼리 또는 문서 텍스트

        Returns:
            토큰 리스트 (bi-gram 포함)
        """
        text = text.lower()
        tokens = []

        # 영문 토큰
        english_tokens = re.findall(r'[a-z0-9_\-\.]+', text)
        for token in english_tokens:
            tokens.append(token)
            # 하이픈/언더스코어로 분리된 부분도 추가
            parts = re.split(r'[-_\.]', token)
            tokens.extend([p for p in parts if p and len(p) > 1])

        # 일본어 토큰 (fugashi 사용 가능 시)
        tagger = _get_tagger()
        if tagger:
            try:
                for word in tagger(text):
                    if hasattr(word, 'surface'):
                        surface = word.surface
                        # 2자 이상만
                        if len(surface) >= 2:
                            tokens.append(surface)
            except Exception:
                pass

        # CJK 문자 bi-gram (fallback 및 보완)
        cjk_pattern = r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]+'
        for match in re.findall(cjk_pattern, text):
            tokens.append(match)
            # Bi-gram
            for i in range(len(match) - 1):
                tokens.append(match[i:i+2])
            # Tri-gram (긴 단어)
            if len(match) > 2:
                for i in range(len(match) - 2):
                    tokens.append(match[i:i+3])

        return list(set(tokens))


# Singleton instance
_cjk_tokenizer_service: Optional[CJKTokenizerService] = None


def get_cjk_tokenizer_service() -> CJKTokenizerService:
    """Get or create singleton CJKTokenizerService instance"""
    global _cjk_tokenizer_service
    if _cjk_tokenizer_service is None:
        _cjk_tokenizer_service = CJKTokenizerService()
    return _cjk_tokenizer_service
