"""
Mindmap-specific Prompt Templates
Prompts for concept extraction and mindmap generation.
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .base import (
    PromptTemplate,
    MultiLanguagePromptTemplate,
    PromptMessage,
    PromptRole,
    Language
)


# ==================== Concept Extraction ====================

class ConceptExtractionPrompt(MultiLanguagePromptTemplate):
    """
    Prompt for extracting concepts from documents.

    Used to build mindmap structures from document content.
    """

    def __init__(self):
        super().__init__(
            name="concept_extraction",
            version="1.0",
            description="Extract concepts and relationships for mindmap"
        )

        self.register_template(
            Language.KOREAN,
            system_template="""당신은 문서에서 핵심 개념과 관계를 추출하는 전문가입니다.
개념을 계층적 구조로 정리하여 마인드맵 형식으로 출력합니다.""",
            user_template="""다음 문서에서 핵심 개념과 관계를 추출하여 마인드맵 구조로 만들어주세요.

문서 내용:
{content}

요구사항:
- 최대 깊이: {max_depth} 레벨
- 레벨당 최대 노드 수: {max_nodes}개
{focus_instruction}

다음 JSON 형식으로 응답하세요:
{{
    "central_concept": "핵심 주제",
    "concepts": [
        {{
            "id": "concept_1",
            "label": "개념 이름",
            "description": "간단한 설명",
            "level": 1,
            "parent_id": null,
            "children": ["concept_1_1", "concept_1_2"]
        }}
    ],
    "relationships": [
        {{
            "from": "concept_1",
            "to": "concept_2",
            "type": "관계 유형"
        }}
    ]
}}"""
        )

        self.register_template(
            Language.ENGLISH,
            system_template="""You are an expert at extracting key concepts and relationships from documents.
Organize concepts hierarchically in mindmap format.""",
            user_template="""Extract key concepts and relationships from the following document to create a mindmap structure.

Document content:
{content}

Requirements:
- Maximum depth: {max_depth} levels
- Maximum nodes per level: {max_nodes}
{focus_instruction}

Respond in the following JSON format:
{{
    "central_concept": "Main Topic",
    "concepts": [
        {{
            "id": "concept_1",
            "label": "Concept Name",
            "description": "Brief description",
            "level": 1,
            "parent_id": null,
            "children": ["concept_1_1", "concept_1_2"]
        }}
    ],
    "relationships": [
        {{
            "from": "concept_1",
            "to": "concept_2",
            "type": "relationship type"
        }}
    ]
}}"""
        )

    def get_required_params(self) -> List[str]:
        return ["content", "max_depth", "max_nodes"]

    def format(
        self,
        content: str,
        max_depth: int = 3,
        max_nodes: int = 5,
        focus_topics: Optional[List[str]] = None,
        language: str = "auto",
        **kwargs
    ) -> List[PromptMessage]:
        lang = Language(language) if language != "auto" else self.detect_language(content)
        templates = self.get_template(lang)

        # Build focus instruction
        focus_instruction = ""
        if focus_topics:
            if lang == Language.KOREAN:
                focus_instruction = f"- 특히 다음 주제에 집중하세요: {', '.join(focus_topics)}"
            else:
                focus_instruction = f"- Focus especially on: {', '.join(focus_topics)}"

        return [
            PromptMessage(PromptRole.SYSTEM, templates["system"]),
            PromptMessage(
                PromptRole.USER,
                templates["user"].format(
                    content=content[:8000],  # Truncate for context window
                    max_depth=max_depth,
                    max_nodes=max_nodes,
                    focus_instruction=focus_instruction
                )
            )
        ]


# ==================== Node Expansion ====================

class NodeExpansionPrompt(MultiLanguagePromptTemplate):
    """
    Prompt for expanding a mindmap node with sub-concepts.
    """

    def __init__(self):
        super().__init__(
            name="node_expansion",
            version="1.0",
            description="Expand mindmap node with sub-concepts"
        )

        self.register_template(
            Language.KOREAN,
            system_template="""당신은 개념 확장 전문가입니다.
주어진 개념에 대해 관련된 하위 개념과 세부 사항을 도출합니다.""",
            user_template="""다음 개념에 대한 하위 개념을 생성하세요.

상위 개념: {node_label}
설명: {node_description}

관련 컨텍스트:
{context}

다음 JSON 형식으로 {expansion_count}개의 하위 개념을 생성하세요:
{{
    "children": [
        {{
            "id": "child_1",
            "label": "하위 개념 이름",
            "description": "간단한 설명",
            "relevance": "상위 개념과의 관계"
        }}
    ]
}}"""
        )

        self.register_template(
            Language.ENGLISH,
            system_template="""You are a concept expansion expert.
