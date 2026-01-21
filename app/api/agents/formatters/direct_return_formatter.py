"""
Direct Return Formatter
LLM 없이 검색 결과를 다국어로 포맷팅하여 할루시네이션을 완전히 제거합니다.

Usage:
    formatter = DirectReturnFormatter()

    # Direct 모드: LLM 없이 검색 결과만 반환
    result = formatter.format(search_results, language="ko", query="에러 코드 5212")

    # 하이브리드 모드 결정
    decision = formatter.decide_mode(search_results, query)
    if decision.use_direct:
        result = formatter.format(search_results, language="ko", query=query)
    else:
        # LLM synthesis 사용
        ...
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HybridModeDecision:
    """하이브리드 모드 결정 결과"""
    use_direct: bool
    reason: str
    confidence: float  # 검색 결과의 신뢰도 (0.0 ~ 1.0)
    top_score: float   # 최고 점수
    result_count: int  # 결과 수


class DirectReturnFormatter:
    """
    LLM 없이 검색 결과를 다국어로 포맷팅.

    Features:
    - 다국어 지원 (한국어, 영어, 일본어)
    - 쿼리 키워드 하이라이팅
    - 테이블/이미지 메타데이터 포함
    - 하이브리드 모드 결정 로직
    """

    # 다국어 템플릿
    TEMPLATES = {
        "ko": {
            "header": "## 검색 결과 ({count}건)\n",
            "no_results": "관련 문서를 찾지 못했습니다. 다른 키워드로 검색해 보세요.",
            "source": "출처",
            "page": "페이지",
            "section": "섹션",
            "content": "내용",
            "tables": "관련 테이블",
            "images": "관련 이미지",
            "score": "관련도",
            "error_match": "에러 코드 일치",
            "keyword_match": "키워드 일치",
            "see_more": "더 보기",
            "image_caption": "이미지",
            "table_caption": "테이블",
            "high_relevance": "높은 관련성",
            "from_document": "문서에서 발췌",
        },
        "en": {
            "header": "## Search Results ({count} found)\n",
            "no_results": "No relevant documents found. Try different keywords.",
            "source": "Source",
            "page": "Page",
            "section": "Section",
            "content": "Content",
            "tables": "Related Tables",
            "images": "Related Images",
            "score": "Relevance",
            "error_match": "Error Code Match",
            "keyword_match": "Keyword Match",
            "see_more": "See more",
            "image_caption": "Image",
            "table_caption": "Table",
            "high_relevance": "High Relevance",
            "from_document": "Excerpt from document",
        },
        "ja": {
            "header": "## 検索結果 ({count}件)\n",
            "no_results": "関連ドキュメントが見つかりませんでした。別のキーワードで検索してください。",
            "source": "出典",
            "page": "ページ",
            "section": "セクション",
            "content": "内容",
            "tables": "関連テーブル",
            "images": "関連画像",
            "score": "関連度",
            "error_match": "エラーコード一致",
            "keyword_match": "キーワード一致",
            "see_more": "もっと見る",
            "image_caption": "画像",
            "table_caption": "テーブル",
            "high_relevance": "高い関連性",
            "from_document": "ドキュメントからの抜粋",
        }
    }

    # 하이브리드 모드 임계값 (2026-01-21 조정: Direct 모드 더 적극적 사용)
    HYBRID_THRESHOLDS = {
        "min_score_for_direct": 0.015,    # Direct 모드 최소 RRF 점수 (낮춤: 0.025 → 0.015)
        "high_confidence_score": 0.025,   # 높은 신뢰도 점수 (낮춤: 0.030 → 0.025)
        "single_result_threshold": 0.020, # 단일 결과일 때 Direct 사용 임계값 (낮춤: 0.028 → 0.020)
        "error_code_boost": True,         # 에러 코드 매치 시 Direct 우선
        "max_results_for_direct": 5,      # Direct 모드 최대 결과 수 (증가: 3 → 5)
        "very_low_score": 0.008,          # 이 점수 미만이면 "정보 없음" 반환 (신규)
    }

    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        """
        Args:
            thresholds: 하이브리드 모드 임계값 오버라이드
        """
        if thresholds:
            self.HYBRID_THRESHOLDS.update(thresholds)

    def format(
        self,
        results: List[Dict[str, Any]],
        language: str = "ko",
        query: Optional[str] = None,
        include_score: bool = False,
        max_content_length: int = 1500,
        highlight_keywords: bool = True,
    ) -> str:
        """
        검색 결과를 다국어로 포맷팅.

        Args:
            results: unified_search에서 반환된 enriched_results
            language: 응답 언어 (ko, en, ja)
            query: 원본 쿼리 (하이라이팅용)
            include_score: 관련도 점수 표시 여부
            max_content_length: 내용 최대 길이
            highlight_keywords: 키워드 하이라이팅 여부

        Returns:
            포맷팅된 마크다운 문자열
        """
        t = self.TEMPLATES.get(language, self.TEMPLATES["ko"])

        if not results:
            return t["no_results"]

        # 쿼리에서 키워드 추출
        keywords = self._extract_keywords(query) if query and highlight_keywords else set()

        output_parts = []

        # 헤더
        output_parts.append(t["header"].format(count=len(results)))

        for i, result in enumerate(results, 1):
            source = result.get("source", {})
            content = result.get("content", "")
            chunk_type = result.get("chunk_type", "TEXT")
            rrf_score = result.get("rrf_score", 0)
            error_boosted = result.get("error_boosted", False)

            # 제목 구성
            doc_name = source.get("document_name", "Unknown")
            page_start = source.get("page_start")
            page_end = source.get("page_end")
            section_title = source.get("section_title") or result.get("title", "")

            # 페이지 표시
            if page_start:
                if page_start == page_end or not page_end:
                    page_display = f"{t['page']} {page_start}"
                else:
                    page_display = f"{t['page']} {page_start}-{page_end}"
            else:
                page_display = ""

            # 결과 헤더
            result_header = f"### {i}. "
            if section_title:
                result_header += f"{section_title}"
            else:
                result_header += f"{doc_name}"

            output_parts.append(result_header)

            # 메타 정보 라인
            meta_parts = []
            meta_parts.append(f"**{t['source']}**: {doc_name}")
            if page_display:
                meta_parts.append(f"**{page_display}**")

            if include_score:
                score_percent = f"{rrf_score * 100:.1f}%" if rrf_score < 1 else f"{rrf_score:.1%}"
                meta_parts.append(f"**{t['score']}**: {score_percent}")

            output_parts.append(" | ".join(meta_parts))

            # 에러 코드 매치 또는 높은 관련성 표시
            if error_boosted:
                output_parts.append(f"\n> **{t['error_match']}** - {t['high_relevance']}")
            elif rrf_score >= self.HYBRID_THRESHOLDS["high_confidence_score"]:
                output_parts.append(f"\n> **{t['high_relevance']}**")

            # 섹션 경로
            section_path = source.get("section_path")
            if section_path:
                output_parts.append(f"\n**{t['section']}**: {section_path}")

            # 내용 (하이라이팅 적용)
            output_parts.append(f"\n**{t['content']}**:\n")

            # 내용 처리
            formatted_content = self._format_content(
                content,
                keywords,
                max_content_length,
                highlight_keywords
            )
            output_parts.append(formatted_content)

            # 테이블
            tables = result.get("tables", [])
            if tables:
                output_parts.append(f"\n\n**{t['tables']}**:")
                for j, table in enumerate(tables[:3], 1):  # 최대 3개
                    table_md = table.get("markdown", "")
                    table_title = table.get("section_title", f"{t['table_caption']} {j}")
                    if table_md:
                        output_parts.append(f"\n*{table_title}*\n")
                        # 테이블에서도 하이라이팅
                        if keywords:
                            table_md = self._highlight_text(table_md, keywords)
                        output_parts.append(table_md)

            # 이미지
            images = result.get("images", [])
            if images:
                output_parts.append(f"\n\n**{t['images']}**:")
                for img in images[:5]:  # 최대 5개
                    img_url = img.get("url", "")
                    img_page = img.get("page_number", "?")
                    similarity = img.get("similarity", 0)

                    if img_url:
                        caption = f"{t['image_caption']} ({t['page']} {img_page}, {similarity:.0%})"
                        output_parts.append(f"\n![{caption}]({img_url})")

            output_parts.append("\n\n---\n")

        return "\n".join(output_parts)

    def format_compact(
        self,
        results: List[Dict[str, Any]],
        language: str = "ko",
        query: Optional[str] = None,
        max_results: int = 3,
    ) -> str:
        """
        컴팩트한 형식으로 포맷팅 (요약 버전).
        단일 결과나 높은 신뢰도 결과에 적합.

        Args:
            results: 검색 결과
            language: 응답 언어
            query: 원본 쿼리
            max_results: 최대 결과 수
        """
        t = self.TEMPLATES.get(language, self.TEMPLATES["ko"])

        if not results:
            return t["no_results"]

        keywords = self._extract_keywords(query) if query else set()
        results = results[:max_results]

        output_parts = []

        for result in results:
            source = result.get("source", {})
            content = result.get("content", "")
            doc_name = source.get("document_name", "Unknown")
            page_start = source.get("page_start", "?")
            section_title = source.get("section_title", "")

            # 내용 하이라이팅
            if keywords:
                content = self._highlight_text(content, keywords)

            # 컴팩트 포맷
            if section_title:
                output_parts.append(f"**{section_title}**\n")

            output_parts.append(content[:1000])

            if len(content) > 1000:
                output_parts.append("...")

            output_parts.append(f"\n\n> {t['from_document']}: {doc_name} ({t['page']} {page_start})\n")

            # 테이블 (있으면 포함)
            tables = result.get("tables", [])
            if tables and tables[0].get("markdown"):
                table_md = tables[0]["markdown"]
                if keywords:
                    table_md = self._highlight_text(table_md, keywords)
                output_parts.append(f"\n{table_md}\n")

        return "\n".join(output_parts)

    def decide_mode(
        self,
        results: List[Dict[str, Any]],
        query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> HybridModeDecision:
        """
        Direct 모드와 LLM 모드 중 선택.

        결정 기준:
        1. 에러 코드 쿼리 + 에러 코드 매치 결과 → Direct
        2. 높은 신뢰도 단일 결과 → Direct
        3. 결과가 없거나 낮은 점수 → LLM (fallback 메시지 생성)
        4. 복잡한 질문 (비교, 요약 등) → LLM

        Args:
            results: 검색 결과
            query: 사용자 쿼리
            context: 추가 컨텍스트 (의도 등)

        Returns:
            HybridModeDecision
        """
        if not results:
            return HybridModeDecision(
                use_direct=True,  # Changed: Direct 모드로 "정보 없음" 반환
                reason="no_results",
                confidence=0.0,
                top_score=0.0,
                result_count=0
            )

        top_score = results[0].get("rrf_score", 0) if results else 0
        result_count = len(results)

        # 에러 코드 쿼리 감지
        error_codes = self._extract_error_codes(query)
        has_error_match = any(r.get("error_boosted", False) for r in results)

        # 복잡한 질문 감지 (비교, 요약, 설명 요청 등)
        is_complex_query = self._is_complex_query(query)

        # ================================================================
        # Case 0: 매우 낮은 점수 → "정보 없음" 반환 (할루시네이션 방지)
        # LLM에게 맡기면 일반 지식으로 답변할 수 있으므로 Direct 모드로 강제
        # ================================================================
        if top_score < self.HYBRID_THRESHOLDS["very_low_score"]:
            logger.info(f"[HybridMode] Very low score ({top_score:.4f}) - forcing 'not found' response")
            return HybridModeDecision(
                use_direct=True,  # Direct 모드로 "정보 없음" 메시지 반환
                reason="very_low_score",
                confidence=0.0,
                top_score=top_score,
                result_count=result_count
            )

        # 결정 로직
        # Case 1: 에러 코드 쿼리 + 매치 결과
        if error_codes and has_error_match:
            return HybridModeDecision(
                use_direct=True,
                reason="error_code_match",
                confidence=min(top_score * 30, 1.0),  # 부스트된 신뢰도
                top_score=top_score,
                result_count=result_count
            )

        # Case 2: 복잡한 질문 + 적정 점수 → LLM 사용
        # 단, 점수가 낮으면 LLM 대신 Direct 모드 사용 (할루시네이션 방지)
        if is_complex_query:
            if top_score >= self.HYBRID_THRESHOLDS["min_score_for_direct"]:
                # 점수가 어느 정도 있으면 LLM 합성 허용
                return HybridModeDecision(
                    use_direct=False,
                    reason="complex_query",
                    confidence=top_score * 20,
                    top_score=top_score,
                    result_count=result_count
                )
            else:
                # 복잡한 질문이지만 점수가 낮으면 Direct 모드
                logger.info(f"[HybridMode] Complex query but low score ({top_score:.4f}) - using Direct mode")
                return HybridModeDecision(
                    use_direct=True,
                    reason="complex_query_low_score",
                    confidence=top_score * 20,
                    top_score=top_score,
                    result_count=result_count
                )

        # Case 3: 높은 신뢰도 결과 (단일 또는 소수)
        if top_score >= self.HYBRID_THRESHOLDS["high_confidence_score"]:
            if result_count <= self.HYBRID_THRESHOLDS["max_results_for_direct"]:
                return HybridModeDecision(
                    use_direct=True,
                    reason="high_confidence",
                    confidence=min(top_score * 25, 1.0),
                    top_score=top_score,
                    result_count=result_count
                )

        # Case 4: 단일 결과 + 적정 점수
        if result_count == 1 and top_score >= self.HYBRID_THRESHOLDS["single_result_threshold"]:
            return HybridModeDecision(
                use_direct=True,
                reason="single_high_match",
                confidence=min(top_score * 25, 1.0),
                top_score=top_score,
                result_count=result_count
            )

        # Case 5: 최소 점수 이상이면 Direct 가능
        if top_score >= self.HYBRID_THRESHOLDS["min_score_for_direct"]:
            return HybridModeDecision(
                use_direct=True,
                reason="adequate_score",
                confidence=top_score * 20,
                top_score=top_score,
                result_count=result_count
            )

        # Default: LLM 사용 (낮은 신뢰도)
        return HybridModeDecision(
            use_direct=False,
            reason="low_confidence",
            confidence=top_score * 20,
            top_score=top_score,
            result_count=result_count
        )

    def _extract_keywords(self, query: Optional[str]) -> Set[str]:
        """쿼리에서 하이라이팅할 키워드 추출"""
        if not query:
            return set()

        keywords = set()

        # 에러 코드 패턴
        error_patterns = [
            r'-?\d{4,5}',  # -5212, 12345
            r'[A-Z]+-\d+', # JEUS-1234, ORA-12154
            r'E\d{4}',     # E2001
        ]
        for pattern in error_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            keywords.update(matches)

        # 일반 키워드 (불용어 제외)
        stopwords = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'what', 'how', 'why', 'when', 'where', 'who', 'which',
            '은', '는', '이', '가', '을', '를', '의', '에', '에서', '로', '으로',
            '와', '과', '하다', '되다', '있다', '없다', '이다', '아니다',
            '무엇', '어떻게', '왜', '언제', '어디', '누구',
            'の', 'は', 'が', 'を', 'に', 'で', 'と', 'も', 'から', 'まで',
            '何', 'どう', 'なぜ', 'いつ', 'どこ', '誰',
        }

        # 단어 추출 (2글자 이상)
        words = re.findall(r'\b[\w가-힣ぁ-んァ-ン一-龥]+\b', query)
        for word in words:
            if len(word) >= 2 and word.lower() not in stopwords:
                keywords.add(word)

        return keywords

    def _extract_error_codes(self, query: str) -> List[str]:
        """쿼리에서 에러 코드 추출"""
        patterns = [
            r'-?\d{4,5}',           # -5212, 12345
            r'[A-Z]+-\d+',          # JEUS-1234
            r'ORA-\d+',             # Oracle errors
            r'SQL-?\d+',            # SQL errors
            r'ERR(?:OR)?-?\d+',     # Generic errors
            r'E\d{4}',              # E2001
        ]

        codes = []
        for pattern in patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            codes.extend(matches)

        return list(set(codes))

    def _is_complex_query(self, query: str) -> bool:
        """복잡한 질문인지 판단 (LLM이 필요한 경우)"""
        complex_patterns = [
            # 비교 요청
            r'비교|차이|다른\s*점|versus|vs\.?|compare|difference',
            # 요약 요청
            r'요약|정리|간략|summary|summarize|overview',
            # 설명 요청
            r'설명|알려|explain|describe|elaborate',
            # 추천/제안
            r'추천|제안|recommend|suggest|best\s*practice',
            # 장단점
            r'장점|단점|pros|cons|advantage|disadvantage',
            # 단계별 설명
            r'단계|순서|step|procedure|how\s*to',
            # 일본어 복잡 패턴
            r'比較|違い|説明|教えて|おすすめ|手順',
        ]

        query_lower = query.lower()
        for pattern in complex_patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True

        return False

    def _highlight_text(self, text: str, keywords: Set[str]) -> str:
        """텍스트에서 키워드 하이라이팅 (굵게)"""
        if not keywords or not text:
            return text

        result = text
        for keyword in keywords:
            if not keyword:
                continue
            # 대소문자 무시하고 치환, 마크다운 **bold** 사용
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            result = pattern.sub(f"**{keyword}**", result)

        # 중복 ** 제거 (****keyword**** → **keyword**)
        result = re.sub(r'\*{4,}', '**', result)

        return result

    def _format_content(
        self,
        content: str,
        keywords: Set[str],
        max_length: int,
        highlight: bool
    ) -> str:
        """내용 포맷팅 (길이 제한 + 하이라이팅)"""
        if not content:
            return ""

        # 길이 제한
        if len(content) > max_length:
            # 문장 경계에서 자르기
            truncated = content[:max_length]
            last_period = max(
                truncated.rfind('. '),
                truncated.rfind('。'),
                truncated.rfind('\n\n'),
            )
            if last_period > max_length * 0.7:
                truncated = content[:last_period + 1]
            content = truncated + "..."

        # 하이라이팅
        if highlight and keywords:
            content = self._highlight_text(content, keywords)

        return content

    def get_mode_explanation(self, decision: HybridModeDecision, language: str = "ko") -> str:
        """결정 이유를 사용자 친화적으로 설명"""
        explanations = {
            "ko": {
                "error_code_match": "에러 코드와 정확히 일치하는 문서를 찾았습니다.",
                "high_confidence": "높은 관련성의 검색 결과를 찾았습니다.",
                "single_high_match": "정확히 일치하는 단일 결과를 찾았습니다.",
                "adequate_score": "관련 문서를 찾았습니다.",
                "complex_query": "복잡한 질문으로 AI 분석이 필요합니다.",
                "low_confidence": "관련 결과가 부족하여 AI 분석이 필요합니다.",
                "no_results": "관련 문서를 찾지 못했습니다.",
            },
            "en": {
                "error_code_match": "Found exact match for the error code.",
                "high_confidence": "Found highly relevant search results.",
                "single_high_match": "Found a single exact match.",
                "adequate_score": "Found relevant documents.",
                "complex_query": "Complex query requires AI analysis.",
                "low_confidence": "Insufficient results, AI analysis needed.",
                "no_results": "No relevant documents found.",
            },
            "ja": {
                "error_code_match": "エラーコードに正確に一致するドキュメントが見つかりました。",
                "high_confidence": "関連性の高い検索結果が見つかりました。",
                "single_high_match": "正確に一致する単一の結果が見つかりました。",
                "adequate_score": "関連ドキュメントが見つかりました。",
                "complex_query": "複雑な質問のためAI分析が必要です。",
                "low_confidence": "結果が不十分なためAI分析が必要です。",
                "no_results": "関連ドキュメントが見つかりませんでした。",
            }
        }

        lang_exp = explanations.get(language, explanations["en"])
        return lang_exp.get(decision.reason, decision.reason)
