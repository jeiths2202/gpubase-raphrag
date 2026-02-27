#!/usr/bin/env python3
"""
CLI Document Processor for KMS System
=====================================

GPU 서버에서 커맨드로 실행 가능한 문서 처리 프로그램
Documents 탭의 청킹 + 임베딩 로직과 동일하게 동작

Usage:
    python cli_document_processor.py /path/to/file.pdf --language ko
    python cli_document_processor.py /path/to/directory --language jp --enable-vlm
    python cli_document_processor.py /path/to/file.pdf -l en --tags manual,important

Author: KMS Development Team
Created: 2026-01-31
"""

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import httpx

# PDF processing
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# Database connections
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

try:
    from neo4j import AsyncGraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False

# Image processing
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class ProcessorConfig:
    """Configuration for document processor"""

    # API Endpoints (GPU Server)
    embedding_url: str = "http://192.168.8.11:12801/v1"
    vision_url: str = "http://192.168.8.11:12803/v1"

    # Models
    embedding_model: str = "nvidia/nv-embedqa-mistral-7b-v2"
    vision_model: str = "Qwen/Qwen2-VL-2B-Instruct"

    # Embedding settings
    embedding_dimension: int = 4096
    embedding_batch_size: int = 32
    embedding_max_text_length: int = 400  # NIM nv-embedqa has 512 token limit (~400 chars for CJK)
    embedding_timeout: float = 60.0

    # Chunking settings
    chunk_size: int = 350  # Keep under embedding token limit
    chunk_overlap: int = 50

    # Vision settings
    vision_enabled: bool = False
    vision_max_images: int = 10
    vision_max_dimension: int = 1344
    vision_timeout: float = 180.0
    vision_dpi: int = 150

    # Database (optional)
    postgres_host: str = "192.168.8.11"
    postgres_port: int = 5432
    postgres_db: str = "ragdb"
    postgres_user: str = "raguser"
    postgres_password: str = "ragpassword123"

    neo4j_uri: str = "bolt://192.168.8.11:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # Processing
    language: str = "ko"
    tags: List[str] = field(default_factory=lambda: ["manual"])
    processing_mode: str = "vlm_enhanced"

    # Output
    output_dir: Optional[str] = None
    save_to_db: bool = False
    verbose: bool = False


class ProcessingStatus(Enum):
    """Document processing status"""
    PENDING = "pending"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    VISION_ANALYSIS = "vision_analysis"
    SAVING = "saving"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ChunkData:
    """Represents a text chunk"""
    id: str
    content: str
    index: int
    start_char: int
    end_char: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


@dataclass
class ImageData:
    """Represents an extracted image"""
    id: str
    page_number: int
    image_bytes: bytes
    format: str = "png"
    width: int = 0
    height: int = 0
    analysis: Optional[str] = None


@dataclass
class ProcessingResult:
    """Result of document processing"""
    document_id: str
    filename: str
    status: ProcessingStatus
    chunks: List[ChunkData] = field(default_factory=list)
    images: List[ImageData] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    processing_time_seconds: float = 0.0


# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(verbose: bool = False) -> logging.Logger:
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # Create logger
    logger = logging.getLogger('cli_processor')
    logger.setLevel(level)
    logger.addHandler(console_handler)

    return logger


# ============================================================================
# Document Parser
# ============================================================================

