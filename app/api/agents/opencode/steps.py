"""
OpenCode 5-Step Mandatory Workflow

Implements the 5-step pipeline from the specification:
1. Keyword Extraction - Extract ALL keywords from user query
2. Summary Search - Search summary documents for each keyword
3. PDF Page Verification - Verify original PDF sources at page level
4. Tool Selection - Select appropriate tool (Vision/vLLM/Embedding)
5. Answer Generation - Generate answer with source citations
"""

import re
import time
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from abc import ABC, abstractmethod

from .types import (
    OpenCodeContext,
    StepResult,
    StepStatus,
    ExtractedKeywords,
    SummarySearchResult,
    PDFVerificationResult,
    ToolSelectionResult,
    ToolType,
)

logger = logging.getLogger(__name__)


class PipelineStep(ABC):
    """Abstract base class for pipeline steps"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Step identifier"""
        pass

    @property
    @abstractmethod
    def step_number(self) -> int:
        """Step number (1-5)"""
        pass

    @property
    def display_names(self) -> Dict[str, str]:
        """Localized display names"""
        return {
            "en": self.name,
            "ko": self.name,
            "ja": self.name,
        }

    @abstractmethod
    async def execute(self, context: OpenCodeContext) -> StepResult:
        """Execute the step"""
        pass


class KeywordExtractionStep(PipelineStep):
    """Step 1: Extract ALL keywords from user query"""

    name = "keyword_extraction"
    step_number = 1

    display_names = {
        "en": "Keyword Extraction",
        "ko": "키워드 추출",
        "ja": "キーワード抽出",
    }

    # OpenFrame product patterns
    PRODUCT_PATTERNS = [
        r"\b(TJES|TACF|OSC|OSI|HiDB|NDB|Tibero|Tmax|WebT|OFManager|OFCOBOL|OpenFrame)\b",
    ]

    # Error code patterns
    ERROR_CODE_PATTERNS = [
        r"-?\d{4,5}",  # -5212, 21000, etc.
        r"[A-Z]{2,4}-\d{3,5}",  # ABC-1234
    ]

    # Command patterns (OpenFrame commands)
    COMMAND_PATTERNS = [
        r"\b(tjesmgr|oscmgr|tacfmgr|osimgr|ndbmgr|hidbmgr|volmgr|catmgr)\b",
        r"\b(tmboot|tmdown|ofboot|ofdown|jesinit|jesdown)\b",
        r"\b(idcams|iebgener|iebcopy|dfsort|dsmigin|dsmigout)\b",
    ]

    async def execute(self, context: OpenCodeContext) -> StepResult:
        """Extract keywords from query"""
        start_time = time.time()

        try:
            query = context.query
            keywords = ExtractedKeywords()

            # Detect language
            keywords.language = self._detect_language(query)

            # Extract error codes
            for pattern in self.ERROR_CODE_PATTERNS:
                matches = re.findall(pattern, query)
                keywords.error_codes.extend(matches)

            # Extract product keywords
            for pattern in self.PRODUCT_PATTERNS:
                matches = re.findall(pattern, query, re.IGNORECASE)
                keywords.product_keywords.extend([m.upper() for m in matches])

            # Extract command names
            for pattern in self.COMMAND_PATTERNS:
                matches = re.findall(pattern, query, re.IGNORECASE)
                keywords.command_names.extend([m.lower() for m in matches])

            # Extract primary keywords (nouns, technical terms)
            primary = self._extract_primary_keywords(query, keywords.language)
            keywords.primary_keywords = primary

            # Extract secondary keywords (related terms)
            secondary = self._extract_secondary_keywords(query, keywords.language)
            keywords.secondary_keywords = secondary

            # Remove duplicates while preserving order
            keywords.primary_keywords = list(dict.fromkeys(keywords.primary_keywords))
            keywords.product_keywords = list(dict.fromkeys(keywords.product_keywords))
            keywords.error_codes = list(dict.fromkeys(keywords.error_codes))
            keywords.command_names = list(dict.fromkeys(keywords.command_names))

            # Limit total keywords
            max_kw = context.config.max_keywords
            all_kw = keywords.all_keywords()
            if len(all_kw) > max_kw:
                # Prioritize: error_codes > commands > products > primary > secondary
                keywords.secondary_keywords = keywords.secondary_keywords[:max(0, max_kw - len(all_kw) + len(keywords.secondary_keywords))]

            context.keywords = keywords

            latency = (time.time() - start_time) * 1000
            logger.info(f"[OpenCode] Step 1 completed: {len(keywords.all_keywords())} keywords extracted")

            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.COMPLETED,
                output=keywords,
                latency_ms=latency,
                metadata={
                    "keyword_count": len(keywords.all_keywords()),
                    "keywords": keywords.to_dict(),
                },
            )

        except Exception as e:
            logger.error(f"[OpenCode] Step 1 failed: {e}")
            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.FAILED,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    def _detect_language(self, text: str) -> str:
        """Detect query language"""
        # Korean characters
        if re.search(r'[\uAC00-\uD7AF]', text):
            return "ko"
        # Japanese characters (Hiragana, Katakana, Kanji)
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text):
            return "ja"
        return "en"

    def _extract_primary_keywords(self, query: str, language: str) -> List[str]:
        """Extract primary keywords (nouns, technical terms)"""
        keywords = []

        # Extract quoted terms
        quoted = re.findall(r'"([^"]+)"', query)
        keywords.extend(quoted)

        # Extract capitalized terms (likely proper nouns or acronyms)
        caps = re.findall(r'\b[A-Z][A-Za-z0-9]{2,}\b', query)
        keywords.extend(caps)

        # For Korean/Japanese, extract nouns using patterns
        if language == "ko":
            # Korean noun patterns (ending with 은/는/이/가/을/를/에/의)
            patterns = re.findall(r'([가-힣]+)(?:은|는|이|가|을|를|에|의|로|와|과|에서)', query)
            keywords.extend(patterns)
        elif language == "ja":
            # Japanese noun patterns (katakana words, kanji compounds)
            katakana = re.findall(r'[ァ-ヶー]{2,}', query)
            keywords.extend(katakana)

        # Extract technical terms (alphanumeric with underscores/hyphens)
        technical = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', query)
        keywords.extend([t for t in technical if len(t) > 2 and t.lower() not in self._get_stopwords()])

        return list(dict.fromkeys(keywords))[:10]

    def _extract_secondary_keywords(self, query: str, language: str) -> List[str]:
        """Extract secondary/related keywords"""
        # Simple extraction of remaining meaningful words
        words = re.findall(r'\b\w{3,}\b', query)
        stopwords = self._get_stopwords()
        return [w for w in words if w.lower() not in stopwords][:5]

    def _get_stopwords(self) -> set:
        """Get stopwords for all languages"""
        return {
            # English
            "the", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "can", "about", "what",
            "how", "why", "when", "where", "which", "who", "this", "that",
            "these", "those", "please", "help", "tell", "explain", "show",
            # Korean
            "을", "를", "이", "가", "은", "는", "에", "의", "로", "와", "과",
            "뭐", "무엇", "어떻게", "왜", "언제", "어디", "누구", "이것", "저것",
            # Japanese
            "は", "が", "を", "に", "で", "と", "の", "から", "まで", "より",
            "何", "どう", "なぜ", "いつ", "どこ", "誰", "これ", "それ", "あれ",
        }


