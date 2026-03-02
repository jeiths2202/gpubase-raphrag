#!/usr/bin/env python3
"""
Q-A Relevance Checker
질문과 답변의 관련성을 검사하여 부적절한 Q&A 쌍을 필터링

검사 기준:
1. 키워드 오버랩 - 질문의 주요 키워드가 답변에 포함되는지
2. 보일러플레이트 패턴 - 반복되는 무의미한 답변 감지
3. 답변 다양성 - 동일한 답변이 여러 질문에 반복되는지
"""

import re
from typing import Tuple, Set
from collections import Counter


class QARelevanceChecker:
    """Q-A 관련성 검사기"""

    # 보일러플레이트 패턴 (무의미한 반복 답변)
    BOILERPLATE_PATTERNS = [
        # NDB 보일러플레이트
        r'以下は、STURNG RANGEにデータを作成するアプリケーションで使用されるPEDファイルの例です',
        r'以下は、TEARNG RANGEにデータを作成するアプリケーションで使用されるPEDファイルの例です',

        # 일반 보일러플레이트 (답변이 거의 없는 경우)
        r'^以下は.*の例です。?\s*$',
        r'^参照.*ください。?\s*$',
        r'^詳細は.*を参照.*$',
        r'^第\d+章.*を参照.*$',
    ]

    # 제외 키워드 (관련성 판단 시 제외)
    EXCLUDED_KEYWORDS = {
        'とは', 'について', 'ください', '説明', '教えて', 'やり方', '方法', '手順',
        'ステップ', '概念', '詳細', '使い方', '設定',
        'what', 'how', 'explain', 'describe', 'show', 'tell',
        '무엇', '어떻게', '설명', '알려', '방법'
    }

    def __init__(self):
        self.answer_frequency = Counter()  # 답변 빈도 추적

    def extract_keywords(self, text: str, min_length: int = 3) -> Set[str]:
        """텍스트에서 주요 키워드 추출"""
        # 알파벳 단어 추출 (3글자 이상)
        en_words = set(re.findall(r'\b[A-Z][A-Za-z]{2,}\b', text))

        # 일본어/한글 단어 추출 (카타카나, 한자, 한글)
        ja_words = set(re.findall(r'[\u30a0-\u30ff\u4e00-\u9fff]{3,}', text))
        ko_words = set(re.findall(r'[\uac00-\ud7a3]{2,}', text))

        # 합집합
        keywords = en_words | ja_words | ko_words

        # 제외 키워드 필터링
        keywords = {kw for kw in keywords if kw.lower() not in self.EXCLUDED_KEYWORDS}

        return keywords

    def is_boilerplate_answer(self, answer: str) -> bool:
        """보일러플레이트 답변인지 확인"""
        # 메타데이터 제거
        clean_answer = re.sub(r'\n\n\*\*製品.*$', '', answer, flags=re.DOTALL)
        clean_answer = re.sub(r'\n\n\*\*出典.*$', '', clean_answer, flags=re.DOTALL)
        clean_answer = clean_answer.strip()

        # 보일러플레이트 패턴 매칭
        for pattern in self.BOILERPLATE_PATTERNS:
            if re.search(pattern, clean_answer):
                # 답변 길이가 매우 짧으면 (< 100자) 보일러플레이트로 간주
                if len(clean_answer) < 100:
                    return True

        return False

    def calculate_keyword_overlap(self, question: str, answer: str) -> float:
        """질문과 답변의 키워드 오버랩 비율 계산"""
        q_keywords = self.extract_keywords(question)
        a_keywords = self.extract_keywords(answer)

        if not q_keywords:
            return 0.0

        # 오버랩 계산
        overlap = len(q_keywords & a_keywords)
        return overlap / len(q_keywords)

    def check_relevance(self, question: str, answer: str,
                       min_overlap: float = 0.2) -> Tuple[bool, str]:
        """
        Q-A 관련성 검사

        Returns:
            (is_relevant, reason) - 관련 있으면 (True, ""), 없으면 (False, "사유")
        """
        # 1. 보일러플레이트 체크
        if self.is_boilerplate_answer(answer):
            return False, "boilerplate_answer"

        # 2. 키워드 오버랩 체크
        overlap_ratio = self.calculate_keyword_overlap(question, answer)

        if overlap_ratio < min_overlap:
            # 질문에 고유명사/기술용어가 있는데 답변에 없으면 불일치
            q_keywords = self.extract_keywords(question)
            if q_keywords:  # 키워드가 있는데 오버랩이 없으면 문제
                return False, f"low_keyword_overlap ({overlap_ratio:.2f})"

        # 3. 답변 다양성 체크 (동일 답변이 너무 많이 반복되면 의심)
        self.answer_frequency[answer[:100]] += 1
        if self.answer_frequency[answer[:100]] > 5:
            # 동일 답변이 5번 이상 반복되면 보일러플레이트 의심
            return False, "repeated_answer"

        return True, ""

    def reset_frequency_counter(self):
        """빈도 카운터 초기화 (제품별 처리 시 사용)"""
        self.answer_frequency.clear()


def test_qa_relevance():
    """테스트 함수"""
    checker = QARelevanceChecker()

    # Test Case 1: 보일러플레이트 (NDB 문제)
    q1 = "階層型データベースと他の製品との違いは何ですか？"
    a1 = "以下は、STURNG RANGEにデータを作成するアプリケーションで使用されるPEDファイルの例です。\n\n**製品/Product**: OF_NDB"

    is_rel, reason = checker.check_relevance(q1, a1)
    print(f"Test 1 (Boilerplate): {is_rel} - {reason}")  # Expected: False, boilerplate_answer

    # Test Case 2: 관련 있는 Q&A
    q2 = "JEUSの起動方法を教えてください。"
    a2 = "JEUSサーバーを起動するには、startJeusコマンドを使用します。詳細な手順は以下の通りです..."

    is_rel, reason = checker.check_relevance(q2, a2)
    print(f"Test 2 (Relevant): {is_rel} - {reason}")  # Expected: True

    # Test Case 3: 키워드 오버랩 없음
    q3 = "Tiberoのバックアップ方法は？"
    a3 = "JEUSサーバーを起動するには、startJeusコマンドを使用します。"

    is_rel, reason = checker.check_relevance(q3, a3)
    print(f"Test 3 (No overlap): {is_rel} - {reason}")  # Expected: False, low_keyword_overlap


if __name__ == '__main__':
    test_qa_relevance()
