"""
Ollama VLM (Vision Language Model) Service
Real implementation using Ollama bakllava model for multimodal document processing.

Features:
- Image description generation
- Image embedding extraction
- Multimodal chat completion
"""
import asyncio
import base64
import logging
import os
from typing import Optional, List, Dict, Any

import aiohttp

logger = logging.getLogger(__name__)

# Configuration from environment
# NIM Vision API (primary)
VISION_API_URL = os.getenv("VISION_API_URL", "http://localhost:12803/v1/chat/completions")
VISION_LLM_MODEL = os.getenv("VISION_LLM_MODEL", "nvidia/llama-3.1-nemotron-nano-vl-8b-v1")

# Ollama fallback
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_VLM_MODEL = os.getenv("OLLAMA_VLM_MODEL", "bakllava")


class OllamaVLMService:
    """
    VLM service for multimodal RAG.

    Supports:
    - NIM Vision API (nvidia/llama-3.1-nemotron-nano-vl-8b-v1) - Primary
    - Ollama bakllava model - Fallback

    Features:
    - Image captioning and description
    - Image understanding and analysis
    - Embedding generation via hidden states
    """

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        timeout: int = 120,
        use_nim: bool = True
    ):
        """
        Initialize VLM service.

        Args:
            base_url: API server URL (auto-detected from env if None)
            model: VLM model name (auto-detected from env if None)
            timeout: Request timeout in seconds
            use_nim: Try NIM Vision API first (default: True)
        """
        self.use_nim = use_nim and VISION_API_URL is not None

        if self.use_nim:
            # Use NIM Vision API
            self.base_url = (base_url or VISION_API_URL).rstrip('/').replace('/chat/completions', '').replace('/v1', '')
            self.model = model or VISION_LLM_MODEL
            self.api_endpoint = f"{self.base_url}/v1/chat/completions"
        else:
            # Fallback to Ollama
            self.base_url = (base_url or OLLAMA_BASE_URL).rstrip('/')
            self.model = model or OLLAMA_VLM_MODEL
            self.api_endpoint = f"{self.base_url}/api/generate"

        self.timeout = timeout
        self.embedding_dimension = 4096

    async def describe_image(
        self,
        image_data: bytes,
        prompt: Optional[str] = None,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a description for an image using bakllava.

        Args:
            image_data: Raw image bytes (PNG, JPEG, etc.)
            prompt: Custom prompt for description
            context: Additional context about the document

        Returns:
            Dict with description, alt_text, and confidence
        """
        # Encode image to base64
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        # Build prompt
        if prompt:
            full_prompt = prompt
        elif context:
            full_prompt = f"""Describe this image from a document. Context: {context}

Provide:
1. A detailed description of the image content
2. A short alt text (1-2 sentences)
3. Any text visible in the image

Be specific about diagrams, charts, tables, or figures."""
        else:
            full_prompt = """Describe this image in detail.

Include:
1. What type of image this is (photo, diagram, chart, table, etc.)
2. The main content and elements
3. Any text visible in the image
4. How this might relate to a document context"""

        # Call Ollama generate API with image
        try:
            result = await self._generate_with_image(
                prompt=full_prompt,
                image_b64=image_b64
            )

            description = result.get("response", "")

            # Parse alt_text from response (usually first line or short summary)
            alt_text = self._extract_alt_text(description)

            return {
                "description": description,
                "alt_text": alt_text,
                "confidence": 0.9 if description else 0.0,
                "model": self.model
            }

        except Exception as e:
            logger.error(f"Failed to describe image: {e}")
            return {
                "description": "",
                "alt_text": "",
                "confidence": 0.0,
                "error": str(e)
            }

    async def generate_embedding(
        self,
        image_data: bytes
    ) -> List[float]:
        """
        Generate embedding vector for an image using bakllava.

        Uses Ollama's /api/embeddings endpoint with the image.

        Args:
            image_data: Raw image bytes

        Returns:
            List of floats representing the 4096-dimensional embedding
        """
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        try:
            # First, try the embeddings endpoint
            embedding = await self._get_image_embedding(image_b64)
            if embedding and len(embedding) == self.embedding_dimension:
                return embedding

            # Fallback: use generate endpoint to extract hidden state embedding
            # This uses a special prompt that asks for a stable representation
            result = await self._generate_with_image(
                prompt="Describe this image in one comprehensive sentence that captures all important details.",
                image_b64=image_b64,
                options={"num_predict": 1}  # Minimal generation
            )

            # If we have embeddings in context, use those
            if "context" in result and result["context"]:
                # The context contains the embedding representation
                context = result["context"]
                if isinstance(context, list) and len(context) >= self.embedding_dimension:
                    return context[:self.embedding_dimension]

            # Final fallback: generate based on description text embedding
            description = result.get("response", "image")
            return await self._get_text_embedding(description)

        except Exception as e:
            logger.error(f"Failed to generate image embedding: {e}")
            # Return zero vector on failure
            return [0.0] * self.embedding_dimension

    async def _generate_with_image(
        self,
        prompt: str,
        image_b64: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call Vision API with an image.

        Supports both NIM Vision API and Ollama API formats.

        Args:
            prompt: Text prompt
            image_b64: Base64-encoded image
            options: Additional generation options

        Returns:
            Response dict with 'response' key containing the generated text
        """
        if self.use_nim:
            # NIM Vision API (OpenAI-compatible format)
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": options.get("num_predict", 1024) if options else 1024,
                "temperature": 0.7
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_endpoint,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"NIM Vision error: {response.status} - {error_text}")
                        raise Exception(f"NIM Vision API error: {response.status}")

                    result = await response.json()
                    # Convert to Ollama-compatible format
                    return {
                        "response": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                        "model": self.model
                    }
        else:
            # Ollama API format
            url = f"{self.base_url}/api/generate"

            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False
            }

            if options:
                payload["options"] = options

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama VLM error: {response.status} - {error_text}")
                        raise Exception(f"Ollama API error: {response.status}")

                    return await response.json()

    async def _get_image_embedding(
        self,
        image_b64: str
    ) -> Optional[List[float]]:
        """
        Try to get embedding directly from Ollama embeddings endpoint.

        Note: This may not work with all models. bakllava may require
        the generate-based approach instead.
        """
        url = f"{self.base_url}/api/embeddings"

        payload = {
            "model": self.model,
            "prompt": "Describe this image",
            "images": [image_b64]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("embedding")
                    return None
        except Exception as e:
            logger.debug(f"Image embedding endpoint not available: {e}")
            return None

    async def _get_text_embedding(
        self,
        text: str
    ) -> List[float]:
        """
        Get text embedding using Ollama embeddings endpoint.
        Fallback when direct image embedding isn't available.
        """
        url = f"{self.base_url}/api/embeddings"

        payload = {
            "model": self.model,
            "prompt": text
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        embedding = data.get("embedding", [])
                        # Pad or truncate to target dimension
                        if len(embedding) < self.embedding_dimension:
                            embedding.extend([0.0] * (self.embedding_dimension - len(embedding)))
                        return embedding[:self.embedding_dimension]
                    else:
                        logger.error(f"Text embedding error: {response.status}")
                        return [0.0] * self.embedding_dimension
        except Exception as e:
            logger.error(f"Text embedding failed: {e}")
            return [0.0] * self.embedding_dimension

    def _extract_alt_text(self, description: str) -> str:
        """
        Extract a short alt text from the full description.

        Args:
            description: Full image description

        Returns:
            Short alt text (1-2 sentences)
        """
        if not description:
            return ""

        # Take first sentence or first 150 characters
        sentences = description.split('.')
        if sentences:
            first_sentence = sentences[0].strip()
            if len(first_sentence) > 20:
                return first_sentence + "."

        # Fallback: truncate
        if len(description) > 150:
            return description[:147] + "..."
        return description

    async def analyze_image(
        self,
        image_data: bytes,
        analysis_type: str = "general"
    ) -> Dict[str, Any]:
        """
        Perform specific analysis on an image.

        Args:
            image_data: Raw image bytes
            analysis_type: Type of analysis (general, chart, table, diagram, text)

        Returns:
            Analysis result dict
        """
        prompts = {
            "general": "Describe this image comprehensively.",
            "chart": """Analyze this chart image:
1. What type of chart is this? (bar, line, pie, etc.)
2. What data is being shown?
3. What are the labels and values?
4. What trends or patterns are visible?""",
            "table": """Analyze this table image:
1. What are the column headers?
2. What data does each row contain?
3. How many rows and columns are there?
4. Extract the table content in markdown format.""",
            "diagram": """Analyze this diagram:
1. What type of diagram is this? (flowchart, architecture, process, etc.)
2. What are the main components?
3. How are they connected?
4. What is the overall purpose?""",
            "text": """Extract all visible text from this image:
1. Main text content
2. Labels and captions
3. Any numbers or data
Format the extracted text clearly."""
        }

        prompt = prompts.get(analysis_type, prompts["general"])
        image_b64 = base64.b64encode(image_data).decode('utf-8')

        try:
            result = await self._generate_with_image(
                prompt=prompt,
                image_b64=image_b64
            )

            return {
                "analysis_type": analysis_type,
                "content": result.get("response", ""),
                "confidence": 0.85,
                "model": self.model
            }

        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return {
                "analysis_type": analysis_type,
                "content": "",
                "confidence": 0.0,
                "error": str(e)
            }

    async def extract_text_ocr(
        self,
        image_data: bytes,
        language: str = "auto"
    ) -> Dict[str, Any]:
        """
        Extract text from an image using OCR via VLM.

        This method is optimized for document pages, scanned images,
        and any image containing text that needs to be extracted.

        Args:
            image_data: Raw image bytes (PNG, JPEG, etc.)
            language: Expected language (auto, en, ko, ja, zh)

        Returns:
            Dict with extracted text, confidence, and metadata
        """
        language_hints = {
            "auto": "any language",
            "en": "English",
            "ko": "Korean (한국어)",
            "ja": "Japanese (日本語)",
            "zh": "Chinese (中文)"
        }
        lang_hint = language_hints.get(language, "any language")

        ocr_prompt = f"""Extract ALL text from this image. This is a document page that may contain:
- Main body text
- Headers and titles
- Table contents (preserve structure with | separators)
- Code blocks (preserve formatting)
- Bullet points and numbered lists
- Captions and labels
- Footnotes

Language hint: {lang_hint}

Rules:
1. Extract text exactly as it appears - preserve original formatting
2. For tables, use markdown table format with | separators
3. For code, use triple backticks
4. Preserve paragraph breaks with blank lines
5. Include ALL visible text, even small labels

Extracted text:"""

        image_b64 = base64.b64encode(image_data).decode('utf-8')

        try:
            result = await self._generate_with_image(
                prompt=ocr_prompt,
                image_b64=image_b64,
                options={"num_predict": 4096}  # Allow longer output for full page OCR
            )

            extracted_text = result.get("response", "").strip()

            # Calculate confidence based on text length and content
            confidence = 0.9 if len(extracted_text) > 50 else 0.5 if extracted_text else 0.0

            return {
                "text": extracted_text,
                "confidence": confidence,
                "language": language,
                "model": self.model,
                "char_count": len(extracted_text)
            }

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            return {
                "text": "",
                "confidence": 0.0,
                "language": language,
                "error": str(e)
            }

    async def extract_tables_from_image(
        self,
        image_data: bytes
    ) -> Dict[str, Any]:
        """
        Extract tables from an image and return as structured data.

        Args:
            image_data: Raw image bytes containing table(s)

        Returns:
            Dict with extracted tables in markdown format
        """
        table_prompt = """Extract all tables from this image.

For each table found:
1. Identify column headers
2. Extract all row data
3. Format as markdown table

Output format:
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| data1    | data2    | data3    |

If multiple tables exist, separate them with a blank line.
If no tables are found, respond with "No tables found."

Tables:"""

        image_b64 = base64.b64encode(image_data).decode('utf-8')

        try:
            result = await self._generate_with_image(
                prompt=table_prompt,
                image_b64=image_b64,
                options={"num_predict": 2048}
            )

            table_content = result.get("response", "").strip()

            return {
                "tables_markdown": table_content,
                "has_tables": "No tables found" not in table_content,
                "confidence": 0.85 if table_content else 0.0,
                "model": self.model
            }

        except Exception as e:
            logger.error(f"Table extraction failed: {e}")
            return {
                "tables_markdown": "",
                "has_tables": False,
                "confidence": 0.0,
                "error": str(e)
            }

    async def batch_describe(
        self,
        images: List[bytes],
        batch_size: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Describe multiple images in batches.

        Args:
            images: List of image byte arrays
            batch_size: Number of concurrent requests

        Returns:
            List of description results
        """
        results = []

        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            tasks = [self.describe_image(img) for img in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    results.append({
                        "description": "",
                        "alt_text": "",
                        "confidence": 0.0,
                        "error": str(result)
                    })
                else:
                    results.append(result)

        return results

    async def batch_embed(
        self,
        images: List[bytes],
        batch_size: int = 2
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple images.

        Args:
            images: List of image byte arrays
            batch_size: Number of concurrent requests

        Returns:
            List of embedding vectors
        """
        results = []

        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            tasks = [self.generate_embedding(img) for img in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Batch embedding error: {result}")
                    results.append([0.0] * self.embedding_dimension)
                else:
                    results.append(result)

        return results

    async def health_check(self) -> bool:
        """Check if VLM service is available."""
        try:
            if self.use_nim:
                # Check NIM Vision API health
                health_url = self.base_url + "/v1/health/ready"
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        health_url,
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            logger.info(f"NIM Vision API healthy: {self.model}")
                            return True
                        return False
            else:
                # Check Ollama
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{self.base_url}/api/tags",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            models = [m.get("name", "") for m in data.get("models", [])]
                            for model in models:
                                if self.model in model:
                                    return True
                            logger.warning(f"Model {self.model} not found in Ollama")
                        return False
        except Exception as e:
            logger.error(f"VLM health check failed: {e}")
            return False


# Singleton instance
_vlm_service_instance: Optional[OllamaVLMService] = None


def get_ollama_vlm_service(use_nim: bool = True) -> OllamaVLMService:
    """
    Get singleton VLM service instance.

    Args:
        use_nim: Use NIM Vision API if available (default: True)

    Returns:
        OllamaVLMService instance configured for NIM or Ollama
    """
    global _vlm_service_instance
    if _vlm_service_instance is None:
        _vlm_service_instance = OllamaVLMService(use_nim=use_nim)
        logger.info(f"VLM Service initialized: {'NIM' if _vlm_service_instance.use_nim else 'Ollama'} - {_vlm_service_instance.model}")
    return _vlm_service_instance