class DocumentParser:
    """Parse various document formats"""

    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.md', '.json'}

    def __init__(self, config: ProcessorConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    async def parse(self, file_path: Path) -> Tuple[str, Dict[str, Any], List[ImageData]]:
        """
        Parse document and extract text content

        Returns:
            Tuple of (text_content, metadata, images)
        """
        ext = file_path.suffix.lower()

        if ext == '.pdf':
            return await self._parse_pdf(file_path)
        elif ext in {'.txt', '.md'}:
            return await self._parse_text(file_path)
        elif ext == '.json':
            return await self._parse_json(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    async def _parse_pdf(self, file_path: Path) -> Tuple[str, Dict[str, Any], List[ImageData]]:
        """Parse PDF document"""
        text_content = ""
        metadata = {}
        images = []

        if PYMUPDF_AVAILABLE:
            # Use PyMuPDF (faster, better image extraction)
            doc = fitz.open(str(file_path))

            metadata = {
                "title": doc.metadata.get("title", file_path.stem),
                "author": doc.metadata.get("author", ""),
                "page_count": len(doc),
                "format": "pdf",
                "producer": doc.metadata.get("producer", ""),
            }

            for page_num, page in enumerate(doc):
                # Extract text
                text_content += page.get_text() + "\n\n"

                # Extract images if VLM enabled
                if self.config.vision_enabled:
                    images.extend(await self._extract_images_pymupdf(page, page_num))

            doc.close()

        elif PYPDF_AVAILABLE:
            # Fallback to pypdf
            reader = PdfReader(str(file_path))

            metadata = {
                "title": reader.metadata.get("/Title", file_path.stem) if reader.metadata else file_path.stem,
                "author": reader.metadata.get("/Author", "") if reader.metadata else "",
                "page_count": len(reader.pages),
                "format": "pdf",
            }

            for page_num, page in enumerate(reader.pages):
                text_content += page.extract_text() + "\n\n"
        else:
            raise RuntimeError("No PDF library available. Install PyMuPDF or pypdf.")

        return text_content.strip(), metadata, images

    async def _extract_images_pymupdf(self, page: Any, page_num: int) -> List[ImageData]:
        """Extract images from PDF page using PyMuPDF"""
        images = []

        if not PIL_AVAILABLE:
            self.logger.warning("PIL not available, skipping image extraction")
            return images

        try:
            # Render page as image
            mat = fitz.Matrix(self.config.vision_dpi / 72, self.config.vision_dpi / 72)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Resize if too large
            if max(img.width, img.height) > self.config.vision_max_dimension:
                ratio = self.config.vision_max_dimension / max(img.width, img.height)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Convert to bytes
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()

            images.append(ImageData(
                id=str(uuid.uuid4()),
                page_number=page_num,
                image_bytes=image_bytes,
                format="png",
                width=img.width,
                height=img.height
            ))

        except Exception as e:
            self.logger.warning(f"Failed to extract image from page {page_num}: {e}")

        return images

    async def _parse_text(self, file_path: Path) -> Tuple[str, Dict[str, Any], List[ImageData]]:
        """Parse text file"""
        content = file_path.read_text(encoding='utf-8')
        metadata = {
            "title": file_path.stem,
            "format": file_path.suffix[1:],
            "char_count": len(content),
        }
        return content, metadata, []

    async def _parse_json(self, file_path: Path) -> Tuple[str, Dict[str, Any], List[ImageData]]:
        """Parse JSON file (extract text content)"""
        data = json.loads(file_path.read_text(encoding='utf-8'))

        # Try to extract text from common JSON structures
        if isinstance(data, dict):
            content = data.get('content', data.get('text', json.dumps(data, ensure_ascii=False, indent=2)))
        else:
            content = json.dumps(data, ensure_ascii=False, indent=2)

        metadata = {
            "title": file_path.stem,
            "format": "json",
        }
        return str(content), metadata, []


# ============================================================================
# Text Chunker
# ============================================================================

class TextChunker:
    """Split text into overlapping chunks"""

    def __init__(self, config: ProcessorConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def chunk(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> List[ChunkData]:
        """Split text into chunks with overlap"""
        chunks = []
        text = self._clean_text(text)

        if not text:
            return chunks

        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap

        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence endings
                for delimiter in [". ", "。", ".\n", "\n\n"]:
                    last_pos = chunk_text.rfind(delimiter)
                    if last_pos > chunk_size * 0.5:
                        chunk_text = chunk_text[:last_pos + len(delimiter)]
                        end = start + last_pos + len(delimiter)
                        break

            chunk_text = chunk_text.strip()

            if chunk_text:
                chunks.append(ChunkData(
                    id=str(uuid.uuid4()),
                    content=chunk_text,
                    index=chunk_index,
                    start_char=start,
                    end_char=end,
                    metadata={
                        "char_count": len(chunk_text),
                        **(metadata or {})
                    }
                ))
                chunk_index += 1

            # Move start position with overlap
            start = end - overlap if end < len(text) else len(text)

        self.logger.info(f"Created {len(chunks)} chunks from {len(text)} characters")
        return chunks

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove excessive whitespace
        import re
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


# ============================================================================
# Embedding Service
# ============================================================================

class EmbeddingService:
    """Generate embeddings using NIM API"""

    def __init__(self, config: ProcessorConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    async def embed_chunks(self, chunks: List[ChunkData]) -> List[ChunkData]:
        """Generate embeddings for all chunks"""
        if not chunks:
            return chunks

        self.logger.info(f"Embedding {len(chunks)} chunks (batch_size={self.config.embedding_batch_size})")

        # Process in batches
        batch_size = self.config.embedding_batch_size
        total_batches = (len(chunks) + batch_size - 1) // batch_size

        async with aiohttp.ClientSession() as session:
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(chunks))
                batch_chunks = chunks[start_idx:end_idx]

                self.logger.debug(f"Processing batch {batch_num + 1}/{total_batches} ({len(batch_chunks)} chunks)")

                try:
                    embeddings = await self._embed_batch(session, batch_chunks)

                    for i, embedding in enumerate(embeddings):
                        batch_chunks[i].embedding = embedding

                except Exception as e:
                    self.logger.error(f"Batch {batch_num + 1} failed: {e}")
                    # Try individual embeddings as fallback
                    for chunk in batch_chunks:
                        try:
                            embeddings = await self._embed_batch(session, [chunk])
                            chunk.embedding = embeddings[0] if embeddings else None
                        except Exception as inner_e:
                            self.logger.error(f"Individual embedding failed for chunk {chunk.index}: {inner_e}")

        # Count successful embeddings
        success_count = sum(1 for c in chunks if c.embedding is not None)
        self.logger.info(f"Embedded {success_count}/{len(chunks)} chunks successfully")

        return chunks

    async def _embed_batch(self, session: aiohttp.ClientSession, chunks: List[ChunkData]) -> List[List[float]]:
        """Embed a batch of chunks"""
        texts = [self._truncate_text(c.content) for c in chunks]

        url = f"{self.config.embedding_url}/embeddings"
        payload = {
            "input": texts,
            "model": self.config.embedding_model,
            "input_type": "passage"  # Required for NIM nv-embedqa model (passage for indexing, query for search)
        }

        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=self.config.embedding_timeout)
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise RuntimeError(f"Embedding API error ({response.status}): {error_text}")

            result = await response.json()

            # Extract embeddings from response
            embeddings = [item["embedding"] for item in result.get("data", [])]
            return embeddings

    def _truncate_text(self, text: str) -> str:
        """Truncate text to max length"""
        if len(text) > self.config.embedding_max_text_length:
            return text[:self.config.embedding_max_text_length]
        return text


# ============================================================================
# Vision Service
# ============================================================================

class VisionService:
    """Analyze images using Vision LLM"""

    ANALYSIS_PROMPTS = {
        "ko": """이 이미지를 분석해주세요. 다음 내용을 포함해주세요:
1. 이미지의 주요 내용 설명
2. 텍스트가 있다면 추출
3. 표나 차트가 있다면 데이터 설명
4. 다이어그램이라면 구조 설명""",

        "ja": """この画像を分析してください。以下の内容を含めてください:
1. 画像の主な内容の説明
2. テキストがあれば抽出
3. 表やチャートがあればデータの説明
4. ダイアグラムであれば構造の説明""",

        "en": """Please analyze this image. Include the following:
1. Description of main content
2. Extract any text if present
3. If there are tables or charts, describe the data
4. If it's a diagram, explain the structure"""
    }

    def __init__(self, config: ProcessorConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger

    async def analyze_images(self, images: List[ImageData]) -> List[ImageData]:
        """Analyze all images using Vision LLM"""
        if not images:
            return images

        # Limit number of images
        if len(images) > self.config.vision_max_images:
            self.logger.warning(f"Limiting images from {len(images)} to {self.config.vision_max_images}")
            images = images[:self.config.vision_max_images]

        self.logger.info(f"Analyzing {len(images)} images with Vision LLM")

        async with aiohttp.ClientSession() as session:
            for i, image in enumerate(images):
                self.logger.debug(f"Analyzing image {i + 1}/{len(images)} (page {image.page_number})")

                try:
                    analysis = await self._analyze_image(session, image)
                    image.analysis = analysis
                except Exception as e:
                    self.logger.error(f"Image analysis failed for page {image.page_number}: {e}")
                    image.analysis = f"[Analysis failed: {str(e)}]"

        success_count = sum(1 for img in images if img.analysis and not img.analysis.startswith("[Analysis failed"))
        self.logger.info(f"Analyzed {success_count}/{len(images)} images successfully")

        return images

    async def _analyze_image(self, session: aiohttp.ClientSession, image: ImageData) -> str:
        """Analyze single image"""
        # Encode image to base64
        image_base64 = base64.b64encode(image.image_bytes).decode('utf-8')

        # Get prompt for language
        prompt = self.ANALYSIS_PROMPTS.get(self.config.language, self.ANALYSIS_PROMPTS["en"])

        # Build message for OpenAI-compatible API (Qwen2-VL)
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image.format};base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]

        url = f"{self.config.vision_url}/chat/completions"
        payload = {
            "model": self.config.vision_model,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.3
        }

        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=self.config.vision_timeout)
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise RuntimeError(f"Vision API error ({response.status}): {error_text}")

            result = await response.json()

            # Extract content from response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content


# ============================================================================
# Database Service
# ============================================================================

class DatabaseService:
    """Save results to PostgreSQL and Neo4j"""

    def __init__(self, config: ProcessorConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self._pg_pool = None
        self._neo4j_driver = None

    async def connect(self):
        """Establish database connections"""
        # PostgreSQL
        if ASYNCPG_AVAILABLE and self.config.postgres_password:
            try:
                self._pg_pool = await asyncpg.create_pool(
                    host=self.config.postgres_host,
                    port=self.config.postgres_port,
                    database=self.config.postgres_db,
                    user=self.config.postgres_user,
                    password=self.config.postgres_password,
                    min_size=1,
                    max_size=5
                )
                self.logger.info("Connected to PostgreSQL")
            except Exception as e:
                self.logger.warning(f"PostgreSQL connection failed: {e}")

        # Neo4j
        if NEO4J_AVAILABLE and self.config.neo4j_password:
            try:
                self._neo4j_driver = AsyncGraphDatabase.driver(
                    self.config.neo4j_uri,
                    auth=(self.config.neo4j_user, self.config.neo4j_password)
                )
                self.logger.info("Connected to Neo4j")
            except Exception as e:
                self.logger.warning(f"Neo4j connection failed: {e}")

    async def close(self):
        """Close database connections"""
        if self._pg_pool:
            await self._pg_pool.close()
        if self._neo4j_driver:
            await self._neo4j_driver.close()

    async def save_document(self, result: ProcessingResult) -> bool:
        """Save processing result to databases"""
        saved = False

        # Save to PostgreSQL
        if self._pg_pool:
            try:
                await self._save_to_postgres(result)
                saved = True
            except Exception as e:
                self.logger.error(f"PostgreSQL save failed: {e}")

        # Save to Neo4j
        if self._neo4j_driver:
            try:
                await self._save_to_neo4j(result)
                saved = True
            except Exception as e:
                self.logger.error(f"Neo4j save failed: {e}")

        return saved

    async def _save_to_postgres(self, result: ProcessingResult):
        """Save to PostgreSQL"""
        async with self._pg_pool.acquire() as conn:
            # Insert document (matching actual table schema)
            await conn.execute("""
                INSERT INTO documents (
                    id, filename, original_name, file_size, mime_type,
                    document_type, status, chunks_count, embedding_status,
                    language, tags, processing_mode, vlm_processed, stats
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    chunks_count = EXCLUDED.chunks_count,
                    embedding_status = EXCLUDED.embedding_status,
                    vlm_processed = EXCLUDED.vlm_processed,
                    stats = EXCLUDED.stats,
                    updated_at = now()
            """,
                result.document_id,
                result.filename,
                result.filename,  # original_name
                result.metadata.get("file_size", 0),
                result.metadata.get("mime_type", "application/pdf"),
                result.metadata.get("document_type", "manual"),
                result.status.value,
                len(result.chunks),
                "completed" if any(c.embedding for c in result.chunks) else "pending",
                self.config.language,
                json.dumps(self.config.tags),
                "vlm" if self.config.vision_enabled else "text_only",
                self.config.vision_enabled,
                json.dumps(result.metadata)
            )

            # Insert chunks with embeddings
            for chunk in result.chunks:
                has_embedding = chunk.embedding is not None
                # Convert embedding list to pgvector string format
                embedding_str = str(chunk.embedding) if chunk.embedding else None
                await conn.execute("""
                    INSERT INTO text_chunks (
                        id, document_id, chunk_index, content, content_length,
                        chunk_type, page_number, embedding, has_embedding, metadata
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, $9, $10)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        has_embedding = EXCLUDED.has_embedding,
                        updated_at = now()
                """,
                    chunk.id,
                    result.document_id,
                    chunk.index,
                    chunk.content,
                    len(chunk.content),
                    chunk.metadata.get("chunk_type", "text"),
                    chunk.metadata.get("page_number"),
                    embedding_str,
                    has_embedding,
                    json.dumps(chunk.metadata)
                )

        self.logger.info(f"Saved document and {len(result.chunks)} chunks to PostgreSQL")

    async def _save_to_neo4j(self, result: ProcessingResult):
        """Save to Neo4j"""
        async with self._neo4j_driver.session() as session:
            # Create Document node
            await session.run("""
                MERGE (d:Document {id: $id})
                SET d.filename = $filename,
                    d.title = $title,
                    d.language = $language,
                    d.tags = $tags,
                    d.status = $status,
                    d.created_at = datetime()
            """,
                id=result.document_id,
                filename=result.filename,
                title=result.metadata.get("title", result.filename),
                language=self.config.language,
                tags=self.config.tags,
                status=result.status.value
            )

            # Create Chunk nodes and relationships
            for chunk in result.chunks:
                await session.run("""
                    MATCH (d:Document {id: $doc_id})
                    MERGE (c:Chunk {id: $chunk_id})
                    SET c.content = $content,
                        c.index = $index,
                        c.embedding = $embedding
                    MERGE (d)-[:HAS_CHUNK]->(c)
                """,
                    doc_id=result.document_id,
                    chunk_id=chunk.id,
                    content=chunk.content[:500],  # Truncate for Neo4j
                    index=chunk.index,
                    embedding=chunk.embedding
                )

        self.logger.info(f"Saved document and {len(result.chunks)} chunks to Neo4j")

    async def update_status(self, document_id: str, status: ProcessingStatus):
        """Update document status in databases after processing completes"""
        # Update Neo4j
        if self._neo4j_driver:
            try:
                async with self._neo4j_driver.session() as session:
                    await session.run("""
                        MATCH (d:Document {id: $id})
                        SET d.status = $status
                    """, id=document_id, status=status.value)
                self.logger.debug(f"Updated Neo4j status to: {status.value}")
            except Exception as e:
                self.logger.warning(f"Failed to update Neo4j status: {e}")

        # Update PostgreSQL
        if self._pg_pool:
            try:
                async with self._pg_pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE documents SET status = $1 WHERE id = $2
                    """, status.value, document_id)
                self.logger.debug(f"Updated PostgreSQL status to: {status.value}")
            except Exception as e:
                self.logger.warning(f"Failed to update PostgreSQL status: {e}")


# ============================================================================
# Main Processor
# ============================================================================

class DocumentProcessor:
    """Main document processor orchestrating all stages"""

    def __init__(self, config: ProcessorConfig):
        self.config = config
        self.logger = setup_logging(config.verbose)

        self.parser = DocumentParser(config, self.logger)
        self.chunker = TextChunker(config, self.logger)
        self.embedder = EmbeddingService(config, self.logger)
        self.vision = VisionService(config, self.logger)
        self.database = DatabaseService(config, self.logger)

    async def process_file(self, file_path: Path) -> ProcessingResult:
        """Process a single file"""
        start_time = time.time()
        document_id = str(uuid.uuid4())

        result = ProcessingResult(
            document_id=document_id,
            filename=file_path.name,
            status=ProcessingStatus.PENDING,
            metadata={
                "source_path": str(file_path),
                "language": self.config.language,
                "tags": self.config.tags,
                "processing_mode": self.config.processing_mode,
                "vlm_enabled": self.config.vision_enabled,
            }
        )

        try:
            # Step 1: Parse document
            self.logger.info(f"[1/5] Parsing: {file_path.name}")
            result.status = ProcessingStatus.PARSING

            text_content, doc_metadata, images = await self.parser.parse(file_path)
            result.metadata.update(doc_metadata)
            result.images = images

            self.logger.info(f"  → Extracted {len(text_content)} chars, {len(images)} images")

            # Step 2: Chunk text
            self.logger.info(f"[2/5] Chunking...")
            result.status = ProcessingStatus.CHUNKING

            chunks = self.chunker.chunk(text_content, {"document_id": document_id})
            result.chunks = chunks

            # Step 3: Generate embeddings
            self.logger.info(f"[3/5] Embedding {len(chunks)} chunks...")
            result.status = ProcessingStatus.EMBEDDING

            result.chunks = await self.embedder.embed_chunks(chunks)

            # Step 4: Vision analysis (if enabled)
            if self.config.vision_enabled and images:
                self.logger.info(f"[4/5] Analyzing {len(images)} images with VLM...")
                result.status = ProcessingStatus.VISION_ANALYSIS

                result.images = await self.vision.analyze_images(images)
            else:
                self.logger.info(f"[4/5] Skipping VLM analysis (disabled or no images)")

            # Step 5: Save to database (if enabled)
            if self.config.save_to_db:
                self.logger.info(f"[5/5] Saving to database...")
                result.status = ProcessingStatus.SAVING

                await self.database.connect()
                await self.database.save_document(result)

                # Update status to COMPLETED after save succeeds
                result.status = ProcessingStatus.COMPLETED
                await self.database.update_status(result.document_id, result.status)

                await self.database.close()
            else:
                self.logger.info(f"[5/5] Skipping database save (disabled)")
                result.status = ProcessingStatus.COMPLETED

            # Done
            result.processing_time_seconds = time.time() - start_time

            self.logger.info(f"✅ Completed: {file_path.name} in {result.processing_time_seconds:.2f}s")

        except Exception as e:
            result.status = ProcessingStatus.FAILED
            result.errors.append(str(e))
            result.processing_time_seconds = time.time() - start_time
            self.logger.error(f"❌ Failed: {file_path.name} - {e}")

            if self.config.verbose:
                import traceback
                self.logger.debug(traceback.format_exc())

        return result

    async def process_directory(self, dir_path: Path) -> List[ProcessingResult]:
        """Process all supported files in directory"""
        results = []

        # Find all supported files
        files = []
        for ext in self.parser.SUPPORTED_EXTENSIONS:
            files.extend(dir_path.glob(f"*{ext}"))
            files.extend(dir_path.glob(f"**/*{ext}"))  # Recursive

        files = sorted(set(files))

        if not files:
            self.logger.warning(f"No supported files found in {dir_path}")
            return results

        self.logger.info(f"Found {len(files)} files to process")

        for i, file_path in enumerate(files, 1):
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"Processing file {i}/{len(files)}: {file_path.name}")
            self.logger.info(f"{'='*60}")

            result = await self.process_file(file_path)
            results.append(result)

        return results

    def save_results_to_file(self, results: List[ProcessingResult], output_path: Path):
        """Save processing results to JSON file"""
        output_data = []

        for result in results:
            output_data.append({
                "document_id": result.document_id,
                "filename": result.filename,
                "status": result.status.value,
                "metadata": result.metadata,
                "chunk_count": len(result.chunks),
                "image_count": len(result.images),
                "chunks": [
                    {
                        "id": c.id,
                        "index": c.index,
                        "content": c.content[:200] + "..." if len(c.content) > 200 else c.content,
                        "char_count": len(c.content),
                        "has_embedding": c.embedding is not None,
                        "embedding_dim": len(c.embedding) if c.embedding else 0,
                    }
                    for c in result.chunks
                ],
                "images": [
                    {
                        "id": img.id,
                        "page": img.page_number,
                        "size": f"{img.width}x{img.height}",
                        "analysis_preview": img.analysis[:200] + "..." if img.analysis and len(img.analysis) > 200 else img.analysis,
                    }
                    for img in result.images
                ],
                "errors": result.errors,
                "processing_time_seconds": result.processing_time_seconds,
            })

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Results saved to: {output_path}")


# ============================================================================
# CLI Entry Point
# ============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="KMS Document Processor CLI - GPU Server Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process single PDF
  python cli_document_processor.py /path/to/manual.pdf -l ko

  # Process directory with VLM enabled
  python cli_document_processor.py /path/to/docs/ -l ja --enable-vlm

  # Full processing with database save
  python cli_document_processor.py /path/to/file.pdf -l en --enable-vlm --save-db

  # Custom output directory
  python cli_document_processor.py /path/to/file.pdf -o /output/dir

Environment Variables:
  POSTGRES_PASSWORD  - PostgreSQL password
  NEO4J_PASSWORD     - Neo4j password
  EMBEDDING_URL      - Embedding API URL (default: http://192.168.8.11:12801/v1)
  VISION_URL         - Vision API URL (default: http://192.168.8.11:12803/v1)
        """
    )

    # Required arguments
    parser.add_argument(
        "input",
        type=str,
        help="Input file or directory path"
    )

    # Language
    parser.add_argument(
        "-l", "--language",
        type=str,
        choices=["ko", "ja", "en"],
        default="ko",
        help="Document language (default: ko)"
    )

    # Tags
    parser.add_argument(
        "-t", "--tags",
        type=str,
        default="manual",
        help="Comma-separated tags (default: manual)"
    )

    # VLM
    parser.add_argument(
        "--enable-vlm",
        action="store_true",
        help="Enable VLM analysis for images, charts, tables"
    )

    # Database
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Save results to PostgreSQL and Neo4j"
    )

    # Output
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output directory for results JSON"
    )

    # API endpoints
    parser.add_argument(
        "--embedding-url",
        type=str,
        default=os.environ.get("EMBEDDING_URL", "http://192.168.8.11:12801/v1"),
        help="Embedding API URL"
    )

    parser.add_argument(
        "--vision-url",
        type=str,
        default=os.environ.get("VISION_URL", "http://192.168.8.11:12803/v1"),
        help="Vision API URL"
    )

    # Chunking parameters
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Chunk size in characters (default: 1000)"
    )

    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="Chunk overlap in characters (default: 200)"
    )

    # Batch size
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Embedding batch size (default: 32)"
    )

    # Verbose
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    return parser.parse_args()


