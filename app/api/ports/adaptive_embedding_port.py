"""
Adaptive Embedding Port Interfaces
적응형 임베딩 포트 인터페이스

Abstract interfaces for adaptive PDF chunking and embedding operations.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from ..models.adaptive_chunk import (
    AdaptiveChunk,
    ChunkPlan,
    ChunkType,
    PDFStructureAnalysis,
    ChunkEmbeddingCoverage,
    CoverageReport,
    QualityMetrics,
)


class PDFStructureAnalyzerPort(ABC):
    """
    Port interface for PDF structure analysis.
    Analyzes document structure to determine optimal chunking strategy.
    """

    @abstractmethod
    async def analyze(
        self,
        pdf_content: bytes,
        pdf_id: str,
        language: str = "auto"
    ) -> PDFStructureAnalysis:
        """
        Analyze PDF structure and extract hierarchy.

        Args:
            pdf_content: Raw PDF bytes
            pdf_id: Unique PDF identifier
            language: Expected document language

        Returns:
            PDFStructureAnalysis with document type, hierarchy, and layout info
        """
        pass

    @abstractmethod
    async def detect_document_type(
        self,
        pdf_content: bytes
    ) -> str:
        """
        Detect document type (manual, report, paper, etc.)

        Args:
            pdf_content: Raw PDF bytes

        Returns:
            Document type string
        """
        pass

    @abstractmethod
    async def extract_hierarchy(
        self,
        pdf_content: bytes,
        language: str = "auto"
    ) -> List[Dict[str, Any]]:
        """
        Extract section hierarchy from PDF.

        Args:
            pdf_content: Raw PDF bytes
            language: Document language

        Returns:
            List of section info dictionaries
        """
        pass


class AdaptiveChunkPlannerPort(ABC):
    """
    Port interface for adaptive chunk planning.
    Plans chunks based on semantic boundaries rather than fixed sizes.
    """

    @abstractmethod
    async def create_chunk_plan(
        self,
        pdf_content: bytes,
        structure: PDFStructureAnalysis,
        options: Dict[str, Any]
    ) -> List[ChunkPlan]:
        """
        Create a chunking plan based on structure analysis.

        Args:
            pdf_content: Raw PDF bytes
            structure: Pre-analyzed PDF structure
            options: Chunking options (max_size, min_size, preserve_tables, etc.)

        Returns:
            List of ChunkPlan objects defining how to chunk the document
        """
        pass

    @abstractmethod
    async def detect_semantic_boundaries(
        self,
        text: str,
        structure: PDFStructureAnalysis
    ) -> List[int]:
        """
        Detect semantic boundary positions in text.

        Args:
            text: Document text content
            structure: Document structure analysis

        Returns:
            List of character positions where boundaries occur
        """
        pass

    @abstractmethod
    async def build_chunk_relations(
        self,
        chunks: List[AdaptiveChunk]
    ) -> List[AdaptiveChunk]:
        """
        Build relationships between chunks (previous, next, references).

        Args:
            chunks: List of chunks without relations

        Returns:
            Same chunks with relations populated
        """
        pass


class ParallelEmbeddingExecutorPort(ABC):
    """
    Port interface for parallel embedding execution.
    Handles concurrent embedding generation with retry logic.
    """

    @abstractmethod
    async def embed_chunks(
        self,
        chunks: List[AdaptiveChunk],
        concurrency: int = 5,
        timeout_per_chunk: float = 30.0
    ) -> List[AdaptiveChunk]:
        """
        Generate embeddings for chunks in parallel.

        Args:
            chunks: Chunks to embed
            concurrency: Maximum concurrent embedding requests
            timeout_per_chunk: Timeout per chunk in seconds

        Returns:
            Chunks with embeddings populated
        """
        pass

    @abstractmethod
    async def embed_single(
        self,
        chunk: AdaptiveChunk,
        retry_count: int = 3
    ) -> AdaptiveChunk:
        """
        Embed a single chunk with retry logic.

        Args:
            chunk: Chunk to embed
            retry_count: Number of retries on failure

        Returns:
            Chunk with embedding
        """
        pass

    @abstractmethod
    async def get_embedding_status(
        self,
        pdf_id: str
    ) -> Dict[str, Any]:
        """
        Get embedding progress status for a document.

        Args:
            pdf_id: Document ID

        Returns:
            Status dict with progress, completed, failed counts
        """
        pass


class EmbeddingCoverageValidatorPort(ABC):
    """
    Port interface for embedding coverage validation.
    Ensures all content types are properly embedded.
    """

    @abstractmethod
    async def validate_coverage(
        self,
        pdf_id: str,
        chunks: List[AdaptiveChunk]
    ) -> CoverageReport:
        """
        Validate embedding coverage for a document.

        Args:
            pdf_id: Document ID
            chunks: All chunks for the document

        Returns:
            CoverageReport with coverage percentages and details
        """
        pass

    @abstractmethod
    async def get_coverage_by_type(
        self,
        pdf_id: str,
        chunk_type: ChunkType
    ) -> float:
        """
        Get coverage percentage for a specific chunk type.

        Args:
            pdf_id: Document ID
            chunk_type: Type of chunk to check

        Returns:
            Coverage percentage (0.0 - 1.0)
        """
        pass

    @abstractmethod
    async def find_missing_embeddings(
        self,
        pdf_id: str
    ) -> List[str]:
        """
        Find chunk IDs without embeddings.

        Args:
            pdf_id: Document ID

        Returns:
            List of chunk IDs missing embeddings
        """
        pass


class AdaptiveQualityEvaluatorPort(ABC):
    """
    Port interface for adaptive embedding quality evaluation.
    Evaluates embedding quality with focus on retrieval accuracy.
    """

    @abstractmethod
    async def evaluate_quality(
        self,
        pdf_id: str,
        chunks: List[AdaptiveChunk],
        sample_size: int = 10
    ) -> QualityMetrics:
        """
        Evaluate embedding quality for a document.

        Args:
            pdf_id: Document ID
            chunks: Chunks with embeddings
            sample_size: Number of chunks to sample for testing

        Returns:
            QualityMetrics with recall, precision, and quality level
        """
        pass

    @abstractmethod
    async def compute_top_k_recall(
        self,
        chunks: List[AdaptiveChunk],
        k: int = 5
    ) -> float:
        """
        Compute Top-K recall metric.

        Args:
            chunks: Chunks with embeddings
            k: Number of top results to consider

        Returns:
            Top-K recall score (0.0 - 1.0)
        """
        pass

    @abstractmethod
    async def compute_section_precision(
        self,
        chunks: List[AdaptiveChunk]
    ) -> float:
        """
        Compute section precision metric.
        Checks if retrieved chunks are from the same section.

        Args:
            chunks: Chunks with embeddings and section info

        Returns:
            Section precision score (0.0 - 1.0)
        """
        pass

    @abstractmethod
    async def detect_hallucination(
        self,
        chunk: AdaptiveChunk,
        retrieved_chunks: List[AdaptiveChunk]
    ) -> Dict[str, Any]:
        """
        Detect potential hallucination issues.
        Checks for page mismatch and section leakage.

        Args:
            chunk: Query chunk
            retrieved_chunks: Chunks retrieved for the query

        Returns:
            Dict with hallucination_detected flag and details
        """
        pass


class AdaptiveChunkRepositoryPort(ABC):
    """
    Port interface for adaptive chunk persistence.
    Handles storage and retrieval of adaptive chunks.
    """

    @abstractmethod
    async def save_chunk(self, chunk: AdaptiveChunk) -> str:
        """Save a single chunk. Returns chunk_id."""
        pass

    @abstractmethod
    async def save_chunks_batch(
        self,
        chunks: List[AdaptiveChunk]
    ) -> int:
        """Save multiple chunks. Returns count of saved chunks."""
        pass

    @abstractmethod
    async def get_chunk(self, chunk_id: str) -> Optional[AdaptiveChunk]:
        """Get a chunk by ID."""
        pass

    @abstractmethod
    async def get_chunks_by_pdf(
        self,
        pdf_id: str,
        chunk_type: Optional[ChunkType] = None
    ) -> List[AdaptiveChunk]:
        """Get all chunks for a PDF, optionally filtered by type."""
        pass

    @abstractmethod
    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        min_similarity: float = 0.3,
        pdf_id: Optional[str] = None,
        chunk_types: Optional[List[ChunkType]] = None,
        section_path_prefix: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks by embedding."""
        pass

    @abstractmethod
    async def update_embedding(
        self,
        chunk_id: str,
        embedding: List[float],
        model_version: str
    ) -> bool:
        """Update embedding for a chunk."""
        pass

    @abstractmethod
    async def delete_pdf_chunks(self, pdf_id: str) -> int:
        """Delete all chunks for a PDF. Returns deleted count."""
        pass

    @abstractmethod
    async def get_chunks_by_hash(
        self,
        content_hash: str
    ) -> List[AdaptiveChunk]:
        """Get chunks by content hash (for incremental updates)."""
        pass

    @abstractmethod
    async def get_chunks_needing_embedding(
        self,
        pdf_id: str
    ) -> List[AdaptiveChunk]:
        """Get chunks that don't have embeddings yet."""
        pass


