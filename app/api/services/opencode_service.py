"""
OpenAgent Service (vLLM Direct Connection with Summary-based RAG)

Connects directly to vLLM server using OpenAI-compatible API.
vLLM server: 192.168.8.11:12800 (Qwen/Qwen2.5-7B-Instruct)

This service provides:
1. Direct vLLM API connection
2. Summary-based RAG for OpenFrame knowledge
3. PDF reference extraction for detailed information

The RAG flow:
1. User query → SummarySearchService (search summaries)
2. Enrich query with summary context
3. Send enriched prompt to vLLM
4. Return response with source references
"""
import os
import re
import logging
from typing import Optional, AsyncGenerator, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# MetadataConfigService lazy import to avoid circular dependencies
_metadata_service = None

async def _get_metadata_service():
    """Lazy load MetadataConfigService."""
    global _metadata_service
    if _metadata_service is None:
        try:
            from .metadata_config_service import get_metadata_config_service
            _metadata_service = await get_metadata_config_service()
            logger.info("MetadataConfigService loaded for OpenAgentService")
        except Exception as e:
            logger.warning(f"Failed to load MetadataConfigService: {e}")
    return _metadata_service


async def _search_document_structure(
    query: str,
    doc_name: Optional[str] = None,
    page_numbers: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Search document structures for hierarchical context.

    Uses the PDF structure extraction system to find:
    - Chapter/Section/Subsection context
    - Page ranges for precise source citations
    - Image/table references within sections

    Args:
        query: User query for keyword extraction
        doc_name: Document name pattern (e.g., "OF_TJES", "HiDB")
        page_numbers: Specific page numbers to search

    Returns:
        Dict containing:
        - structure_context: Formatted section hierarchy
        - sections: List of matching sections with page ranges
        - images: Image references from matching sections
    """
    result = {
        "structure_context": "",
        "sections": [],
        "images": [],
        "doc_name": None,
    }

    try:
        from .summary_search_service import get_summary_search_service
        summary_service = get_summary_search_service()

        # Step 1: Find document by name pattern or query keywords
        if doc_name:
            # Search for structure matching document name
            structure = await summary_service.search_structure(doc_name)
        else:
            # Try to extract document reference from query
            # Patterns: HiDB, TJES, OSC, TACF, Base, etc.
            doc_patterns = [
                (r"(HiDB|HIDB)", "HiDB"),
                (r"(TJES|tjes)", "TJES"),
                (r"(OSC|osc)", "OSC"),
                (r"(TACF|tacf)", "TACF"),
                (r"(OSI|osi)", "OSI"),
                (r"(NDB|ndb)", "NDB"),
                (r"(BASE|Base|base)", "Base"),
                (r"(Batch|BATCH|batch)", "Batch"),
                (r"(COBOL|cobol)", "COBOL"),
                (r"(ASM|asm)", "ASM"),
                (r"(Tibero|tibero)", "Tibero"),
            ]

            structure = None
            for pattern, name in doc_patterns:
                if re.search(pattern, query):
                    structure = await summary_service.search_structure(name)
                    if structure:
                        result["doc_name"] = name
                        break

        if not structure:
            return result

        result["doc_name"] = structure.get("file_name", "")

        # Step 2: If specific pages requested, get sections for those pages
        if page_numbers:
            pdf_name = structure.get("file_name", "")
            for page in page_numbers[:3]:  # Limit to 3 pages
                page_structure = await summary_service.get_structure_for_pages(
                    pdf_name, page, page
                )
                if page_structure and page_structure.get("sections"):
                    result["sections"].extend(page_structure["sections"])

        # Step 3: Build structure context string
        hierarchy = structure.get("hierarchy", [])
        if hierarchy:
            context_parts = []
            for node in hierarchy[:10]:  # Limit to top 10 chapters
                title = node.get("title", "")
                page_start = node.get("page_start", 0)
                page_end = node.get("page_end", 0)
                node_type = node.get("node_type", "")

                if node_type == "chapter":
                    context_parts.append(f"## {title} (p.{page_start}-{page_end})")

                    # Add top-level sections
                    for child in node.get("children", [])[:5]:
                        child_title = child.get("title", "")
                        child_start = child.get("page_start", 0)
                        context_parts.append(f"  - {child_title} (p.{child_start})")

            result["structure_context"] = "\n".join(context_parts)

        # Step 4: Get image references for the document
        pdf_name = structure.get("file_name", "")
        if pdf_name:
            images = await summary_service.get_image_references(pdf_name)
            result["images"] = images[:10]  # Limit to 10 images

        logger.info(
            f"Structure search: doc={result['doc_name']}, "
            f"sections={len(result['sections'])}, images={len(result['images'])}"
        )

    except Exception as e:
        logger.warning(f"Document structure search failed: {e}")

    return result


@dataclass
class OpenAgentConfig:
    """Configuration for OpenAgent vLLM connection."""
    base_url: str = "http://192.168.8.11:12800/v1"
    model: str = "Qwen/Qwen2.5-7B-Instruct"
    max_tokens: int = 2048
    temperature: float = 0.7
    timeout: int = 120


class OpenAgentService:
    """
    Service for vLLM-based chat using OpenAI-compatible API.

    Connects directly to vLLM server without requiring opencode CLI.
    """

    def __init__(self, config: Optional[OpenAgentConfig] = None):
        """
        Initialize OpenAgent service.

        Args:
            config: Optional configuration. Uses defaults from opencode.json if not provided.
        """
        self.config = config or self._load_config()

        # Initialize AsyncOpenAI client for vLLM
        self.client = AsyncOpenAI(
            base_url=self.config.base_url,
            api_key="EMPTY",  # vLLM doesn't require API key
            timeout=self.config.timeout,
        )

        # Domain knowledge for anti-hallucination
        self._glossary_map: Dict[str, str] = {}
        self._domain_knowledge_prompt: str = ""
        self._load_domain_knowledge()

        logger.info(f"OpenAgent initialized: {self.config.base_url} / {self.config.model}")

    def _load_config(self) -> OpenAgentConfig:
        """Load configuration from environment or opencode.json."""
        # Check environment variables first
        base_url = os.getenv("VLLM_BASE_URL", "http://192.168.8.11:12800/v1")
        model = os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        max_tokens = int(os.getenv("VLLM_MAX_TOKENS", "2048"))
        temperature = float(os.getenv("VLLM_TEMPERATURE", "0.7"))

        # Try to load from opencode.json if exists
        try:
            import json
            config_paths = [
                "opencode.json",
                "/opt/kms/opencode.json",
                os.path.expanduser("~/.opencode.json"),
            ]

            for config_path in config_paths:
                if os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        data = json.load(f)

                    # Extract vLLM config
                    if "provider" in data and "vllm" in data["provider"]:
                        vllm_config = data["provider"]["vllm"]
                        if "options" in vllm_config:
                            base_url = vllm_config["options"].get("baseURL", base_url)
                        if "models" in vllm_config:
                            # Get first model's settings
                            for model_id, model_config in vllm_config["models"].items():
                                model = model_id
                                if "limit" in model_config:
                                    max_tokens = model_config["limit"].get("output", max_tokens)
                                break

                    # Check if model is specified at root level
                    if "model" in data:
                        model_str = data["model"]
                        if "/" in model_str:
                            # Format: "vllm/Qwen/Qwen2.5-7B-Instruct"
                            parts = model_str.split("/", 1)
                            if len(parts) > 1:
                                model = parts[1]

                    logger.info(f"Loaded config from {config_path}")
                    break

        except Exception as e:
            logger.warning(f"Could not load opencode.json: {e}")

        return OpenAgentConfig(
            base_url=base_url,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    # 핵심 약어 정의 - 폴백용 (DB 로드 실패 시 사용)
    # 실제 데이터는 MetadataConfigService에서 로드
    _FALLBACK_CORE_TERMS: Dict[str, str] = {
        "TJES": "Tmax Job Entry Subsystem (batch job scheduling, equivalent to JES2/JES3)",
        "TACF": "Tmax Access Control Facility (security, equivalent to RACF)",
        "OSC": "Online SC (online transaction processing, equivalent to CICS)",
        "HiDB": "Hierarchical Database (equivalent to IMS DB)",
        "KSDS": "Key Sequenced Data Set (키순 데이터셋, records stored in key order, supports random access by key)",
        "ESDS": "Entry Sequenced Data Set (입력순 데이터셋, records stored in entry order, sequential access only)",
        "RRDS": "Relative Record Data Set (상대 레코드 데이터셋, records accessed by relative record number)",
    }

    # _CORE_TERMS는 동적으로 로드됨 (DB 우선, 폴백으로 _FALLBACK_CORE_TERMS)
    _CORE_TERMS: Dict[str, str] = {}

    def _load_domain_knowledge(self) -> None:
        """Load glossary terms from summary files and build domain knowledge prompt.

        This is the sync initialization method. For DB-driven terms, call
        _load_domain_knowledge_async() after service initialization.
        """
        # 폴백 약어로 초기화 (DB 로드 전까지 사용)
        self._CORE_TERMS = dict(self._FALLBACK_CORE_TERMS)
        self._glossary_map = dict(self._FALLBACK_CORE_TERMS)
        self._metadata_loaded = False

        # glossary 파일에서 추가 용어 동적 로드 (파일 시스템 기반)
        summaries_dir = Path("uploads/summaries")
        if not summaries_dir.exists():
            summaries_dir = Path("/opt/kms/uploads/summaries")

        glossary_dir = summaries_dir / "glossary"
        if glossary_dir.exists():
            loaded_count = 0
            for md_file in sorted(glossary_dir.glob("*.md")):
                if md_file.name == "index.md":
                    continue
                try:
                    content = md_file.read_text(encoding="utf-8")
                    # 패턴: ## TERM\n- **정식명칭**: FullName
                    for match in re.finditer(
                        r"^## ([A-Za-z][\w]{1,20})\n- \*\*정식명칭\*\*: (.+)",
                        content,
                        re.MULTILINE,
                    ):
                        term = match.group(1).strip()
                        full_name = match.group(2).strip()
                        # 핵심 약어는 하드코딩 우선
                        if term.upper() not in {k.upper() for k in self._CORE_TERMS}:
                            # 명백히 부정확한 항목 필터링 (코드 조각, 숫자만 등)
                            if (
                                len(full_name) > 1
                                and not full_name.startswith("(")
                                and not full_name[0].isdigit()
                            ):
                                self._glossary_map[term] = full_name
                                loaded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to parse glossary {md_file.name}: {e}")

            logger.info(
                f"Loaded {loaded_count} glossary terms "
                f"(+ {len(self._CORE_TERMS)} core terms)"
            )

    async def _load_domain_knowledge_async(self) -> None:
        """Load domain knowledge from MetadataConfigService (async version).

        Call this after initialization to load DB-driven terms.
        """
        if self._metadata_loaded:
            return

        try:
            metadata_service = await _get_metadata_service()
            if metadata_service:
                # Load glossary terms from DB
                db_terms = await metadata_service.get_all_glossary_terms()
                if db_terms:
                    # Convert DB format to our format
                    for term, data in db_terms.items():
                        full_name = data.get('full_name', '')
                        equiv = data.get('equivalent_to', '')
                        desc = data.get('description', '')

                        # Build description string like the original format
                        term_desc = full_name
                        if equiv:
                            term_desc += f" (equivalent to {equiv})"
                        elif desc:
                            term_desc += f" ({desc[:50]})"

                        self._CORE_TERMS[term] = term_desc
                        self._glossary_map[term] = term_desc

                    logger.info(f"Loaded {len(db_terms)} glossary terms from MetadataConfigService")
                    self._metadata_loaded = True

                    # Rebuild domain knowledge prompt with new terms
                    self._rebuild_domain_knowledge_prompt()
        except Exception as e:
            logger.warning(f"Failed to load domain knowledge from DB: {e}")

        # 정적 도메인 지식 프롬프트 구축
        core_terms_table = "\n".join(
            f"- {term}: {desc}" for term, desc in self._CORE_TERMS.items()
        )
        self._domain_knowledge_prompt = f"""## OpenFrame Domain Knowledge

OpenFrame is TmaxSoft's mainframe rehosting solution that migrates IBM/Fujitsu mainframe workloads to open systems (Linux/Unix).

### Core Abbreviations (AUTHORITATIVE - use ONLY these definitions):
{core_terms_table}

### Key Management Commands:
- tjesmgr: TJES管理ツール (BOOT, SHUTDOWN, SUBMIT, CANCEL, etc.)
- tacfmgr: TACF管理ツール (ADDUSER, ADDGROUP, PERMIT, etc.)
- hidbmgr: HiDB管理ツール (START, STOP, STATUS, etc.)
- oscmgr: OSC管理ツール (region management)
- ndbmgr: NDB管理ツール
- catmgr: Catalog管理ツール
- volmgr: Volume管理ツール
- osimgr: OSI管理ツール

### Key System Commands:
- tmboot/tmdown: Tmax engine start/stop
- ofboot/ofdown: OpenFrame system start/stop
- jesinit/jesdown: JES subsystem start/stop"""

    def _rebuild_domain_knowledge_prompt(self) -> None:
        """Rebuild domain knowledge prompt after loading new terms."""
        core_terms_table = "\n".join(
            f"- {term}: {desc}" for term, desc in self._CORE_TERMS.items()
        )
        self._domain_knowledge_prompt = f"""## OpenFrame Domain Knowledge

OpenFrame is TmaxSoft's mainframe rehosting solution that migrates IBM/Fujitsu mainframe workloads to open systems (Linux/Unix).

### Core Abbreviations (AUTHORITATIVE - use ONLY these definitions):
{core_terms_table}

### Key Management Commands:
- tjesmgr: TJES管理ツール (BOOT, SHUTDOWN, SUBMIT, CANCEL, etc.)
- tacfmgr: TACF管理ツール (ADDUSER, ADDGROUP, PERMIT, etc.)
- hidbmgr: HiDB管理ツール (START, STOP, STATUS, etc.)
- oscmgr: OSC管理ツール (region management)
- ndbmgr: NDB管理ツール
- catmgr: Catalog管理ツール
- volmgr: Volume管理ツール
- osimgr: OSI管理ツール

### Key System Commands:
- tmboot/tmdown: Tmax engine start/stop
- ofboot/ofdown: OpenFrame system start/stop
- jesinit/jesdown: JES subsystem start/stop"""

    async def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        file_content: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a chat message and get a complete response.

        Args:
            message: User message
            system_prompt: Optional system prompt
            file_content: Optional file content to include as context
            history: Optional conversation history
            temperature: Optional temperature override

        Returns:
            Complete response text

        Raises:
            Exception: If API call fails
        """
        result = await self._chat_with_usage(
            message, system_prompt, file_content, history, temperature
        )
        return result["response"]

    async def _chat_with_usage(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        file_content: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Internal chat method that returns both response and token usage.

        Returns:
            Dict with 'response' and 'token_usage' keys
        """
        messages = self._build_messages(message, system_prompt, file_content, history)
        temp = temperature if temperature is not None else self.config.temperature

        logger.info(f"Sending chat request to vLLM: {len(message)} chars, temp={temp}")

        try:
            response = await self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=temp,
            )

            result = response.choices[0].message.content

            # Token usage tracking
            token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            usage = getattr(response, 'usage', None)
            if usage:
                token_usage = {
                    "prompt_tokens": getattr(usage, 'prompt_tokens', 0),
                    "completion_tokens": getattr(usage, 'completion_tokens', 0),
                    "total_tokens": getattr(usage, 'total_tokens', 0),
                }
                logger.info(
                    f"OpenAgent token usage: prompt={token_usage['prompt_tokens']}, "
                    f"completion={token_usage['completion_tokens']}, total={token_usage['total_tokens']}"
                )
            else:
                logger.debug("Token usage not available from vLLM response")

            logger.info(f"Received response: {len(result)} chars")
            return {"response": result, "token_usage": token_usage}

        except Exception as e:
            logger.error(f"vLLM API error: {e}")
            raise

    async def stream(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        file_content: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Send a chat message and stream the response.

        Args:
            message: User message
            system_prompt: Optional system prompt
            file_content: Optional file content to include as context
            history: Optional conversation history
            temperature: Optional temperature override

        Yields:
            Response chunks as they arrive
        """
        async for item in self._stream_with_usage(
            message, system_prompt, file_content, history, temperature
        ):
            if item["type"] == "chunk":
                yield item["data"]
            # Usage info is logged but not yielded in simple stream

    async def _stream_with_usage(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        file_content: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Internal stream method that yields chunks and final token usage.

        Yields:
            Dict with either:
            - {"type": "chunk", "data": "..."} - Content chunk
            - {"type": "usage", "data": {...}} - Final token usage
        """
        messages = self._build_messages(message, system_prompt, file_content, history)
        temp = temperature if temperature is not None else self.config.temperature

        logger.info(f"Starting stream request to vLLM: {len(message)} chars, temp={temp}")

        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            # Request with stream_options to get usage in streaming mode
            stream = await self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=temp,
                stream=True,
                stream_options={"include_usage": True},
            )

            async for chunk in stream:
                # Check for content chunks
                if chunk.choices and chunk.choices[0].delta.content:
                    yield {"type": "chunk", "data": chunk.choices[0].delta.content}

                # Check for usage info (comes in final chunk)
                usage = getattr(chunk, 'usage', None)
                if usage:
                    token_usage = {
                        "prompt_tokens": getattr(usage, 'prompt_tokens', 0),
                        "completion_tokens": getattr(usage, 'completion_tokens', 0),
                        "total_tokens": getattr(usage, 'total_tokens', 0),
                    }

            # Log and yield final usage
            if token_usage["total_tokens"] > 0:
                logger.info(
                    f"OpenAgent stream token usage: prompt={token_usage['prompt_tokens']}, "
                    f"completion={token_usage['completion_tokens']}, total={token_usage['total_tokens']}"
                )
            yield {"type": "usage", "data": token_usage}

        except Exception as e:
            logger.error(f"vLLM stream error: {e}")
            yield {"type": "chunk", "data": f"[Error: {str(e)}]"}
            yield {"type": "usage", "data": token_usage}

    def _build_messages(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        file_content: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """Build the messages list for the API call."""
        messages = []

        # System prompt
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({
                "role": "system",
                "content": (
                    "You are a helpful AI assistant. "
                    "Answer questions clearly and concisely. "
                    "If you're given file content as context, use it to inform your answers."
                )
            })

        # Add history
        if history:
            messages.extend(history)

        # User message with optional file context
        user_content = message
        if file_content:
            user_content = f"File content:\n```\n{file_content}\n```\n\nQuestion: {message}"

        messages.append({"role": "user", "content": user_content})

        return messages

    async def health_check(self) -> bool:
        """
        Check if vLLM server is available.

        Returns:
            True if server is available, False otherwise
        """
        try:
            # Try to list models
            models = await self.client.models.list()
            model_ids = [m.id for m in models.data]
            logger.info(f"vLLM available. Models: {model_ids}")
            return True
        except Exception as e:
            logger.warning(f"vLLM health check failed: {e}")
            return False

    async def _route_query(self, message: str) -> Dict[str, Any]:
        """
        Route query to appropriate LLM (Vision or Text) using EnhancedQueryRouter.

        Returns:
            Dict with routing decision including selected_llm
        """
        try:
            from app.api.services.enhanced_query_router import EnhancedQueryRouter
            router = EnhancedQueryRouter()
            result = await router.route(query=message)
            return {
                "selected_llm": result.selected_llm,
                "is_visual_query": result.is_visual_query,
                "visual_aspects": result.visual_aspects,
                "reasoning": result.llm_reasoning,
                "confidence": result.llm_confidence,
            }
        except Exception as e:
            logger.warning(f"Query routing failed, defaulting to text: {e}")
            return {
                "selected_llm": "text",
                "is_visual_query": False,
                "visual_aspects": [],
                "reasoning": "Routing failed, using text LLM",
                "confidence": 0.5,
            }

    async def _call_vision_llm(
        self,
        message: str,
        summary_context: str,
        images: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Call Vision LLM (MiniCPM-V) with the given context and images.

        Args:
            message: User query
            summary_context: Context from summary search
            images: List of images with 'data' (base64) and 'page' keys

        Returns:
            Dict with response and metadata
        """
        try:
            from app.api.adapters.vision.minicpm_vision_adapter import MiniCPMVisionAdapter
            from app.api.ports.vision_llm_port import ImageContent, VisionMessage, VisionLLMConfig
            from app.api.core.config import get_api_settings
            import base64

            settings = get_api_settings()

            # Create MiniCPM-V adapter
            adapter = MiniCPMVisionAdapter(
                base_url=settings.VISION_API_URL,
                model=settings.VISION_LLM_MODEL,
                max_tokens=settings.VISION_MAX_TOKENS,
                timeout=settings.VISION_TIMEOUT,
            )

            # Build system prompt with summary context
            system_prompt = f"""{self._domain_knowledge_prompt}

## Reference Context from Summaries
{summary_context if summary_context else "No additional context available."}

## Instructions
- Analyze the provided image(s) carefully
- Answer the user's question based on the visual content
- If the image contains tables, charts, or diagrams, describe them accurately
- Reference the summary context when relevant
- If the information is not visible in the image, say so clearly
- Respond in the same language as the user's question"""

            # Convert images to ImageContent
            image_contents = []
            for img in images[:5]:  # Limit to 5 images
                try:
                    image_bytes = None
                    page_info = img.get('page', img.get('page_start', 'N/A'))
                    mime_type = "image/png"

                    # Case 1: base64 encoded data in 'data' key
                    if img.get("data"):
                        image_bytes = base64.b64decode(img["data"])

                    # Case 2: image_url - could be data URL or HTTP URL
                    elif img.get("image_url"):
                        image_url = img["image_url"]

                        # Handle data URLs (e.g., data:image/png;base64,...)
                        if image_url.startswith("data:"):
                            # Parse data URL: data:[<mediatype>][;base64],<data>
                            try:
                                # Split by comma to separate header from data
                                header, data = image_url.split(",", 1)
                                # Extract mime type from header if present
                                if ";" in header:
                                    mime_part = header.split(":")[1].split(";")[0]
                                    if mime_part:
                                        mime_type = mime_part
                                image_bytes = base64.b64decode(data)
                            except Exception as e:
                                logger.warning(f"Failed to parse data URL: {e}")

                        # Handle HTTP/HTTPS URLs
                        elif image_url.startswith("http"):
                            import aiohttp
                            async with aiohttp.ClientSession() as session:
                                async with session.get(image_url) as resp:
                                    if resp.status == 200:
                                        image_bytes = await resp.read()
                                    else:
                                        logger.warning(f"Failed to fetch image from {image_url}: {resp.status}")

                        # Handle relative URLs
                        elif image_url.startswith("/"):
                            import aiohttp
                            full_url = f"http://localhost:9000{image_url}"
                            async with aiohttp.ClientSession() as session:
                                async with session.get(full_url) as resp:
                                    if resp.status == 200:
                                        image_bytes = await resp.read()
                                    else:
                                        logger.warning(f"Failed to fetch image from {full_url}: {resp.status}")

                    if image_bytes:
                        image_contents.append(ImageContent(
                            image_bytes=image_bytes,
                            mime_type=mime_type,
                            description=f"Page {page_info}"
                        ))
                        logger.info(f"Successfully processed image for page {page_info}, size={len(image_bytes)} bytes")
                except Exception as e:
                    logger.warning(f"Failed to process image: {e}")

            if not image_contents:
                logger.warning("No valid images for Vision LLM, falling back to text")
                return None

            logger.info(f"Calling Vision LLM with {len(image_contents)} images")

            # Build messages
            messages = [
                VisionMessage(role="system", content=system_prompt),
                VisionMessage(role="user", content=message, images=image_contents),
            ]

            # Call Vision LLM
            config = VisionLLMConfig(
                max_tokens=settings.VISION_MAX_TOKENS,
                temperature=0.3,
                timeout=settings.VISION_TIMEOUT,
            )

            response = await adapter.generate(messages, config)
            logger.info(f"Vision LLM response received: {len(response.content)} chars")

            return {
                "response": response.content,
                "model": "vision/minicpm-v",
                "token_usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            }

        except Exception as e:
            logger.error(f"Vision LLM call failed: {type(e).__name__}: {e}")
            return None

    async def rag_chat(
        self,
        message: str,
        file_content: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        use_summaries: bool = True,
        language: str = "ja",
    ) -> Dict[str, Any]:
        """
        RAG-enhanced chat using summary documents.

        This method:
        1. Searches summaries for relevant context
        2. Builds a knowledge-enriched system prompt
        3. Sends to vLLM for response generation
        4. Returns response with source references

        Args:
            message: User query
            file_content: Optional additional file content
            history: Conversation history
            use_summaries: Whether to use summary-based RAG (default True)
            language: UI language setting (en, ko, ja) - response will be in this language

        Returns:
            Dict containing:
            - response: LLM response text
            - sources: List of source references
            - summary_context: Context used from summaries
            - confidence: high/medium/low
        """
        # Lazy load metadata from DB (first call only)
        await self._load_domain_knowledge_async()

        from .summary_search_service import get_summary_search_service

        sources = []
        summary_context = ""
        confidence = "low"

        # Step 1: Search summaries for relevant context
        if use_summaries:
            try:
                summary_service = get_summary_search_service()
                search_result = await summary_service.comprehensive_search(message)

                if search_result.get("results"):
                    summary_context = search_result.get("context_string", "")
                    confidence = search_result.get("confidence", "low")

                    # Collect source references
                    for result in search_result.get("results", []):
                        source_file = result.get("source_file", "")
                        if source_file:
                            sources.append({
                                "type": result.get("type"),
                                "file": source_file,
                            })

                    logger.info(
                        f"Summary RAG: Found {len(search_result.get('results', []))} "
                        f"results, confidence={confidence}"
                    )

            except Exception as e:
                logger.warning(f"Summary search failed: {e}")

        # Step 1.5: Search document structures for hierarchical context
        structure_context = ""
        structure_sections = []
        structure_images = []
        try:
            # Extract document name from sources if available
            doc_name_hint = None
            for src in sources:
                src_file = src.get("file", "")
                # Extract product name from file path (e.g., "commands/OpenFrame_TJES_MVS.md")
                if "TJES" in src_file:
                    doc_name_hint = "TJES"
                    break
                elif "HiDB" in src_file or "HIDB" in src_file:
                    doc_name_hint = "HiDB"
                    break
                elif "OSC" in src_file:
                    doc_name_hint = "OSC"
                    break
                elif "TACF" in src_file:
                    doc_name_hint = "TACF"
                    break
                elif "OSI" in src_file:
                    doc_name_hint = "OSI"
                    break

            structure_result = await _search_document_structure(
                query=message,
                doc_name=doc_name_hint,
            )

            if structure_result.get("structure_context"):
                structure_context = structure_result["structure_context"]
                structure_sections = structure_result.get("sections", [])
                structure_images = structure_result.get("images", [])

                # Add structure source to references
                if structure_result.get("doc_name"):
                    sources.append({
                        "type": "document_structure",
                        "file": structure_result["doc_name"],
                    })

                logger.info(
                    f"Structure RAG: doc={structure_result.get('doc_name')}, "
                    f"sections={len(structure_sections)}, images={len(structure_images)}"
                )

        except Exception as e:
            logger.warning(f"Document structure search failed: {e}")

        # Step 2: Route query to determine Vision vs Text LLM
        routing_decision = await self._route_query(message)
        selected_llm = routing_decision.get("selected_llm", "text")
        logger.info(
            f"Query routing: selected_llm={selected_llm}, "
            f"is_visual={routing_decision.get('is_visual_query')}, "
            f"confidence={routing_decision.get('confidence')}"
        )

        # Step 3: Search for related tables and images (needed for both Vision and Text paths)
        tables = []
        images = []
        try:
            # Extract page references from summary context
            page_refs = re.findall(r"p\.(\d+)|page\s*(\d+)|(\d+)ページ", summary_context, re.IGNORECASE)
            pages = [int(p[0] or p[1] or p[2]) for p in page_refs if p[0] or p[1] or p[2]]

            # PRIORITY: Extract product keywords from USER QUERY first (not from summary context)
            # This ensures table/image search is relevant to what user asked about
            doc_refs = []
            query_product = None

            # 1. First try regex patterns on user query (most reliable)
            query_patterns = [
                r"(HiDB|HIDB)",
                r"(TJES|tjes)",
                r"(OSC|osc)",
                r"(TACF|tacf)",
                r"(BASE|base)",
                r"(ADRDSSU|adrdssu)",
                r"(IDCAMS|idcams)",
                r"(IEBCOPY|iebcopy)",
                r"(IEBGENER|iebgener)",
                r"(DFSORT|dfsort)",
            ]
            for pattern in query_patterns:
                match = re.search(pattern, message, re.IGNORECASE)
                if match:
                    query_product = match.group(1).upper()
                    doc_refs = [query_product]
                    logger.info(f"Extracted product keyword from query: {query_product}")
                    break

            # 2. If no product found in query, try metadata service
            if not doc_refs:
                try:
                    metadata_service = await _get_metadata_service()
                    if metadata_service:
                        doc_name = await metadata_service.find_document_for_keyword(message)
                        if doc_name:
                            doc_refs = [doc_name]
                            logger.debug(f"Found document pattern from metadata: {doc_name}")
                except Exception as e:
                    logger.debug(f"Metadata lookup failed: {e}")

            # 3. Fallback to summary context (least reliable - may contain unrelated docs)
            # Only use if nothing found above
            if not doc_refs:
                doc_refs = re.findall(r"(OF_[A-Za-z_]+)", summary_context)
                if doc_refs:
                    logger.debug(f"Using doc refs from summary context: {doc_refs[:2]}")

            doc_name = doc_refs[0] if doc_refs else None

            # Store query_product for later filtering
            query_product_filter = query_product

            # Search conditions: has page refs, doc name, or query mentions tables/formats/charts/diagrams
            # Use MetadataConfigService for visual keywords
            has_visual_keywords = False
            try:
                metadata_service = await _get_metadata_service()
                if metadata_service:
                    has_visual_keywords, visual_weight = await metadata_service.is_visual_keyword(message)
                    if has_visual_keywords:
                        logger.debug(f"Visual keyword detected from metadata, weight={visual_weight}")
            except Exception as e:
                logger.debug(f"Visual keyword metadata lookup failed: {e}")

            # Fallback to hardcoded list if metadata lookup failed
            if not has_visual_keywords:
                visual_keywords = ["表", "テーブル", "フォーマット", "table", "format", "データ構造", "structure",
                                  "図", "チャート", "ダイアグラム", "chart", "diagram", "flow", "process", "画像", "image",
                                  "プロセス図", "処理図", "フロー図"]
                has_visual_keywords = any(kw in message.lower() for kw in visual_keywords)
            should_search = pages or doc_name or has_visual_keywords

            if should_search:
                if pages:
                    # Search by page numbers
                    for page in pages[:3]:
                        result = await self.search_tables_and_images(
                            doc_name=doc_name,
                            page_number=page
                        )
                        tables.extend(result.get("tables", []))
                        images.extend(result.get("images", []))
                elif doc_name:
                    # Search by document name only
                    # CONSERVATIVE: Only add images if visual keywords detected
                    # Without visual keywords, searching by doc name alone returns too many unrelated images
                    result = await self.search_tables_and_images(
                        doc_name=doc_name
                    )
                    tables.extend(result.get("tables", []))
                    # Only add images when visual keywords present
                    if has_visual_keywords:
                        images.extend(result.get("images", []))
                        logger.info(f"Adding {len(result.get('images', []))} images for doc={doc_name} (visual keywords detected)")
                    else:
                        logger.info(f"Skipping {len(result.get('images', []))} images for doc={doc_name} (no visual keywords)")
                elif has_visual_keywords:
                    # CONSERVATIVE: Skip image search without document context
                    # Query-only search often returns unrelated images from other documents
                    # Only search tables by query (tables are usually more relevant)
                    logger.info("Visual keywords detected but no doc/page context - skipping image search to avoid unrelated images")
                    result = await self.search_tables_and_images(
                        query=message
                    )
                    # Only include tables, NOT images (too high risk of unrelated results)
                    tables.extend(result.get("tables", []))
                    # images NOT extended here - only add images when document context exists

                logger.info(f"Table/image search: doc={doc_name}, pages={pages}, found tables={len(tables)}, images={len(images)}")

                # Post-filter tables to ensure relevance to user's query
                # Two-stage filtering: product name AND query keywords
                if tables:
                    original_count = len(tables)
                    filtered_tables = []

                    # Extract query keywords for content relevance check
                    # Focus on meaningful terms (nouns, commands) not particles
                    query_keywords = []
                    # Japanese/English keywords from query
                    import re as filter_re
                    # Extract alphanumeric terms (commands, product names)
                    alpha_terms = filter_re.findall(r'[A-Za-z]{3,}', message)
                    query_keywords.extend([t.lower() for t in alpha_terms])
                    # Extract CJK meaningful terms (longer than 2 chars to skip particles)
                    cjk_terms = filter_re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{2,}', message)
                    # Filter out common Japanese particles and question words
                    stop_words = {'について', 'ください', 'できる', 'ある', 'する', 'です', 'ます', 'こと', 'もの', 'なに', 'どの'}
                    query_keywords.extend([t for t in cjk_terms if t not in stop_words])

                    logger.debug(f"Table filter keywords: {query_keywords}")

                    for tbl in tables:
                        doc_filename = tbl.get("doc_filename", "").lower()
                        content = tbl.get("content", "").lower()

                        # Stage 1: Product filter (if available)
                        product_match = True
                        if query_product_filter:
                            product_lower = query_product_filter.lower()
                            product_match = product_lower in doc_filename or product_lower in content

                        # Stage 2: Content relevance check - at least one query keyword must match
                        keyword_match = False
                        if query_keywords:
                            for kw in query_keywords:
                                if kw.lower() in content:
                                    keyword_match = True
                                    break
                        else:
                            # No keywords extracted, pass through
                            keyword_match = True

                        # Include if: product matches AND at least one keyword matches in content
                        if product_match and keyword_match:
                            filtered_tables.append(tbl)
                        else:
                            logger.debug(f"Filtered out table: {doc_filename} (product={product_match}, keyword={keyword_match})")

                    tables = filtered_tables
                    if len(tables) != original_count:
                        logger.info(f"Filtered tables: {original_count} -> {len(tables)} (product + keyword relevance)")

        except Exception as e:
            logger.warning(f"Table/image search failed: {e}")

        # Step 3.5: Vision Knowledge Service - Dynamic PDF page analysis
        # When no indexed images found, try to render PDF pages from summary references
        vision_knowledge_result = None
        if not images and sources and confidence in ("high", "medium"):
            try:
                from .vision_knowledge_service import get_vision_knowledge_service, ENABLE_VISION_KNOWLEDGE

                if ENABLE_VISION_KNOWLEDGE:
                    vision_service = get_vision_knowledge_service()
                    vision_knowledge_result = await vision_service.search_with_vision(
                        query=message,
                        language=language,
                        max_pages=3,
                    )

                    if vision_knowledge_result.get("type") == "vision_enriched":
                        logger.info(
                            f"VisionKnowledge enrichment: {vision_knowledge_result.get('image_count', 0)} images analyzed, "
                            f"sources={vision_knowledge_result.get('sources', [])}"
                        )
            except Exception as vk_error:
                logger.warning(f"VisionKnowledge enrichment failed: {vk_error}")

        # Step 4: Call appropriate LLM based on routing decision and available images
        model_used = "text/qwen"

        # Force Vision LLM when images are available AND query contains visual/format keywords
        use_vision = selected_llm == "vision" and images

        if not use_vision and images:
            # Check if query suggests visual content should be analyzed
            visual_query_keywords = ["フォーマット", "format", "構造", "structure", "図", "chart", "diagram",
                                    "テーブル", "table", "表", "画像", "image", "プロセス", "process", "flow"]
            has_visual_kw = any(kw in message.lower() for kw in visual_query_keywords)
            if has_visual_kw:
                use_vision = True
                logger.info(f"Forcing Vision LLM due to visual keywords in query and {len(images)} images available")

        if use_vision:
            # Use Vision LLM (MiniCPM-V) when visual query and images are available
            logger.info(f"Using Vision LLM (MiniCPM-V) with {len(images)} images")
            vision_result = await self._call_vision_llm(
                message=message,
                summary_context=summary_context,
                images=images,
            )

            if vision_result:
                # Vision LLM succeeded
                model_used = vision_result.get("model", "vision/minicpm-v")
                return {
                    "response": vision_result["response"],
                    "sources": sources,
                    "summary_context": summary_context,
                    "structure_context": structure_context,
                    "confidence": confidence,
                    "token_usage": vision_result.get("token_usage", {}),
                    "tables": tables,
                    "images": images,
                    "structure_images": structure_images,
                    "model": model_used,
                    "routing": routing_decision,
                }
            else:
                # Vision LLM failed, fallback to Text LLM
                logger.warning("Vision LLM failed, falling back to Text LLM")
                selected_llm = "text"

        # Check if VisionKnowledge enrichment is available
        if vision_knowledge_result and vision_knowledge_result.get("type") == "vision_enriched":
            # Use VisionKnowledge analysis result directly
            vision_answer = vision_knowledge_result.get("answer", "")
            vision_sources = vision_knowledge_result.get("sources", [])

            # Combine summary context with vision answer
            combined_response = f"{vision_answer}"

            # Add vision sources to source list
            for vs in vision_sources:
                sources.append({
                    "type": "vision_analysis",
                    "file": vs,
                })

            logger.info(
                f"[RAG_CHAT_RESULT] Using VisionKnowledge: {vision_knowledge_result.get('image_count', 0)} images, "
                f"sources={vision_sources}"
            )

            # Get page images for UI display
            page_images = vision_knowledge_result.get("page_images", [])

            # Convert to UI-compatible image format
            vision_images = []
            for pi in page_images:
                vision_images.append({
                    "chunk_id": f"vision_{pi.get('pdf_name', '')}_{pi.get('page_num', 0)}",
                    "content": "",
                    "page_start": pi.get("page_num", 0),
                    "page_end": pi.get("page_num", 0),
                    "doc_filename": pi.get("pdf_name", ""),
                    "image_url": f"data:image/png;base64,{pi.get('image_base64', '')}",
                })

            return {
                "response": combined_response,
                "sources": sources,
                "summary_context": summary_context,
                "structure_context": structure_context,
                "confidence": "high",  # VisionKnowledge analysis is high confidence
                "token_usage": {},  # Vision LLM doesn't return token usage in same format
                "tables": tables,
                "images": vision_images if vision_images else images,  # Vision 이미지 우선
                "structure_images": structure_images,
                "model": "vision/minicpm-v",
                "routing": routing_decision,
                "vision_enriched": True,
                "vision_image_count": vision_knowledge_result.get("image_count", 0),
                "vision_sources": vision_sources,
            }

        # Text LLM path (default or fallback)
        # Combine summary_context with structure_context for enriched prompt
        combined_context = summary_context
        if structure_context:
            combined_context = f"{summary_context}\n\n## Document Structure\n{structure_context}"

        system_prompt = self._build_rag_system_prompt(
            combined_context, confidence, message, language
        )

        chat_result = await self._chat_with_usage(
            message=message,
            system_prompt=system_prompt,
            file_content=file_content,
            history=history,
            temperature=0.3,
        )

        # Log final result before returning
        logger.info(f"[RAG_CHAT_RESULT] tables={len(tables)}, images={len(images)}, model={model_used}")
        if images:
            for idx, img in enumerate(images):
                logger.info(f"[RAG_CHAT_IMAGE] {idx+1}: doc={img.get('doc_filename')}, page={img.get('page_start')}")

        return {
            "response": chat_result["response"],
            "sources": sources,
            "summary_context": summary_context,
            "structure_context": structure_context,
            "confidence": confidence,
            "token_usage": chat_result["token_usage"],
            "tables": tables,
            "images": images,
            "structure_images": structure_images,
            "model": model_used,
            "routing": routing_decision,
        }

    async def rag_stream(
        self,
        message: str,
        file_content: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        use_summaries: bool = True,
        language: str = "ja",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        RAG-enhanced streaming chat.

        First yields summary context info, then streams LLM response.

        Args:
            language: UI language setting (en, ko, ja) - response will be in this language

        Yields:
            Dict with either:
            - {"type": "context", "data": {...}} - Summary context info
            - {"type": "chunk", "data": "..."} - Response chunk
            - {"type": "done", "data": {...}} - Final info
        """
        from .summary_search_service import get_summary_search_service

        sources = []
        summary_context = ""
        confidence = "low"

        # Step 1: Search summaries
        if use_summaries:
            try:
                summary_service = get_summary_search_service()
                search_result = await summary_service.comprehensive_search(message)

                if search_result.get("results"):
                    summary_context = search_result.get("context_string", "")
                    confidence = search_result.get("confidence", "low")

                    for result in search_result.get("results", []):
                        source_file = result.get("source_file", "")
                        if source_file:
                            sources.append({
                                "type": result.get("type"),
                                "file": source_file,
                            })

                    # Yield context info first
                    yield {
                        "type": "context",
                        "data": {
                            "sources": sources,
                            "confidence": confidence,
                            "result_count": len(search_result.get("results", [])),
                        }
                    }

            except Exception as e:
                logger.warning(f"Summary search failed: {e}")

        # Step 1.5: Search document structures for hierarchical context
        structure_context = ""
        try:
            # Extract document name hint from sources
            doc_name_hint = None
            for src in sources:
                src_file = src.get("file", "")
                if "TJES" in src_file:
                    doc_name_hint = "TJES"
                    break
                elif "HiDB" in src_file or "HIDB" in src_file:
                    doc_name_hint = "HiDB"
                    break
                elif "OSC" in src_file:
                    doc_name_hint = "OSC"
                    break
                elif "TACF" in src_file:
                    doc_name_hint = "TACF"
                    break

            structure_result = await _search_document_structure(
                query=message,
                doc_name=doc_name_hint,
            )

            if structure_result.get("structure_context"):
                structure_context = structure_result["structure_context"]
                if structure_result.get("doc_name"):
                    sources.append({
                        "type": "document_structure",
                        "file": structure_result["doc_name"],
                    })

        except Exception as e:
            logger.warning(f"Structure search in stream failed: {e}")

        # Step 2: Build system prompt and stream response
        # Combine summary_context with structure_context
        combined_context = summary_context
        if structure_context:
            combined_context = f"{summary_context}\n\n## Document Structure\n{structure_context}"

        system_prompt = self._build_rag_system_prompt(
            combined_context, confidence, message, language
        )

        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        async for item in self._stream_with_usage(
            message=message,
            system_prompt=system_prompt,
            file_content=file_content,
            history=history,
            temperature=0.3,
        ):
            if item["type"] == "chunk":
                yield {"type": "chunk", "data": item["data"]}
            elif item["type"] == "usage":
                token_usage = item["data"]

        # Final info with token usage
        yield {
            "type": "done",
            "data": {
                "sources": sources,
                "summary_context": summary_context,
                "structure_context": structure_context,
                "confidence": confidence,
                "token_usage": token_usage,
            }
        }

    def _build_rag_system_prompt(
        self,
        summary_context: str,
        confidence: str,
        user_query: str = "",
        language: str = "ja",
    ) -> str:
        """Build RAG-enhanced system prompt with anti-hallucination rules and domain knowledge."""
        from .language_policy import get_language_policy_service

        # 중앙화된 언어 정책 서비스 사용
        lang_service = get_language_policy_service()
        language_instruction = lang_service.get_language_instruction(language)

        # Language-specific "no info" messages (still needed for error responses)
        lang_no_info = {
            "ja": "この情報はコンテキストに含まれていません",
            "ko": "이 정보는 컨텍스트에 포함되어 있지 않습니다",
            "en": "This information is not included in the context",
        }
        no_info_msg = lang_no_info.get(language, lang_no_info["ja"])

        # Language names for the prompt (still needed for anti-hallucination rules)
        lang_names = {
            "ja": {"name": "Japanese", "native": "日本語"},
            "ko": {"name": "Korean", "native": "한국어"},
            "en": {"name": "English", "native": "English"},
        }
        lang = lang_names.get(language, lang_names["ja"])

        # Section 1: Identity + Anti-Hallucination rules (최우선)
        identity_prompt = (
            f"{language_instruction}\n\n"
            "You are an OpenFrame technical support specialist. "
            "You MUST follow these rules strictly:\n\n"
            "### CRITICAL RULES:\n"
            "1. ONLY answer based on the provided context below. "
            "If the context does not contain the answer, say "
            f'"{no_info_msg}".\n'
            "2. NEVER guess or invent abbreviation meanings. "
            "Use ONLY the definitions provided below.\n"
            "3. NEVER fabricate command options, parameters, or syntax "
            "that are not in the context.\n"
            f"4. RESPOND ONLY IN {lang['name'].upper()} ({lang['native']}).\n"
            "5. For commands, include ONLY the exact syntax from the context. "
            "Do NOT add options like -r, -s, -f unless they appear in the context.\n"
            "6. For error codes, explain based ONLY on the context provided.\n"
            "7. VSAM TYPE SEPARATION: When asked about a specific VSAM type "
            "(KSDS, ESDS, RRDS), ONLY describe that specific type. "
            "Do NOT mention other VSAM types even if they appear in the context.\n"
            "   - ESDS question → answer ESDS only (Entry Sequenced Data Set)\n"
            "   - KSDS question → answer KSDS only (Key Sequenced Data Set)\n"
            "   - RRDS question → answer RRDS only (Relative Record Data Set)\n\n"
            "### FORBIDDEN HALLUCINATIONS:\n"
            '- TJES ≠ "Transaction Journal Entry System" (WRONG)\n'
            '- TACF ≠ "Transaction Access Control Framework" (WRONG)\n'
            "- Do NOT invent subcommands or parameters not in the context.\n"
            "- Do NOT mix VSAM types: ESDS answer must NOT contain KSDS/RRDS.\n"
        )

        # Section 2: 정적 도메인 지식 (항상 포함)
        sections = [identity_prompt, self._domain_knowledge_prompt]

        # Section 3: 동적 Summary Context (조건부)
        if summary_context:
            formatted_context = self._format_summary_context(summary_context)
            if formatted_context:
                sections.append(
                    f"\n## Reference Context (confidence: {confidence}):\n"
                    f"{formatted_context}\n\n"
                    "Answer the user's question using the above context."
                )

        # Section 4: 동적 Glossary Terms (조건부)
        if user_query:
            extra_terms = self._get_query_relevant_terms(user_query)
            if extra_terms:
                terms_text = "\n".join(
                    f"- {term}: {definition}"
                    for term, definition in extra_terms.items()
                )
                sections.append(
                    f"\n## Additional Relevant Terms:\n{terms_text}"
                )

        return "\n".join(sections)

    def _format_summary_context(self, summary_context: str) -> str:
        """Filter out empty/None entries from summary context."""
        if not summary_context:
            return ""

        lines = summary_context.split("\n")
        filtered = []
        for line in lines:
            # "[명령어 tjesmgr: None]" 같은 빈 항목 필터링
            if ": None]" in line or ": None}" in line:
                match = re.search(
                    r"\[(?:명령어|command|용어|term)\s+(\w+):\s*None\]", line
                )
                if match:
                    term = match.group(1)
                    if term in self._glossary_map:
                        line = line.replace(
                            ": None]", f": {self._glossary_map[term]}]"
                        )
                    else:
                        continue
                else:
                    continue
            filtered.append(line)

        return "\n".join(filtered)

    def _get_query_relevant_terms(self, query: str) -> Dict[str, str]:
        """Extract abbreviations from query and return matching glossary definitions."""
        # 대문자 약어 추출 (2글자 이상)
        abbreviations = set(re.findall(r"\b([A-Z][A-Za-z]{1,15})\b", query))
        # 소문자 매칭도 포함 (tjesmgr, hidbmgr 등)
        abbreviations.update(
            re.findall(r"\b([a-z]{2,}mgr)\b", query, re.IGNORECASE)
        )

        # 핵심 약어 목록에 이미 포함된 것은 제외 (프롬프트 중복 방지)
        core_upper = {k.upper() for k in self._CORE_TERMS}
        result: Dict[str, str] = {}

        for abbr in abbreviations:
            if abbr.upper() in core_upper:
                continue
            for key, value in self._glossary_map.items():
                if key.upper() == abbr.upper():
                    result[key] = value
                    break

            if len(result) >= 5:
                break

        return result

    async def read_summary_file(self, file_path: str) -> Optional[str]:
        """
        Read a summary file from the summaries directory.

        Args:
            file_path: Relative path within summaries directory
                      (e.g., "commands/OpenFrame_TJES_MVS.md")

        Returns:
            File content or None if not found
        """
        summaries_dir = Path("/opt/kms/uploads/summaries")

        # Also check local path for development
        local_path = Path("uploads/summaries")
        if local_path.exists():
            summaries_dir = local_path

        full_path = summaries_dir / file_path

        if full_path.exists() and full_path.is_file():
            try:
                return full_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read summary file {file_path}: {e}")

        return None

    async def search_summaries(self, query: str) -> Dict[str, Any]:
        """
        Search summaries without calling LLM.

        Useful for debugging or getting raw summary data.

        Args:
            query: Search query

        Returns:
            Comprehensive search results from SummarySearchService
        """
        from .summary_search_service import get_summary_search_service

        try:
            summary_service = get_summary_search_service()
            return await summary_service.comprehensive_search(query)
        except Exception as e:
            logger.error(f"Summary search error: {e}")
            return {
                "results": [],
                "confidence": "low",
                "error": str(e),
            }

    async def search_tables_and_images(
        self,
        doc_name: Optional[str] = None,
        page_number: Optional[int] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search for TABLE_CHUNK and IMAGE_CHUNK in Neo4j.
        For images, fetch actual binary data from PostgreSQL via FigureImageService.

        Args:
            doc_name: Document filename to filter (e.g., "HiDB")
            page_number: Page number to filter
            query: Optional semantic query for vector search

        Returns:
            Dict with tables and images lists (images include base64 data URI)
        """
        try:
            from langchain_neo4j import Neo4jGraph
            from app.src.config import config

            graph = Neo4jGraph(
                url=config.neo4j.uri,
                username=config.neo4j.user,
                password=config.neo4j.password,
            )

            # Build Cypher query for tables and images (include document ID)
            where_clauses = ["c.chunk_type IN ['TABLE_CHUNK', 'IMAGE_CHUNK', 'table', 'image_caption']"]
            params = {}

            if doc_name:
                where_clauses.append("toLower(d.filename) CONTAINS toLower($doc_name)")
                params["doc_name"] = doc_name

            if page_number:
                where_clauses.append("(c.page_start <= $page_number AND c.page_end >= $page_number)")
                params["page_number"] = page_number

            # Query-based search when no doc_name/page_number specified
            if query and not doc_name and not page_number:
                # Extract keywords from query for content matching
                keywords = re.findall(r'[A-Za-z]{3,}|[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]{2,}', query)
                if keywords:
                    # Build OR conditions for keyword matching in content
                    keyword_conditions = [
                        f"toLower(c.content) CONTAINS toLower('{kw}')"
                        for kw in keywords[:5]  # Limit to 5 keywords
                    ]
                    if keyword_conditions:
                        where_clauses.append(f"({' OR '.join(keyword_conditions)})")
                        logger.info(f"Query-based image search with keywords: {keywords[:5]}")

            where_clause = " AND ".join(where_clauses)

            cypher_query = f"""
            MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
            WHERE {where_clause}
            RETURN
                c.id AS chunk_id,
                c.content AS content,
                c.chunk_type AS chunk_type,
                c.page_start AS page_start,
                c.page_end AS page_end,
                d.filename AS doc_filename,
                d.id AS doc_id
            ORDER BY c.page_start, c.chunk_type
            LIMIT 10
            """

            results = graph.query(cypher_query, params)

            tables = []
            image_refs = []  # Collect image references for PostgreSQL lookup

            for r in results:
                chunk_type = r.get("chunk_type", "")
                item = {
                    "chunk_id": r.get("chunk_id"),
                    "content": r.get("content"),
                    "page_start": r.get("page_start"),
                    "page_end": r.get("page_end"),
                    "doc_filename": r.get("doc_filename"),
                    "doc_id": r.get("doc_id"),
                }

                if chunk_type in ["TABLE_CHUNK", "table"]:
                    tables.append(item)
                elif chunk_type in ["IMAGE_CHUNK", "image_caption"]:
                    image_refs.append(item)

            # Fetch actual image data from PostgreSQL via FigureImageService
            images = []
            if image_refs:
                try:
                    from ..core.deps import get_figure_image_service
                    figure_service = await get_figure_image_service()

                    # Group by document_id and page_numbers
                    doc_pages: Dict[str, set] = {}
                    for ref in image_refs:
                        doc_id = ref.get("doc_id")
                        page_start = ref.get("page_start")
                        if doc_id and page_start:
                            if doc_id not in doc_pages:
                                doc_pages[doc_id] = set()
                            doc_pages[doc_id].add(page_start)

                    # Fetch images from PostgreSQL
                    for doc_id, pages in doc_pages.items():
                        pg_images = await figure_service.get_images_for_pages(
                            document_id=doc_id,
                            page_numbers=list(pages),
                            include_data=True  # Include Base64 data
                        )

                        for pg_img in pg_images:
                            # Find matching Neo4j reference for metadata
                            matching_ref = next(
                                (r for r in image_refs
                                 if r.get("doc_id") == doc_id
                                 and r.get("page_start") == pg_img.get("page_number")),
                                {}
                            )
                            images.append({
                                "chunk_id": matching_ref.get("chunk_id"),
                                "content": pg_img.get("figure_caption") or pg_img.get("description") or matching_ref.get("content", ""),
                                "page_start": pg_img.get("page_number"),
                                "page_end": pg_img.get("page_number"),
                                "doc_filename": matching_ref.get("doc_filename"),
                                "image_url": pg_img.get("data"),  # Base64 Data URI
                            })

                    logger.info(f"Fetched {len(images)} images with base64 data from PostgreSQL")

                except Exception as img_err:
                    logger.warning(f"Failed to fetch image data from PostgreSQL: {img_err}")
                    # Fallback to Neo4j metadata only (no image_url)
                    for ref in image_refs:
                        images.append({
                            "chunk_id": ref.get("chunk_id"),
                            "content": ref.get("content"),
                            "page_start": ref.get("page_start"),
                            "page_end": ref.get("page_end"),
                            "doc_filename": ref.get("doc_filename"),
                            "image_url": None,
                        })

            logger.info(f"Found {len(tables)} tables, {len(images)} images")
            return {"tables": tables, "images": images}

        except Exception as e:
            logger.error(f"Table/image search error: {e}")
            return {"tables": [], "images": [], "error": str(e)}


# Singleton instance
_openagent_service: Optional[OpenAgentService] = None


def get_openagent_service() -> OpenAgentService:
    """Get or create the OpenAgent service singleton."""
    global _openagent_service
    if _openagent_service is None:
        _openagent_service = OpenAgentService()
    return _openagent_service