class SummarySearchStep(PipelineStep):
    """Step 2: Search summary documents for each keyword"""

    name = "summary_search"
    step_number = 2

    display_names = {
        "en": "Summary Document Search",
        "ko": "요약 문서 검색",
        "ja": "要約ドキュメント検索",
    }

    async def execute(self, context: OpenCodeContext) -> StepResult:
        """Search summary documents for all keywords"""
        start_time = time.time()

        if not context.keywords:
            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.FAILED,
                error="No keywords available from Step 1",
                latency_ms=(time.time() - start_time) * 1000,
            )

        try:
            from ...services.summary_search_service import get_summary_search_service
            summary_service = get_summary_search_service()

            results = []

            # Search for each keyword type
            for error_code in context.keywords.error_codes:
                result = SummarySearchResult(keyword=error_code)
                error_info = await summary_service.search_error_code(error_code)
                if error_info:
                    result.error_context = self._format_error_context(error_info)
                    result.matched_documents.append({
                        "type": "error_code",
                        "file": error_info.get("source_file"),
                        "content": error_info,
                    })
                results.append(result)

            for cmd in context.keywords.command_names:
                result = SummarySearchResult(keyword=cmd)
                cmd_info = await summary_service.search_command(cmd)
                if cmd_info:
                    result.command_context = self._format_command_context(cmd_info)
                    result.matched_documents.append({
                        "type": "command",
                        "file": cmd_info.get("source_file"),
                        "content": cmd_info,
                    })
                results.append(result)

            for term in context.keywords.product_keywords + context.keywords.primary_keywords[:3]:
                result = SummarySearchResult(keyword=term)
                term_info = await summary_service.search_glossary(term)
                if term_info:
                    result.term_context = self._format_term_context(term_info)
                    result.matched_documents.append({
                        "type": "glossary",
                        "file": term_info.get("source_file"),
                        "content": term_info,
                    })
                results.append(result)

            context.summary_searches = results

            # Count successful searches
            successful = sum(1 for r in results if r.matched_documents)
            total = len(results)

            latency = (time.time() - start_time) * 1000
            logger.info(f"[OpenCode] Step 2 completed: {successful}/{total} keywords found in summaries")

            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.COMPLETED,
                output=results,
                latency_ms=latency,
                metadata={
                    "total_searches": total,
                    "successful_searches": successful,
                    "keywords_searched": [r.keyword for r in results],
                },
            )

        except Exception as e:
            logger.error(f"[OpenCode] Step 2 failed: {e}")
            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.FAILED,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    def _format_error_context(self, error_info: Dict) -> str:
        """Format error info for context"""
        return (
            f"에러코드 {error_info.get('code')} ({error_info.get('module')}/{error_info.get('name')}):\n"
            f"  설명: {error_info.get('description', 'N/A')}\n"
            f"  대처: {error_info.get('solution', 'N/A')}"
        )

    def _format_command_context(self, cmd_info: Dict) -> str:
        """Format command info for context"""
        products = ", ".join(cmd_info.get("products", []))
        return (
            f"명령어 {cmd_info.get('command')}:\n"
            f"  지원 제품: {products}\n"
            f"  설명: {cmd_info.get('description', 'N/A')}\n"
            f"  구문: {cmd_info.get('syntax', 'N/A')}"
        )

    def _format_term_context(self, term_info: Dict) -> str:
        """Format term info for context"""
        return (
            f"{term_info.get('term')} ({term_info.get('full_name', '')}):\n"
            f"  설명: {term_info.get('description', 'N/A')}\n"
            f"  제품: {term_info.get('product', 'N/A')}"
        )


