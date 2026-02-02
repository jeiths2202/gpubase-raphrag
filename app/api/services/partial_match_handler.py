"""
PartialMatchHandler: 부분 일치 응답 처리

검색 결과가 질문에 완전히 답하지 못할 때 사용자에게 명확한 안내를 제공합니다.

Scenarios:
1. Exact match not found: 특정 config 파일 정보 없음
2. Intent mismatch: 구조 질문에 명령어 결과만 있음
3. Partial support: 일부 정보만 확인됨

Created as part of PDCA: rag-accuracy-improvement
"""

import logging
from typing import List, Optional

from ..models.rag_accuracy import (
    QueryAnalysis,
    GradedResult,
    RelevanceGrade,
    SupportLevel,
    QueryIntent,
)

logger = logging.getLogger(__name__)


class PartialMatchHandler:
    """부분 일치 응답 처리기"""

    # Response templates by language
    TEMPLATES = {
        "ja": {
            # Partial match scenarios
            "partial_intro": "「{query}」に関連する情報が見つかりましたが、完全な回答ではありません：",
            "found_instead": "以下の関連情報が見つかりました：",

            # Exact match scenarios
            "no_exact_match": "⚠️ 「{exact_term}」の正確な情報は見つかりませんでした。",
            "wrong_config": "⚠️ 「{expected}」ではなく「{found}」の情報が見つかりました。{expected}固有の情報は現在のドキュメントにない可能性があります。",

            # Intent mismatch scenarios
            "intent_mismatch_structure": "構造に関する情報は見つかりませんでしたが、関連するコマンドや使用方法の情報があります。",
            "intent_mismatch_command": "コマンドの情報は見つかりませんでしたが、概要や構造に関する情報があります。",
            "intent_mismatch_howto": "設定方法の詳細は見つかりませんでしたが、概要情報があります。",

            # Suggestions
            "suggestion": "💡 より具体的なキーワードで検索してみてください。",
            "related_topics": "📚 関連トピック：",
            "alternative_queries": "🔍 代替検索候補：",

            # No results
            "no_results": "申し訳ございませんが、「{query}」に関する情報が見つかりませんでした。",
        },
        "ko": {
            "partial_intro": "'{query}'와 관련된 정보를 찾았지만, 완전한 답변이 아닙니다:",
            "found_instead": "다음 관련 정보를 찾았습니다:",

            "no_exact_match": "⚠️ '{exact_term}'에 대한 정확한 정보를 찾지 못했습니다.",
            "wrong_config": "⚠️ '{expected}'가 아닌 '{found}'의 정보가 검색되었습니다. {expected} 관련 정보는 현재 문서에 없을 수 있습니다.",

            "intent_mismatch_structure": "구조에 관한 정보는 찾지 못했지만, 관련 명령어나 사용법 정보가 있습니다.",
            "intent_mismatch_command": "명령어 정보는 찾지 못했지만, 개요나 구조 정보가 있습니다.",
            "intent_mismatch_howto": "설정 방법의 상세 정보는 찾지 못했지만, 개요 정보가 있습니다.",

            "suggestion": "💡 더 구체적인 키워드로 검색해 보세요.",
            "related_topics": "📚 관련 토픽:",
            "alternative_queries": "🔍 대체 검색어:",

            "no_results": "죄송합니다. '{query}'에 관한 정보를 찾지 못했습니다.",
        },
        "en": {
            "partial_intro": "Found related information for '{query}', but not a complete answer:",
            "found_instead": "Found the following related information:",

            "no_exact_match": "⚠️ No exact information found for '{exact_term}'.",
            "wrong_config": "⚠️ Found information for '{found}' instead of '{expected}'. Information specific to {expected} may not be in the current documents.",

            "intent_mismatch_structure": "No structural information found, but related command and usage information is available.",
            "intent_mismatch_command": "No command information found, but overview and structural information is available.",
            "intent_mismatch_howto": "No detailed setup instructions found, but overview information is available.",

            "suggestion": "💡 Try searching with more specific keywords.",
            "related_topics": "📚 Related topics:",
            "alternative_queries": "🔍 Alternative search terms:",

            "no_results": "Sorry, no information found for '{query}'.",
        },
    }

    def build_partial_response(
        self,
        query_analysis: QueryAnalysis,
        graded_results: List[GradedResult],
        support_level: SupportLevel,
        alternative_queries: Optional[List[str]] = None,
    ) -> str:
        """
        부분 일치 응답 생성

        Args:
            query_analysis: 쿼리 분석 결과
            graded_results: 그레이딩된 검색 결과
            support_level: 충실도 검증 결과
            alternative_queries: 대안 쿼리 리스트 (선택)

        Returns:
            부분 일치 응답 문자열
        """
        lang = query_analysis.language
        templates = self.TEMPLATES.get(lang, self.TEMPLATES["en"])

        parts: List[str] = []

        # 1. Determine the scenario
        scenario = self._determine_scenario(query_analysis, graded_results, support_level)

        # 2. Build response based on scenario
        if scenario == "no_results":
            parts.append(templates["no_results"].format(query=query_analysis.original_query))

        elif scenario == "wrong_config":
            # Find what config was found instead
            found_config = self._find_wrong_config(query_analysis, graded_results)
            parts.append(templates["wrong_config"].format(
                expected=query_analysis.exact_match_value,
                found=found_config,
            ))

        elif scenario == "no_exact_match":
            parts.append(templates["no_exact_match"].format(
                exact_term=query_analysis.exact_match_value,
            ))
            # Add what was found instead
            self._add_found_instead(parts, templates, graded_results)

        elif scenario == "intent_mismatch":
            # Add intent-specific mismatch message
            intent_key = self._get_intent_mismatch_key(query_analysis.primary_intent)
            if intent_key in templates:
                parts.append(templates[intent_key])
            # Add what was found
            self._add_found_instead(parts, templates, graded_results)

        else:  # partial_support
            parts.append(templates["partial_intro"].format(
                query=query_analysis.original_query,
            ))
            self._add_found_instead(parts, templates, graded_results)

        # 3. Add related topics if available
        relevant_or_partial = [
            r for r in graded_results
            if r.grade in (RelevanceGrade.RELEVANT, RelevanceGrade.PARTIAL)
        ]
        if relevant_or_partial:
            parts.append("")
            parts.append(templates["related_topics"])
            for r in relevant_or_partial[:3]:
                doc_info = r.doc_name
                content_preview = r.content[:80].replace("\n", " ")
                parts.append(f"• {doc_info}: {content_preview}...")

        # 4. Add alternative queries if provided
        if alternative_queries:
            parts.append("")
            parts.append(templates["alternative_queries"])
            for alt in alternative_queries[:3]:
                parts.append(f"• {alt}")

        # 5. Add suggestion
        parts.append("")
        parts.append(templates["suggestion"])

        response = "\n".join(parts)
        logger.info(f"[PartialMatchHandler] Generated partial response ({scenario})")

        return response

    def _determine_scenario(
        self,
        query_analysis: QueryAnalysis,
        graded_results: List[GradedResult],
        support_level: SupportLevel,
    ) -> str:
        """시나리오 결정"""
        # No results at all
        if not graded_results:
            return "no_results"

        # All irrelevant
        if all(r.grade == RelevanceGrade.IRRELEVANT for r in graded_results):
            # Check if wrong config file was found
            if query_analysis.exact_match_value and self._is_config_file(query_analysis.exact_match_value):
                wrong_config = self._find_wrong_config(query_analysis, graded_results)
                if wrong_config:
                    return "wrong_config"
            return "no_results"

        # Exact match not found
        if query_analysis.exact_match_value:
            if not any(r.exact_match_found for r in graded_results):
                return "no_exact_match"

        # Intent mismatch
        if not any(r.intent_match for r in graded_results):
            return "intent_mismatch"

        # Default: partial support
        return "partial_support"

    def _is_config_file(self, value: str) -> bool:
        """config 파일인지 확인"""
        return value.lower().endswith('.conf')

    def _find_wrong_config(
        self,
        query_analysis: QueryAnalysis,
        graded_results: List[GradedResult],
    ) -> Optional[str]:
        """잘못된 config 파일 찾기"""
        expected = query_analysis.exact_match_value
        if not expected:
            return None

        import re
        for r in graded_results:
            # Find any .conf file mentioned in content
            matches = re.findall(r'\b\w+\.conf\b', r.content, re.IGNORECASE)
            for m in matches:
                if m.lower() != expected.lower():
                    return m

        return None

    def _get_intent_mismatch_key(self, intent: QueryIntent) -> str:
        """의도 불일치 템플릿 키 반환"""
        mapping = {
            QueryIntent.STRUCTURE: "intent_mismatch_structure",
            QueryIntent.COMMAND: "intent_mismatch_command",
            QueryIntent.HOWTO: "intent_mismatch_howto",
        }
        return mapping.get(intent, "intent_mismatch_structure")

    def _add_found_instead(
        self,
        parts: List[str],
        templates: dict,
        graded_results: List[GradedResult],
    ) -> None:
        """찾은 내용 추가"""
        relevant_or_partial = [
            r for r in graded_results
            if r.grade in (RelevanceGrade.RELEVANT, RelevanceGrade.PARTIAL)
        ]
        if relevant_or_partial:
            parts.append("")
            parts.append(templates["found_instead"])

    def build_clarification_response(
        self,
        query_analysis: QueryAnalysis,
        possible_intents: List[QueryIntent],
    ) -> str:
        """
        명확화 요청 응답 생성

        여러 의도가 감지되었을 때 사용자에게 명확화를 요청합니다.

        Args:
            query_analysis: 쿼리 분석 결과
            possible_intents: 가능한 의도 리스트

        Returns:
            명확화 요청 응답
        """
        lang = query_analysis.language

        clarification_templates = {
            "ja": "「{query}」について、どの情報をお探しですか？\n{options}",
            "ko": "'{query}'에 대해 어떤 정보를 찾으시나요?\n{options}",
            "en": "What information are you looking for about '{query}'?\n{options}",
        }

        intent_labels = {
            "ja": {
                QueryIntent.STRUCTURE: "構造・アーキテクチャ",
                QueryIntent.COMMAND: "コマンド・使用方法",
                QueryIntent.HOWTO: "設定方法・手順",
                QueryIntent.ERROR: "エラー・トラブルシューティング",
                QueryIntent.DEFINITION: "概要・定義",
            },
            "ko": {
                QueryIntent.STRUCTURE: "구조/아키텍처",
                QueryIntent.COMMAND: "명령어/사용법",
                QueryIntent.HOWTO: "설정 방법/순서",
                QueryIntent.ERROR: "에러/문제 해결",
                QueryIntent.DEFINITION: "개요/정의",
            },
            "en": {
                QueryIntent.STRUCTURE: "Structure/Architecture",
                QueryIntent.COMMAND: "Commands/Usage",
                QueryIntent.HOWTO: "Setup/Configuration",
                QueryIntent.ERROR: "Errors/Troubleshooting",
                QueryIntent.DEFINITION: "Overview/Definition",
            },
        }

        template = clarification_templates.get(lang, clarification_templates["en"])
        labels = intent_labels.get(lang, intent_labels["en"])

        options = "\n".join([
            f"• {labels.get(intent, intent.value)}"
            for intent in possible_intents
        ])

        return template.format(
            query=query_analysis.original_query,
            options=options,
        )


# =============================================================================
# Singleton Pattern
# =============================================================================

_partial_match_handler: Optional[PartialMatchHandler] = None


def get_partial_match_handler() -> PartialMatchHandler:
    """PartialMatchHandler 싱글톤 반환"""
    global _partial_match_handler
    if _partial_match_handler is None:
        _partial_match_handler = PartialMatchHandler()
    return _partial_match_handler