Derive related sub-concepts and details for given concepts.""",
            user_template="""Generate sub-concepts for the following concept.

Parent concept: {node_label}
Description: {node_description}

Related context:
{context}

Generate {expansion_count} sub-concepts in the following JSON format:
{{
    "children": [
        {{
            "id": "child_1",
            "label": "Sub-concept name",
            "description": "Brief description",
            "relevance": "Relationship to parent concept"
        }}
    ]
}}"""
        )

    def get_required_params(self) -> List[str]:
        return ["node_label"]

    def format(
        self,
        node_label: str,
        node_description: str = "",
        context: str = "",
        expansion_count: int = 5,
        language: str = "auto",
        **kwargs
    ) -> List[PromptMessage]:
        lang = Language(language) if language != "auto" else self.detect_language(node_label)
        templates = self.get_template(lang)

        return [
            PromptMessage(PromptRole.SYSTEM, templates["system"]),
            PromptMessage(
                PromptRole.USER,
                templates["user"].format(
                    node_label=node_label,
                    node_description=node_description or "없음",
                    context=context or "없음",
                    expansion_count=expansion_count
                )
            )
        ]


# ==================== Node Query ====================

class NodeQueryPrompt(MultiLanguagePromptTemplate):
    """
    Prompt for answering questions about a specific mindmap node.
    """

    def __init__(self):
        super().__init__(
            name="node_query",
            version="1.0",
            description="Answer questions about mindmap node"
        )

        self.register_template(
            Language.KOREAN,
            system_template="""당신은 특정 개념에 대한 질문에 답변하는 전문가입니다.
컨텍스트를 바탕으로 개념과 관련된 정확한 정보를 제공합니다.""",
            user_template="""다음 개념에 대한 질문에 답변하세요.

개념: {node_label}
개념 설명: {node_description}

관련 문서 컨텍스트:
{context}

질문: {question}

답변:"""
        )

        self.register_template(
            Language.ENGLISH,
            system_template="""You are an expert at answering questions about specific concepts.
Provide accurate information about concepts based on context.""",
            user_template="""Answer the question about the following concept.

Concept: {node_label}
Description: {node_description}

Related document context:
{context}

Question: {question}

Answer:"""
        )

    def get_required_params(self) -> List[str]:
        return ["node_label", "question"]

    def format(
        self,
        node_label: str,
        question: str,
        node_description: str = "",
        context: str = "",
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
                    node_label=node_label,
                    node_description=node_description or "없음",
                    context=context or "관련 컨텍스트 없음",
                    question=question
                )
            )
        ]


# ==================== Relationship Extraction ====================

class RelationshipExtractionPrompt(PromptTemplate):
    """
    Prompt for extracting relationships between concepts.
    """

    def __init__(self):
        super().__init__(
            name="relationship_extraction",
            version="1.0",
            description="Extract relationships between concepts"
        )

        self._template = """Analyze the relationships between the following concepts in the document.

Document:
{content}

Concepts to analyze:
{concepts}

For each pair of related concepts, identify:
1. Relationship type (e.g., "is-a", "part-of", "causes", "relates-to")
2. Strength (strong, moderate, weak)
3. Direction (directional or bidirectional)

Respond in JSON format:
{{
    "relationships": [
        {{
            "from": "concept_a",
            "to": "concept_b",
            "type": "relationship_type",
            "strength": "strong|moderate|weak",
            "bidirectional": true|false,
            "description": "Brief explanation"
        }}
    ]
}}"""

    def get_required_params(self) -> List[str]:
        return ["content", "concepts"]

    def format(
        self,
        content: str,
        concepts: List[str],
        **kwargs
    ) -> List[PromptMessage]:
        concepts_str = "\n".join(f"- {c}" for c in concepts)

        return [
            PromptMessage(
                PromptRole.USER,
                self._template.format(
                    content=content[:6000],
                    concepts=concepts_str
                )
            )
        ]


# ==================== Prompt Collection ====================

class MindmapPrompts:
    """
    Collection of all mindmap prompts.
    """

    concept_extraction = ConceptExtractionPrompt()
    node_expansion = NodeExpansionPrompt()
    node_query = NodeQueryPrompt()
    relationship_extraction = RelationshipExtractionPrompt()

    @classmethod
    def register_all(cls, registry) -> None:
        """Register all mindmap prompts with a registry"""
        registry.register(cls.concept_extraction)
        registry.register(cls.node_expansion)
        registry.register(cls.node_query)
        registry.register(cls.relationship_extraction)
