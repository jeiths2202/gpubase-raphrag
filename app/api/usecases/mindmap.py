"""
Mindmap Use Cases
Business logic for mindmap generation and manipulation.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import time
import json
import re
import logging

from .base import UseCase, UseCaseResult, UseCaseContext
from ..ports import LLMPort, EmbeddingPort, VectorStorePort
from ..ports.llm_port import LLMMessage, LLMRole, LLMConfig
from ..repositories import DocumentRepository

logger = logging.getLogger(__name__)


# ==================== Input/Output DTOs ====================

@dataclass
class MindmapInput:
    """Input for mindmap generation"""
    document_id: str
    max_depth: int = 3
    max_nodes_per_level: int = 5
    language: str = "ko"
    focus_topics: Optional[List[str]] = None


@dataclass
class NodeExpansionInput:
    """Input for node expansion"""
    mindmap_id: str
    node_id: str
    expansion_depth: int = 1


@dataclass
class NodeQueryInput:
    """Input for querying a node"""
    mindmap_id: str
    node_id: str
    question: str


@dataclass
class MindmapNode:
    """Mindmap node structure"""
    id: str
    label: str
    description: str = ""
    level: int = 0
    parent_id: Optional[str] = None
    children: List["MindmapNode"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "level": self.level,
            "parent_id": self.parent_id,
            "children": [c.to_dict() for c in self.children],
            "metadata": self.metadata
        }


@dataclass
class MindmapOutput:
    """Output of mindmap generation"""
    mindmap_id: str
    document_id: str
    title: str
    root_node: MindmapNode
    total_nodes: int
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mindmap_id": self.mindmap_id,
            "document_id": self.document_id,
            "title": self.title,
            "root_node": self.root_node.to_dict(),
            "total_nodes": self.total_nodes,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class NodeExpansionOutput:
    """Output of node expansion"""
    node_id: str
    new_children: List[MindmapNode]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "new_children": [c.to_dict() for c in self.new_children]
        }


@dataclass
class NodeQueryOutput:
    """Output of node query"""
    node_id: str
    question: str
    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "question": self.question,
            "answer": self.answer,
            "sources": self.sources
        }


# ==================== Use Cases ====================

class GenerateMindmapUseCase(UseCase[MindmapInput, MindmapOutput]):
    """
    Generate mindmap from document.

    This use case:
    1. Fetches document content
    2. Extracts concepts using LLM
    3. Builds hierarchical mindmap structure
    4. Returns structured mindmap

    All external dependencies (LLM, Repository) are injected,
    making this fully testable with mocks.
    """

    def __init__(
        self,
        llm: LLMPort,
        document_repository: DocumentRepository
    ):
        self.llm = llm
        self.document_repo = document_repository

    async def execute(
        self,
        input: MindmapInput,
        context: UseCaseContext
    ) -> UseCaseResult[MindmapOutput]:
        """Execute mindmap generation"""
        start_time = time.time()

        try:
            # 1. Fetch document
            document = await self.document_repo.get_by_id(input.document_id)
            if not document:
                return UseCaseResult.not_found("Document", input.document_id)

            # 2. Extract concepts using LLM
            concepts = await self._extract_concepts(
                document.content,
                input.max_depth,
                input.max_nodes_per_level,
                input.language,
                input.focus_topics
            )

            if not concepts:
                return UseCaseResult.failure(
                    "Failed to extract concepts from document",
                    "CONCEPT_EXTRACTION_FAILED"
                )

            # 3. Build mindmap structure
            root_node = self._build_mindmap_tree(concepts, document.name)
            total_nodes = self._count_nodes(root_node)

            # 4. Create output
            import uuid
            output = MindmapOutput(
                mindmap_id=str(uuid.uuid4()),
                document_id=input.document_id,
                title=document.name,
                root_node=root_node,
                total_nodes=total_nodes
            )

            execution_time = int((time.time() - start_time) * 1000)
            result = UseCaseResult.success(output, execution_time)
            self._log_execution(input, context, result)

            return result

        except Exception as e:
            logger.exception(f"Mindmap generation failed: {e}")
            return UseCaseResult.failure(str(e), "GENERATION_FAILED")

    async def _extract_concepts(
        self,
        content: str,
        max_depth: int,
        max_nodes: int,
        language: str,
        focus_topics: Optional[List[str]]
    ) -> Optional[Dict[str, Any]]:
        """Extract concepts from content using LLM"""

        focus_instruction = ""
        if focus_topics:
            focus_instruction = f"\n특히 다음 주제에 집중하세요: {', '.join(focus_topics)}"

        prompt = f"""다음 문서에서 핵심 개념과 관계를 추출하여 마인드맵 구조로 만들어주세요.

문서 내용:
{content[:8000]}

