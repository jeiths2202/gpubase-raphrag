"""
Document Compare Service
다중 문서 비교 서비스

Compares multiple documents on a specific topic by:
1. Retrieving relevant sections from each document using vector search
2. Generating comparison summary using LLM
3. Identifying commonalities and differences
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional, AsyncGenerator
import json

from ..models.document import (
    DocumentCompareRequest,
    DocumentSection,
    DocumentCompareResult,
    ComparisonDifference,
    ComparisonSummary,
)
from ..core.config import api_settings

logger = logging.getLogger(__name__)


class DocumentCompareService:
    """
    Service for comparing multiple documents on a specific topic
    """

    def __init__(self, hybrid_rag, llm_adapter=None):
        """
        Initialize document compare service

        Args:
            hybrid_rag: HybridRAG instance for vector search
            llm_adapter: Optional LLM adapter for summary generation
        """
        self.hybrid_rag = hybrid_rag
        self.llm_adapter = llm_adapter
        self.max_sections_per_doc = getattr(api_settings, 'COMPARE_SECTIONS_PER_DOC', 3)
        self.max_documents = getattr(api_settings, 'COMPARE_MAX_DOCUMENTS', 5)
        self.summary_max_tokens = getattr(api_settings, 'COMPARE_SUMMARY_MAX_TOKENS', 500)

    async def _get_document_name(self, doc_id: str) -> str:
        """Get document name from database"""
        try:
            import asyncpg
            from ..core.config import api_settings

            dsn = (
                f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@"
                f"{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
            )
            conn = await asyncpg.connect(dsn)
            try:
                row = await conn.fetchrow(
                    "SELECT original_name FROM documents WHERE id = $1",
                    doc_id
                )
                return row["original_name"] if row else doc_id
            finally:
                await conn.close()
        except Exception as e:
            logger.warning(f"Failed to get document name for {doc_id}: {e}")
            return doc_id

    async def _search_document(
        self,
        doc_id: str,
        topic: str,
        top_k: int = 3
    ) -> List[DocumentSection]:
        """
        Search for relevant sections in a specific document

        Args:
            doc_id: Document ID to search in
            topic: Topic/query to search for
            top_k: Number of sections to retrieve

        Returns:
            List of relevant DocumentSection objects
        """
        sections = []

        try:
            # Use vector search with document filter
            results = await asyncio.to_thread(
                self.hybrid_rag.vector_search,
                topic,
                top_k=top_k,
                pdf_ids=[doc_id]  # Filter to specific document
            )

            for result in results:
                section = DocumentSection(
                    section_path=result.get("section_path"),
                    section_title=result.get("section_title") or result.get("title"),
                    content=result.get("content", ""),
                    page_number=result.get("page_number"),
                    score=result.get("score", 0.0),
                    chunk_id=result.get("chunk_id"),
                )
                sections.append(section)

        except Exception as e:
            logger.error(f"Error searching document {doc_id}: {e}")

        return sections

    def _get_language_prompts(self, language: str) -> Dict[str, str]:
        """Get language-specific prompts"""
        prompts = {
            "ko": {
                "system": "당신은 문서 분석 전문가입니다. 여러 문서를 비교하여 공통점과 차이점을 명확하게 정리해주세요.",
                "task": "다음 문서들을 '{topic}' 주제에 대해 비교 분석해주세요:",
                "summary_label": "요약",
                "commonalities_label": "공통점",
                "differences_label": "차이점",
            },
            "en": {
                "system": "You are a document analysis expert. Compare multiple documents and clearly identify commonalities and differences.",
                "task": "Please compare the following documents on the topic '{topic}':",
                "summary_label": "Summary",
                "commonalities_label": "Commonalities",
                "differences_label": "Differences",
            },
            "ja": {
                "system": "あなたは文書分析の専門家です。複数の文書を比較し、共通点と相違点を明確に整理してください。",
                "task": "以下の文書を'{topic}'というトピックについて比較分析してください:",
                "summary_label": "要約",
                "commonalities_label": "共通点",
                "differences_label": "相違点",
            },
        }
        return prompts.get(language, prompts["ko"])

    async def _generate_comparison_summary(
        self,
        topic: str,
        documents: List[DocumentCompareResult],
        language: str = "ko"
    ) -> tuple[str, List[str], List[ComparisonDifference]]:
        """
        Generate comparison summary using LLM

        Args:
            topic: Comparison topic
            documents: Document comparison results
            language: Response language

        Returns:
            Tuple of (summary, commonalities, differences)
        """
        if not self.llm_adapter:
            return "", [], []

        prompts = self._get_language_prompts(language)

        # Build document content for comparison
        doc_contents = []
        for doc in documents:
            if doc.relevant_sections:
                content_parts = [f"## {doc.doc_name}"]
                for section in doc.relevant_sections:
                    if section.section_title:
                        content_parts.append(f"### {section.section_title}")
                    content_parts.append(section.content[:1000])  # Truncate for prompt size
                doc_contents.append("\n".join(content_parts))

        if not doc_contents:
            return "", [], []

        # Build comparison prompt
        prompt = f"""{prompts['task'].format(topic=topic)}