async def main():
    """Main entry point"""
    args = parse_args()

    # Build configuration
    config = ProcessorConfig(
        embedding_url=args.embedding_url,
        vision_url=args.vision_url,
        language=args.language,
        tags=args.tags.split(","),
        vision_enabled=args.enable_vlm,
        save_to_db=args.save_db,
        output_dir=args.output,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        embedding_batch_size=args.batch_size,
        verbose=args.verbose,
        postgres_password=os.environ.get("POSTGRES_PASSWORD", ""),
        neo4j_password=os.environ.get("NEO4J_PASSWORD", ""),
    )

    # Create processor
    processor = DocumentProcessor(config)

    # Process input
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           KMS Document Processor CLI                         ║
╠══════════════════════════════════════════════════════════════╣
║  Input     : {str(input_path)[:45]:<45} ║
║  Language  : {config.language:<45} ║
║  Tags      : {','.join(config.tags)[:45]:<45} ║
║  VLM       : {'Enabled' if config.vision_enabled else 'Disabled':<45} ║
║  Save DB   : {'Yes' if config.save_to_db else 'No':<45} ║
╚══════════════════════════════════════════════════════════════╝
""")

    if input_path.is_file():
        results = [await processor.process_file(input_path)]
    else:
        results = await processor.process_directory(input_path)

    # Print summary
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    Processing Summary                        ║
╠══════════════════════════════════════════════════════════════╣""")

    total_chunks = sum(len(r.chunks) for r in results)
    total_images = sum(len(r.images) for r in results)
    success_count = sum(1 for r in results if r.status == ProcessingStatus.COMPLETED)
    failed_count = sum(1 for r in results if r.status == ProcessingStatus.FAILED)
    total_time = sum(r.processing_time_seconds for r in results)

    print(f"║  Files Processed : {len(results):<42} ║")
    print(f"║  Successful      : {success_count:<42} ║")
    print(f"║  Failed          : {failed_count:<42} ║")
    print(f"║  Total Chunks    : {total_chunks:<42} ║")
    print(f"║  Total Images    : {total_images:<42} ║")
    print(f"║  Total Time      : {total_time:.2f}s{' ':<38} ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")

    # Save results to file
    if config.output_dir:
        output_dir = Path(config.output_dir)
    else:
        output_dir = input_path.parent if input_path.is_file() else input_path

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"processing_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    processor.save_results_to_file(results, output_file)

    # Exit code
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