요구사항:
- 최대 깊이: {max_depth} 레벨
- 레벨당 최대 노드 수: {max_nodes}개
- 언어: {language}
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
    ]
}}"""

        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content="You are a concept extraction expert. Extract key concepts and relationships from documents."),
            LLMMessage(role=LLMRole.USER, content=prompt)
        ]

        config = LLMConfig(temperature=0.3, max_tokens=4000)
        response = await self.llm.generate(messages, config)

        # Parse JSON from response
        try:
            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON")

        return None

    def _build_mindmap_tree(
        self,
        concepts: Dict[str, Any],
        title: str
    ) -> MindmapNode:
        """Build tree structure from extracted concepts"""

        # Create root node
        root = MindmapNode(
            id="root",
            label=concepts.get("central_concept", title),
            level=0
        )

        # Build concept index
        concept_list = concepts.get("concepts", [])
        concept_map = {c["id"]: c for c in concept_list}

        # Build tree
        def add_children(parent_node: MindmapNode):
            parent_concept = concept_map.get(parent_node.id)
            if not parent_concept:
                return

            child_ids = parent_concept.get("children", [])
            for child_id in child_ids:
                child_concept = concept_map.get(child_id)
                if child_concept:
                    child_node = MindmapNode(
                        id=child_id,
                        label=child_concept.get("label", ""),
                        description=child_concept.get("description", ""),
                        level=parent_node.level + 1,
                        parent_id=parent_node.id
                    )
                    parent_node.children.append(child_node)
                    add_children(child_node)

        # Add level 1 concepts to root
        for concept in concept_list:
            if concept.get("level") == 1:
                node = MindmapNode(
                    id=concept["id"],
                    label=concept.get("label", ""),
                    description=concept.get("description", ""),
                    level=1,
                    parent_id="root"
                )
                root.children.append(node)
                add_children(node)

        return root

    def _count_nodes(self, node: MindmapNode) -> int:
        """Count total nodes in tree"""
        count = 1
        for child in node.children:
            count += self._count_nodes(child)
        return count


class ExpandNodeUseCase(UseCase[NodeExpansionInput, NodeExpansionOutput]):
    """
    Expand a mindmap node with sub-concepts.

    Uses LLM to generate additional detail for a specific concept.
    """

    def __init__(
        self,
        llm: LLMPort,
        vector_store: VectorStorePort,
        embedding: EmbeddingPort
    ):
        self.llm = llm
        self.vector_store = vector_store
        self.embedding = embedding

    async def execute(
        self,
        input: NodeExpansionInput,
        context: UseCaseContext
    ) -> UseCaseResult[NodeExpansionOutput]:
        """Execute node expansion"""
        start_time = time.time()

        try:
            # TODO: Fetch node details from storage
            # For now, generate expansion based on node_id

            prompt = f"""노드 '{input.node_id}'에 대한 하위 개념을 {input.expansion_depth} 레벨 깊이로 생성하세요.

다음 JSON 형식으로 응답하세요:
{{
    "children": [
        {{
            "id": "child_1",
            "label": "하위 개념 1",
            "description": "설명"
        }}
    ]
}}"""

            messages = [
                LLMMessage(role=LLMRole.USER, content=prompt)
            ]

            response = await self.llm.generate(messages)

            # Parse response
            children = []
            try:
                json_match = re.search(r'\{[\s\S]*\}', response.content)
                if json_match:
                    data = json.loads(json_match.group())
                    for child_data in data.get("children", []):
                        children.append(MindmapNode(
                            id=child_data["id"],
                            label=child_data["label"],
                            description=child_data.get("description", ""),
                            parent_id=input.node_id
                        ))
            except json.JSONDecodeError:
                pass

            output = NodeExpansionOutput(
                node_id=input.node_id,
                new_children=children
            )

            execution_time = int((time.time() - start_time) * 1000)
            return UseCaseResult.success(output, execution_time)

        except Exception as e:
            logger.exception(f"Node expansion failed: {e}")
            return UseCaseResult.failure(str(e))


class QueryNodeUseCase(UseCase[NodeQueryInput, NodeQueryOutput]):
    """
    Answer questions about a specific mindmap node.

    Uses RAG to find relevant context and LLM to generate answer.
    """

    def __init__(
        self,
        llm: LLMPort,
        vector_store: VectorStorePort,
        embedding: EmbeddingPort
    ):
        self.llm = llm
        self.vector_store = vector_store
        self.embedding = embedding

    async def execute(
        self,
        input: NodeQueryInput,
        context: UseCaseContext
    ) -> UseCaseResult[NodeQueryOutput]:
        """Execute node query"""
        start_time = time.time()

        try:
            # 1. Generate query embedding
            query_embedding = await self.embedding.embed_query(input.question)

            # 2. Search for relevant context
            search_results = await self.vector_store.search(
                collection="documents",
                query_vector=query_embedding.embedding,
                top_k=5
            )

            # 3. Build context
            context_text = "\n".join([
                f"- {r.content}" for r in search_results if r.content
            ])

            # 4. Generate answer
            prompt = f"""다음 컨텍스트를 바탕으로 질문에 답변하세요.

컨텍스트:
{context_text}

질문: {input.question}

답변:"""

            messages = [
                LLMMessage(role=LLMRole.USER, content=prompt)
            ]

            response = await self.llm.generate(messages)

            output = NodeQueryOutput(
                node_id=input.node_id,
                question=input.question,
                answer=response.content,
                sources=[{"id": r.id, "score": r.score} for r in search_results]
            )

            execution_time = int((time.time() - start_time) * 1000)
            return UseCaseResult.success(output, execution_time)

        except Exception as e:
            logger.exception(f"Node query failed: {e}")
            return UseCaseResult.failure(str(e))
