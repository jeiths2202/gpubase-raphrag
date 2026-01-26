"""
RAG-specific Prompt Templates
Prompts for retrieval-augmented generation.
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .base import (
    PromptTemplate,
    MultiLanguagePromptTemplate,
    PromptMessage,
    PromptRole,
    PromptConfig,
    Language
)


# ==================== Answer Generation ====================

class AnswerGenerationPrompt(MultiLanguagePromptTemplate):
    """
    Prompt for generating answers from retrieved context.

    Supports:
    - Multiple languages (Korean, English, Japanese)
    - Different response styles (concise, detailed, technical)
    - Source attribution
    """

    def __init__(self):
        super().__init__(
            name="answer_generation",
            version="1.0",
            description="Generate answer from retrieved context",
            default_language=Language.KOREAN
        )

        # Korean template
        self.register_template(
            Language.KOREAN,
            system_template="""당신은 문서 기반 질의응답 전문가입니다.
주어진 컨텍스트를 바탕으로 정확하고 도움이 되는 답변을 제공하세요.

지침:
- 컨텍스트에 있는 정보만 사용하세요
- 불확실한 경우 명확히 밝히세요
- 답변은 명확하고 구조적으로 작성하세요
- 관련 소스를 참조하세요""",
            user_template="""다음 문서들을 참고하여 질문에 답변하세요.

컨텍스트:
{context}

질문: {question}

답변:"""
        )

        # English template
        self.register_template(
            Language.ENGLISH,
            system_template="""You are a document-based Q&A expert.
Provide accurate and helpful answers based on the given context.

Guidelines:
- Only use information from the context
- Clearly state when uncertain
- Structure your answer clearly
- Reference relevant sources""",
            user_template="""Answer the question based on the following documents.

Context:
{context}

Question: {question}

Answer:"""
        )

        # Japanese template
        self.register_template(
            Language.JAPANESE,
            system_template="""あなたは文書ベースのQ&A専門家です。
与えられたコンテキストに基づいて、正確で役立つ回答を提供してください。

ガイドライン:
- コンテキストの情報のみを使用
- 不確かな場合は明確に述べる
- 回答は明確に構成する
- 関連するソースを参照する""",
            user_template="""以下の文書を参考に質問に答えてください。

コンテキスト:
{context}

質問: {question}

回答:"""
        )

    def get_required_params(self) -> List[str]:
        return ["context", "question"]

    def format(
        self,
        context: str,
        question: str,
        language: str = "auto",
        **kwargs
    ) -> List[PromptMessage]:
        """Format the answer generation prompt"""
        # Detect or use specified language
        lang = Language(language) if language != "auto" else self.detect_language(question)
        templates = self.get_template(lang)

        return [
            PromptMessage(
                role=PromptRole.SYSTEM,
                content=templates["system"]
            ),
            PromptMessage(
                role=PromptRole.USER,
                content=templates["user"].format(
                    context=context,
                    question=question
                )
            )
        ]


class AnswerWithPriorityPrompt(MultiLanguagePromptTemplate):
    """
    Answer generation with session document priority.

    Used when session-specific documents should be prioritized.
    """

    def __init__(self):
        super().__init__(
            name="answer_with_priority",
            version="1.0",
            description="Generate answer with session document priority"
        )

        self.register_template(
            Language.KOREAN,
            system_template="""당신은 문서 기반 질의응답 전문가입니다.
세션 문서는 사용자가 현재 작업 중인 문서이므로 우선적으로 참조하세요.""",
            user_template="""다음 문서들을 참고하여 질문에 답변하세요.

세션 문서 (우선 참조):
{session_context}

일반 문서:
{general_context}

질문: {question}

세션 문서의 내용을 우선적으로 활용하여 답변하세요:"""
        )

        self.register_template(
            Language.ENGLISH,
            system_template="""You are a document-based Q&A expert.
Session documents are the user's current working documents, prioritize them.""",
            user_template="""Answer the question based on the following documents.

Session Documents (Priority):
{session_context}

General Documents:
{general_context}

Question: {question}

Prioritize session document content in your answer:"""
        )

    def get_required_params(self) -> List[str]:
        return ["session_context", "general_context", "question"]

    def format(
        self,
        session_context: str,
        general_context: str,
        question: str,
        language: str = "auto",
        **kwargs
    ) -> List[PromptMessage]:
        lang = Language(language) if language != "auto" else self.detect_language(question)
        templates = self.get_template(lang)

        return [
            PromptMessage(PromptRole.SYSTEM, templates["system"]),
            PromptMessage(
                PromptRole.USER,
                templates["user"].format(
                    session_context=session_context,
                    general_context=general_context,
                    question=question
                )
            )
        ]


# ==================== Query Classification ====================

class QueryClassificationPrompt(PromptTemplate):
    """
    Prompt for classifying query intent and selecting retrieval strategy.
    """

    def __init__(self):
        super().__init__(
            name="query_classification",
            version="1.0",
            description="Classify query for optimal retrieval strategy"
        )

        self._template = """Analyze the following query and classify it.

Query: {question}

Determine:
1. Query type: factual, analytical, comparative, procedural, code-related
2. Complexity: simple, moderate, complex
3. Best retrieval strategy: vector, keyword, hybrid, graph

Respond in JSON format:
{{
    "query_type": "<type>",
    "complexity": "<level>",
    "strategy": "<strategy>",
    "keywords": ["<key1>", "<key2>"],
    "requires_deep_analysis": <true/false>
}}"""

    def get_required_params(self) -> List[str]:
        return ["question"]

    def format(self, question: str, **kwargs) -> List[PromptMessage]:
        return [
            PromptMessage(
                PromptRole.USER,
                self._template.format(question=question)
            )
        ]