{chr(10).join(doc_contents)}

다음 형식으로 JSON으로 응답해주세요:
{{
    "summary": "비교 요약 (2-3문장)",
    "commonalities": ["공통점1", "공통점2"],
    "differences": [
        {{"aspect": "관점1", "details": "문서별 차이점 설명"}}
    ]
}}
"""

        try:
            # Call LLM for comparison
            response = await self.llm_adapter.generate(
                prompt,
                system_prompt=prompts["system"],
                max_tokens=self.summary_max_tokens,
            )

            # Parse JSON response
            try:
                # Extract JSON from response
                json_match = response
                if "```json" in response:
                    json_match = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    json_match = response.split("```")[1].split("```")[0]

                result = json.loads(json_match.strip())

                summary = result.get("summary", "")
                commonalities = result.get("commonalities", [])
                differences_raw = result.get("differences", [])

                differences = []
                for diff in differences_raw:
                    if isinstance(diff, dict):
                        differences.append(ComparisonDifference(
                            aspect=diff.get("aspect", ""),
                            documents={"details": diff.get("details", "")}
                        ))

                return summary, commonalities, differences

            except json.JSONDecodeError:
                # Fallback: return raw response as summary
                return response[:500], [], []

        except Exception as e:
            logger.error(f"Error generating comparison summary: {e}")
            return "", [], []

    async def compare(
        self,
        request: DocumentCompareRequest
    ) -> ComparisonSummary:
        """
        Compare multiple documents on a specific topic

        Args:
            request: Document comparison request

        Returns:
            ComparisonSummary with results
        """
        # Validate document count
        doc_ids = request.document_ids[:self.max_documents]
        topic = request.topic
        language = request.language if request.language != "auto" else "ko"

        # Search each document for relevant sections
        doc_results = []
        for doc_id in doc_ids:
            doc_name = await self._get_document_name(doc_id)
            sections = await self._search_document(
                doc_id,
                topic,
                top_k=self.max_sections_per_doc
            )

            doc_result = DocumentCompareResult(
                doc_id=doc_id,
                doc_name=doc_name,
                relevant_sections=sections,
                has_content=len(sections) > 0
            )
            doc_results.append(doc_result)

        # Generate comparison summary
        summary, commonalities, differences = await self._generate_comparison_summary(
            topic,
            doc_results,
            language
        )

        return ComparisonSummary(
            topic=topic,
            documents=doc_results,
            summary=summary,
            commonalities=commonalities,
            differences=differences,
            language=language
        )

    async def stream_compare(
        self,
        request: DocumentCompareRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream document comparison results

        Args:
            request: Document comparison request

        Yields:
            Streaming chunks with comparison progress and results
        """
        doc_ids = request.document_ids[:self.max_documents]
        topic = request.topic
        language = request.language if request.language != "auto" else "ko"

        # Yield start event
        yield {
            "type": "compare_start",
            "data": {
                "topic": topic,
                "document_count": len(doc_ids)
            }
        }

        # Process each document
        doc_results = []
        for i, doc_id in enumerate(doc_ids):
            # Yield document processing start
            yield {
                "type": "document_start",
                "data": {
                    "index": i,
                    "doc_id": doc_id
                }
            }

            doc_name = await self._get_document_name(doc_id)
            sections = await self._search_document(
                doc_id,
                topic,
                top_k=self.max_sections_per_doc
            )

            doc_result = DocumentCompareResult(
                doc_id=doc_id,
                doc_name=doc_name,
                relevant_sections=sections,
                has_content=len(sections) > 0
            )
            doc_results.append(doc_result)

            # Yield document result
            yield {
                "type": "document_result",
                "data": {
                    "index": i,
                    "doc_id": doc_id,
                    "doc_name": doc_name,
                    "sections_count": len(sections),
                    "sections": [
                        {
                            "title": s.section_title,
                            "content": s.content[:300],  # Preview
                            "score": s.score
                        }
                        for s in sections[:3]
                    ]
                }
            }

        # Generate summary
        yield {"type": "summary_start", "data": {}}

        summary, commonalities, differences = await self._generate_comparison_summary(
            topic,
            doc_results,
            language
        )

        # Yield final result
        yield {
            "type": "compare_done",
            "data": {
                "summary": summary,
                "commonalities": commonalities,
                "differences": [
                    {"aspect": d.aspect, "documents": d.documents}
                    for d in differences
                ],
                "documents": [
                    {
                        "doc_id": d.doc_id,
                        "doc_name": d.doc_name,
                        "has_content": d.has_content,
                        "sections": [
                            {
                                "title": s.section_title,
                                "content": s.content,
                                "page_number": s.page_number,
                                "score": s.score
                            }
                            for s in d.relevant_sections
                        ]
                    }
                    for d in doc_results
                ]
            }
        }


# Singleton accessor
_compare_service: Optional[DocumentCompareService] = None


def get_document_compare_service(
    hybrid_rag=None,
    llm_adapter=None
) -> DocumentCompareService:
    """Get or create document compare service singleton"""
    global _compare_service
    if _compare_service is None:
        _compare_service = DocumentCompareService(hybrid_rag, llm_adapter)
    return _compare_service