class PDFVerificationStep(PipelineStep):
    """Step 3: Verify original PDF sources at page level"""

    name = "pdf_verification"
    step_number = 3

    display_names = {
        "en": "PDF Page Verification",
        "ko": "PDF 페이지 검증",
        "ja": "PDFページ検証",
    }

    async def execute(self, context: OpenCodeContext) -> StepResult:
        """Verify PDF sources and extract page-level content"""
        start_time = time.time()

        try:
            # Use vector search to find relevant PDF chunks
            from ...core.deps import get_rag_service
            rag_service = get_rag_service()

            # Search using vector strategy to get source chunks
            result = await rag_service.query(
                question=context.query,
                strategy="vector",
                language=context.language,
                top_k=context.config.max_documents * 2,
            )

            # Extract sources from the query result
            search_results = result.get("sources", [])

            if not search_results:
                logger.warning("[OpenCode] Step 3: No PDF chunks found in vector search")
                return StepResult(
                    step_name=self.name,
                    step_number=self.step_number,
                    status=StepStatus.COMPLETED,
                    output=[],
                    latency_ms=(time.time() - start_time) * 1000,
                    metadata={"verified_count": 0, "no_results": True},
                )

            # Group results by document
            doc_chunks: Dict[str, List[Dict]] = {}
            for result in search_results:
                doc_name = result.get("document_name") or result.get("source", "Unknown")
                if doc_name not in doc_chunks:
                    doc_chunks[doc_name] = []
                doc_chunks[doc_name].append(result)

            # Verify top documents (limit by config)
            verifications = []
            for doc_name in list(doc_chunks.keys())[:context.config.max_documents]:
                chunks = doc_chunks[doc_name][:context.config.max_pages_per_doc]

                # Extract page numbers
                pages = set()
                for chunk in chunks:
                    page = chunk.get("page_number") or chunk.get("page")
                    if page:
                        pages.add(int(page))

                # Detect visual content
                has_visual = any(
                    chunk.get("has_image") or
                    chunk.get("has_table") or
                    chunk.get("content_type") in ["image", "table", "chart"]
                    for chunk in chunks
                )

                visual_elements = [
                    {"type": chunk.get("content_type"), "page": chunk.get("page_number")}
                    for chunk in chunks
                    if chunk.get("content_type") in ["image", "table", "chart", "diagram"]
                ]

                verification = PDFVerificationResult(
                    document_name=doc_name,
                    page_numbers=sorted(pages),
                    verified_chunks=chunks,
                    has_visual_content=has_visual,
                    visual_elements=visual_elements,
                    content_types=list(set(c.get("content_type", "text") for c in chunks)),
                )
                verifications.append(verification)

            context.pdf_verifications = verifications

            total_pages = sum(len(v.page_numbers) for v in verifications)
            visual_count = sum(1 for v in verifications if v.has_visual_content)

            latency = (time.time() - start_time) * 1000
            logger.info(f"[OpenCode] Step 3 completed: {len(verifications)} docs, {total_pages} pages, {visual_count} with visual content")

            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.COMPLETED,
                output=verifications,
                latency_ms=latency,
                metadata={
                    "verified_docs": len(verifications),
                    "total_pages": total_pages,
                    "visual_content_count": visual_count,
                    "documents": [v.document_name for v in verifications],
                },
            )

        except Exception as e:
            logger.error(f"[OpenCode] Step 3 failed: {e}")
            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.FAILED,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )


class ToolSelectionStep(PipelineStep):
    """Step 4: Select appropriate tool based on content type"""

    name = "tool_selection"
    step_number = 4

    display_names = {
        "en": "Tool Selection",
        "ko": "도구 선택",
        "ja": "ツール選択",
    }

    async def execute(self, context: OpenCodeContext) -> StepResult:
        """Select tools based on content analysis"""
        start_time = time.time()

        try:
            selected_tools = []
            reasoning_parts = []

            # Check for visual content
            has_visual = any(
                pdf.has_visual_content for pdf in context.pdf_verifications
            )

            if has_visual:
                selected_tools.append(ToolType.VISION)
                reasoning_parts.append("Visual content detected (images/tables/charts) - using Vision LLM")
            else:
                reasoning_parts.append("No visual content - skipping Vision LLM")

            # Always include vLLM for text generation
            selected_tools.append(ToolType.VLLM)
            reasoning_parts.append("Text generation required - using vLLM")

            # Include Embedding if we need more context
            if len(context.pdf_verifications) == 0:
                selected_tools.append(ToolType.EMBEDDING)
                reasoning_parts.append("No direct PDF matches - using Embedding search for semantic retrieval")

            # Estimate tokens based on content
            total_content_length = sum(
                len(chunk.get("content", ""))
                for pdf in context.pdf_verifications
                for chunk in pdf.verified_chunks
            )
            estimated_tokens = total_content_length // 4  # Rough estimate

            result = ToolSelectionResult(
                selected_tools=selected_tools,
                reasoning=" | ".join(reasoning_parts),
                vision_required=has_visual,
                estimated_tokens=estimated_tokens,
            )

            context.tool_selection = result

            latency = (time.time() - start_time) * 1000
            logger.info(f"[OpenCode] Step 4 completed: Selected tools: {[t.value for t in selected_tools]}")

            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.COMPLETED,
                output=result,
                latency_ms=latency,
                metadata={
                    "tools": [t.value for t in selected_tools],
                    "vision_required": has_visual,
                    "estimated_tokens": estimated_tokens,
                },
            )

        except Exception as e:
            logger.error(f"[OpenCode] Step 4 failed: {e}")
            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.FAILED,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )


class AnswerGenerationStep(PipelineStep):
    """Step 5: Generate answer with source citations"""

    name = "answer_generation"
    step_number = 5

    display_names = {
        "en": "Answer Generation",
        "ko": "답변 생성",
        "ja": "回答生成",
    }

    async def execute(self, context: OpenCodeContext) -> StepResult:
        """Generate answer using selected tools"""
        start_time = time.time()

        try:
            # Build context from verified sources
            source_context = self._build_source_context(context)

            if not source_context.strip():
                # No sources found - return blocked answer
                return StepResult(
                    step_name=self.name,
                    step_number=self.step_number,
                    status=StepStatus.COMPLETED,
                    output={
                        "answer": self._get_no_results_message(context.keywords.language if context.keywords else "en"),
                        "sources": [],
                        "blocked": True,
                    },
                    latency_ms=(time.time() - start_time) * 1000,
                    metadata={"blocked": True, "reason": "No verified sources found"},
                )

            # Determine which LLM to use
            use_vision = (
                context.tool_selection and
                ToolType.VISION in context.tool_selection.selected_tools
            )

            if use_vision:
                answer = await self._generate_with_vision(context, source_context)
            else:
                answer = await self._generate_with_vllm(context, source_context)

            # Extract sources for citation
            sources = context.get_all_sources()

            latency = (time.time() - start_time) * 1000
            logger.info(f"[OpenCode] Step 5 completed: Generated answer ({len(answer)} chars), {len(sources)} sources")

            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.COMPLETED,
                output={
                    "answer": answer,
                    "sources": sources,
                    "blocked": False,
                },
                latency_ms=latency,
                metadata={
                    "answer_length": len(answer),
                    "source_count": len(sources),
                    "vision_used": use_vision,
                },
            )

        except Exception as e:
            logger.error(f"[OpenCode] Step 5 failed: {e}")
            return StepResult(
                step_name=self.name,
                step_number=self.step_number,
                status=StepStatus.FAILED,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

    def _build_source_context(self, context: OpenCodeContext) -> str:
        """Build context string from verified sources"""
        parts = []

        # Add summary context
        for search in context.summary_searches:
            if search.error_context:
                parts.append(f"[SUMMARY - Error Code]\n{search.error_context}")
            if search.command_context:
                parts.append(f"[SUMMARY - Command]\n{search.command_context}")
            if search.term_context:
                parts.append(f"[SUMMARY - Term]\n{search.term_context}")

        # Add PDF chunk context
        for pdf in context.pdf_verifications:
            for chunk in pdf.verified_chunks:
                content = chunk.get("content", "")
                page = chunk.get("page_number", "N/A")
                if content:
                    parts.append(f"[Source: {pdf.document_name}, Page: {page}]\n{content[:1000]}")

        return "\n\n---\n\n".join(parts)

    async def _generate_with_vision(self, context: OpenCodeContext, source_context: str) -> str:
        """Generate answer using Vision LLM (MiniCPM-V)"""
        try:
            from ...services.vision_llm_factory import get_vision_llm_factory
            factory = get_vision_llm_factory()
            vision_llm = await factory.get_or_create("minicpm")

            # Build prompt for Vision LLM
            prompt = self._build_generation_prompt(context, source_context)

            # Call Vision LLM
            response = await vision_llm.generate(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=context.config.max_tokens if hasattr(context.config, 'max_tokens') else 2048,
            )

            return response.content if hasattr(response, 'content') else str(response)

        except Exception as e:
            logger.warning(f"[OpenCode] Vision LLM failed, falling back to vLLM: {e}")
            return await self._generate_with_vllm(context, source_context)

    async def _generate_with_vllm(self, context: OpenCodeContext, source_context: str) -> str:
        """Generate answer using text LLM (vLLM)"""
        try:
            from ..adapters.ollama_adapter import get_llm_adapter
            llm = get_llm_adapter()

            prompt = self._build_generation_prompt(context, source_context)

            response = await llm.generate([{"role": "user", "content": prompt}])

            return response.get("content", "")

        except Exception as e:
            logger.error(f"[OpenCode] vLLM generation failed: {e}")
            raise

    def _build_generation_prompt(self, context: OpenCodeContext, source_context: str) -> str:
        """Build the generation prompt"""
        language = context.keywords.language if context.keywords else "auto"

        language_instruction = {
            "ko": "한국어로 답변하세요.",
            "ja": "日本語で回答してください。",
            "en": "Answer in English.",
        }.get(language, "Answer in the same language as the question.")

        return f"""You are a document-grounded AI assistant. You MUST answer ONLY using the provided source documents.

{language_instruction}

CRITICAL RULES:
1. ONLY use information from the sources below
2. ALWAYS cite sources using format: [Source: document_name, Page: X]
3. If information is not in sources, say "정보를 찾을 수 없습니다" (or equivalent)
4. DO NOT use any knowledge outside the provided sources

USER QUERY:
{context.query}

VERIFIED SOURCES:
{source_context}

ANSWER (with source citations):"""

    def _get_no_results_message(self, language: str) -> str:
        """Get no-results message in appropriate language"""
        messages = {
            "ko": "이 질문에 대한 정보를 지식 베이스에서 찾을 수 없습니다. 관련 문서를 업로드해 주시면 답변해 드릴 수 있습니다.",
            "ja": "この情報はナレッジベースで見つかりませんでした。関連文書をアップロードしていただければ回答できます。",
            "en": "I cannot find information about this in the knowledge base. Please upload relevant documents if you'd like me to answer.",
        }
        return messages.get(language, messages["en"])


# Export all steps
PIPELINE_STEPS = [
    KeywordExtractionStep,
    SummarySearchStep,
    PDFVerificationStep,
    ToolSelectionStep,
    AnswerGenerationStep,
]