class PDFStructureRepositoryPort(ABC):
    """
    Port interface for PDF structure analysis persistence.
    """

    @abstractmethod
    async def save_analysis(
        self,
        analysis: PDFStructureAnalysis
    ) -> str:
        """Save structure analysis. Returns pdf_id."""
        pass

    @abstractmethod
    async def get_analysis(
        self,
        pdf_id: str
    ) -> Optional[PDFStructureAnalysis]:
        """Get structure analysis for a PDF."""
        pass

    @abstractmethod
    async def delete_analysis(self, pdf_id: str) -> bool:
        """Delete structure analysis."""
        pass

    @abstractmethod
    async def get_changed_pages(
        self,
        pdf_id: str,
        new_page_hashes: Dict[str, str]
    ) -> List[int]:
        """
        Compare page hashes and return changed page numbers.

        Args:
            pdf_id: Document ID
            new_page_hashes: New page hashes from current content

        Returns:
            List of page numbers that have changed
        """
        pass


class CoverageRepositoryPort(ABC):
    """
    Port interface for embedding coverage persistence.
    """

    @abstractmethod
    async def save_coverage(
        self,
        coverage: ChunkEmbeddingCoverage
    ) -> str:
        """Save coverage report. Returns pdf_id."""
        pass

    @abstractmethod
    async def get_coverage(
        self,
        pdf_id: str
    ) -> Optional[ChunkEmbeddingCoverage]:
        """Get coverage report for a PDF."""
        pass

    @abstractmethod
    async def update_quality_metrics(
        self,
        pdf_id: str,
        metrics: QualityMetrics
    ) -> bool:
        """Update quality metrics for a document."""
        pass

    @abstractmethod
    async def delete_coverage(self, pdf_id: str) -> bool:
        """Delete coverage report."""
        pass