# ==================== Context Building ====================

class ContextBuildingPrompt(PromptTemplate):
    """
    Prompt for building context from multiple sources.
    """

    def __init__(self):
        super().__init__(
            name="context_building",
            version="1.0",
            description="Build context from retrieved documents"
        )

    def get_required_params(self) -> List[str]:
        return ["sources"]

    def format(
        self,
        sources: List[Dict[str, Any]],
        max_length: int = 8000,
        **kwargs
    ) -> List[PromptMessage]:
        """Format sources into context string"""
        context_parts = []
        current_length = 0

        for i, source in enumerate(sources, 1):
            content = source.get("content", "")
            doc_name = source.get("doc_name", f"Source {i}")
            score = source.get("score", 0)

            part = f"[{doc_name}] (relevance: {score:.2f})\n{content}"

            if current_length + len(part) > max_length:
                break

            context_parts.append(part)
            current_length += len(part)

        context = "\n\n---\n\n".join(context_parts)

        return [PromptMessage(PromptRole.USER, context)]


# ==================== Deep Analysis ====================

class DeepAnalysisPrompt(MultiLanguagePromptTemplate):
    """
    Prompt for deep analysis of complex queries.
    """

    def __init__(self):
        super().__init__(
            name="deep_analysis",
            version="1.0",
            description="Deep analysis for complex queries"
        )

        self.register_template(
            Language.KOREAN,
            system_template="""당신은 심층 분석 전문가입니다.
복잡한 질문에 대해 체계적이고 포괄적인 분석을 제공합니다.""",
            user_template="""다음 질문에 대해 심층 분석을 수행하세요.

컨텍스트:
{context}

질문: {question}

다음 구조로 분석하세요:
1. 핵심 개념 파악
2. 관련 요소 분석
3. 상호 관계 설명
4. 결론 및 시사점

분석:"""
        )

        self.register_template(
            Language.ENGLISH,
            system_template="""You are a deep analysis expert.
Provide systematic and comprehensive analysis for complex questions.""",
            user_template="""Perform deep analysis for the following question.

Context:
{context}

Question: {question}

Analyze with this structure:
1. Identify core concepts
2. Analyze related elements
3. Explain relationships
4. Conclusions and implications

Analysis:"""
        )

    def get_required_params(self) -> List[str]:
        return ["context", "question"]

    def format(
        self,
        context: str,
        question: str,
        language: str = "auto",
        **kwargs
    ) -> List[PromptMessage]:
        lang = Language(language) if language != "auto" else self.detect_language(question)
        templates = self.get_template(lang)

        return [
            PromptMessage(PromptRole.SYSTEM, templates["system"]),
            PromptMessage(
                PromptRole.USER,
                templates["user"].format(context=context, question=question)
            )
        ]


# ==================== Code Generation ====================

class CodeGenerationPrompt(PromptTemplate):
    """
    Prompt for code-related queries.
    """

    def __init__(self):
        super().__init__(
            name="code_generation",
            version="1.0",
            description="Handle code-related queries"
        )

        self._system = """You are an expert programmer and technical assistant.
Help users with code-related questions, providing clear explanations and working examples.

Guidelines:
- Provide working, tested code examples
- Explain the logic and approach
- Mention potential edge cases
- Follow best practices and conventions"""

        self._user = """Context from codebase:
{context}

User's request: {question}

Provide a helpful response with code if applicable:"""

    def get_required_params(self) -> List[str]:
        return ["context", "question"]

    def format(
        self,
        context: str,
        question: str,
        **kwargs
    ) -> List[PromptMessage]:
        return [
            PromptMessage(PromptRole.SYSTEM, self._system),
            PromptMessage(
                PromptRole.USER,
                self._user.format(context=context, question=question)
            )
        ]


# ==================== Prompt Collection ====================

class RAGPrompts:
    """
    Collection of all RAG prompts.

    Provides easy access to all RAG-related prompts
    and handles registration with the global registry.
    """

    answer_generation = AnswerGenerationPrompt()
    answer_with_priority = AnswerWithPriorityPrompt()
    query_classification = QueryClassificationPrompt()
    context_building = ContextBuildingPrompt()
    deep_analysis = DeepAnalysisPrompt()
    code_generation = CodeGenerationPrompt()

    @classmethod
    def register_all(cls, registry) -> None:
        """Register all RAG prompts with a registry"""
        registry.register(cls.answer_generation)
        registry.register(cls.answer_with_priority)
        registry.register(cls.query_classification)
        registry.register(cls.context_building)
        registry.register(cls.deep_analysis)
        registry.register(cls.code_generation)

    @classmethod
    def get_answer_prompt(
        cls,
        has_session_docs: bool = False
    ) -> PromptTemplate:
        """Get appropriate answer prompt"""
        if has_session_docs:
            return cls.answer_with_priority
        return cls.answer_generation
