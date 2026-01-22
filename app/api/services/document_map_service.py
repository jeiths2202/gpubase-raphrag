"""
Document Map Service (AGENT.md Role)

Provides document hierarchy map for Agent-Driven RAG navigation.
Enables pre-search confirmation by providing document/section candidates
based on the user's query.

Uses existing pdf_structure_analysis table for document hierarchy information.
"""
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SectionCandidate:
    """A document section that may be relevant to the user's query."""
    pdf_id: str
    document_name: str
    section_path: str
    section_title: str
    page_start: int
    page_end: int
    relevance_score: float = 0.0
    keywords: List[str] = field(default_factory=list)
    level: int = 1


@dataclass
class DocumentCandidate:
    """A document that may be relevant to the user's query."""
    pdf_id: str
    document_name: str
    document_type: str
    total_pages: int
    sections: List[SectionCandidate] = field(default_factory=list)
    relevance_score: float = 0.0
    keywords: List[str] = field(default_factory=list)


@dataclass
class DocumentMapEntry:
    """Entry in the document map for navigation."""
    pdf_id: str
    document_name: str
    document_type: str
    total_pages: int
    total_sections: int
    sections: List[Dict[str, Any]]
    keywords: List[str]
    language: str
    last_updated: Optional[datetime] = None


class DocumentMapService:
    """
    Service for managing document hierarchy maps.

    Provides:
    - Document/section candidate retrieval based on query
    - Keyword extraction and matching
    - Navigation recommendations
    """

    def __init__(self, pool=None):
        """
        Initialize Document Map Service.

        Args:
            pool: asyncpg connection pool (optional, will auto-connect if not provided)
        """
        self._pool = pool
        self._initialized = False
        self._document_cache: Dict[str, DocumentMapEntry] = {}
        self._keyword_index: Dict[str, List[str]] = {}  # keyword -> [pdf_ids]

    async def _ensure_pool(self):
        """Ensure database connection pool is available."""
        if self._pool is not None:
            return

        try:
            import asyncpg
            from ..core.config import api_settings

            dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
            self._pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
            logger.info("DocumentMapService: Connected to PostgreSQL")
        except Exception as e:
            logger.error(f"DocumentMapService: Failed to connect to PostgreSQL: {e}")
            raise

    async def initialize(self) -> bool:
        """Initialize the service and build document map."""
        if self._initialized:
            return True

        try:
            await self._ensure_pool()
            await self._build_document_map()
            self._initialized = True
            logger.info(f"DocumentMapService: Initialized with {len(self._document_cache)} documents")
            return True
        except Exception as e:
            logger.error(f"DocumentMapService: Initialization failed: {e}")
            return False

    async def _build_document_map(self) -> None:
        """Build document map from pdf_structure_analysis table."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    pdf_id, document_name, document_type, hierarchy,
                    total_pages, language, analyzed_at
                FROM pdf_structure_analysis
                ORDER BY analyzed_at DESC
            """)

            self._document_cache.clear()
            self._keyword_index.clear()

            for row in rows:
                pdf_id = row["pdf_id"]
                hierarchy = row["hierarchy"] if isinstance(row["hierarchy"], list) else []

                # Extract keywords from document name and section titles
                doc_keywords = self._extract_keywords(row["document_name"] or "")
                for section in hierarchy:
                    title = section.get("title", "")
                    doc_keywords.extend(self._extract_keywords(title))

                doc_keywords = list(set(doc_keywords))

                entry = DocumentMapEntry(
                    pdf_id=pdf_id,
                    document_name=row["document_name"] or pdf_id,
                    document_type=row["document_type"] or "unknown",
                    total_pages=row["total_pages"] or 0,
                    total_sections=len(hierarchy),
                    sections=hierarchy,
                    keywords=doc_keywords,
                    language=row["language"] or "auto",
                    last_updated=row["analyzed_at"]
                )

                self._document_cache[pdf_id] = entry

                # Build keyword index
                for keyword in doc_keywords:
                    if keyword not in self._keyword_index:
                        self._keyword_index[keyword] = []
                    if pdf_id not in self._keyword_index[keyword]:
                        self._keyword_index[keyword].append(pdf_id)

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        if not text:
            return []

        # Normalize text
        text = text.lower()

        # Extract error codes (e.g., -5212, ERROR-001)
        error_codes = re.findall(r'[-]?\d{3,5}|error[-_]?\d+', text, re.IGNORECASE)

        # Extract technical terms (capitalized words, acronyms)
        tech_terms = re.findall(r'\b[A-Z]{2,}[a-z]*\b|\b[A-Z][a-z]+[A-Z][a-z]+\b', text)

        # Extract words (filtering common words)
        words = re.findall(r'\b[a-zA-Z가-힣ぁ-んァ-ン一-龥]{2,}\b', text)

        # Common stop words to filter
        stop_words = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 'have',
                     'are', 'was', 'were', 'been', 'being', 'chapter', 'section'}

        keywords = []
        for word in words:
            if word.lower() not in stop_words and len(word) > 1:
                keywords.append(word.lower())

        keywords.extend([ec.lower() for ec in error_codes])
        keywords.extend([tt.lower() for tt in tech_terms])

        return list(set(keywords))

    async def get_document_candidates(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.1
    ) -> List[DocumentCandidate]:
        """
        Get document candidates based on query.

        Args:
            query: User's search query
            top_k: Maximum number of documents to return
            min_score: Minimum relevance score

        Returns:
            List of DocumentCandidate sorted by relevance
        """
        if not self._initialized:
            await self.initialize()

        query_keywords = self._extract_keywords(query)
        candidates = []

        for pdf_id, entry in self._document_cache.items():
            # Calculate relevance score based on keyword matching
            score = self._calculate_relevance(query_keywords, entry.keywords, query, entry.document_name)

            if score >= min_score:
                # Get relevant sections
                sections = await self._get_section_candidates(
                    pdf_id, entry.sections, query_keywords, query
                )

                candidates.append(DocumentCandidate(
                    pdf_id=pdf_id,
                    document_name=entry.document_name,
                    document_type=entry.document_type,
                    total_pages=entry.total_pages,
                    sections=sections,
                    relevance_score=score,
                    keywords=entry.keywords[:10]
                ))

        # Sort by relevance and return top-k
        candidates.sort(key=lambda x: x.relevance_score, reverse=True)
        return candidates[:top_k]

    async def _get_section_candidates(
        self,
        pdf_id: str,
        sections: List[Dict[str, Any]],
        query_keywords: List[str],
        query: str
    ) -> List[SectionCandidate]:
        """Get section candidates within a document."""
        entry = self._document_cache.get(pdf_id)
        if not entry:
            return []

        candidates = []
        for section in sections:
            section_keywords = self._extract_keywords(section.get("title", ""))
            score = self._calculate_relevance(
                query_keywords, section_keywords,
                query, section.get("title", "")
            )

            if score > 0:
                candidates.append(SectionCandidate(
                    pdf_id=pdf_id,
                    document_name=entry.document_name,
                    section_path=section.get("id", ""),
                    section_title=section.get("title", ""),
                    page_start=section.get("page_start", 1),
                    page_end=section.get("page_end", 1),
                    relevance_score=score,
                    keywords=section_keywords,
                    level=section.get("level", 1)
                ))

        candidates.sort(key=lambda x: x.relevance_score, reverse=True)
        return candidates[:5]

    def _calculate_relevance(
        self,
        query_keywords: List[str],
        target_keywords: List[str],
        query: str,
        target_text: str
    ) -> float:
        """Calculate relevance score between query and target."""
        if not query_keywords or not target_keywords:
            return 0.0

        # Keyword overlap score
        overlap = len(set(query_keywords) & set(target_keywords))
        keyword_score = overlap / max(len(query_keywords), 1)

        # Exact match bonus
        exact_match_bonus = 0.0
        query_lower = query.lower()
        target_lower = target_text.lower()

        # Check for error code exact match
        error_code_pattern = r'[-]?\d{3,5}'
        query_codes = re.findall(error_code_pattern, query_lower)
        target_codes = re.findall(error_code_pattern, target_lower)
        if query_codes and set(query_codes) & set(target_codes):
            exact_match_bonus = 0.5

        # Substring match
        if any(kw in target_lower for kw in query_keywords if len(kw) > 3):
            exact_match_bonus += 0.2

        return min(keyword_score + exact_match_bonus, 1.0)

    async def get_document_map(self, pdf_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the document map for navigation.

        Args:
            pdf_id: Optional specific document ID

        Returns:
            Document map with hierarchy information
        """
        if not self._initialized:
            await self.initialize()

        if pdf_id:
            entry = self._document_cache.get(pdf_id)
            if entry:
                return {
                    "documents": [{
                        "pdf_id": entry.pdf_id,
                        "document_name": entry.document_name,
                        "document_type": entry.document_type,
                        "total_pages": entry.total_pages,
                        "sections": entry.sections,
                        "keywords": entry.keywords
                    }]
                }
            return {"documents": []}

        # Return all documents
        documents = []
        for entry in self._document_cache.values():
            documents.append({
                "pdf_id": entry.pdf_id,
                "document_name": entry.document_name,
                "document_type": entry.document_type,
                "total_pages": entry.total_pages,
                "total_sections": entry.total_sections,
                "keywords": entry.keywords[:10],
                "language": entry.language
            })

        return {"documents": documents}

    async def search_by_keyword(
        self,
        keyword: str,
        include_sections: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search documents by keyword.

        Args:
            keyword: Search keyword
            include_sections: Whether to include section details

        Returns:
            List of matching documents
        """
        if not self._initialized:
            await self.initialize()

        keyword_lower = keyword.lower()
        matching_pdf_ids = self._keyword_index.get(keyword_lower, [])

        results = []
        for pdf_id in matching_pdf_ids:
            entry = self._document_cache.get(pdf_id)
            if entry:
                result = {
                    "pdf_id": entry.pdf_id,
                    "document_name": entry.document_name,
                    "document_type": entry.document_type,
                    "keywords": entry.keywords
                }

                if include_sections:
                    # Find sections containing the keyword
                    matching_sections = []
                    for section in entry.sections:
                        title = section.get("title", "").lower()
                        if keyword_lower in title:
                            matching_sections.append(section)
                    result["matching_sections"] = matching_sections

                results.append(result)

        return results

    async def refresh_document(self, pdf_id: str) -> bool:
        """
        Refresh a specific document in the map.

        Args:
            pdf_id: Document ID to refresh

        Returns:
            True if successful
        """
        try:
            await self._ensure_pool()

            async with self._pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        pdf_id, document_name, document_type, hierarchy,
                        total_pages, language, analyzed_at
                    FROM pdf_structure_analysis
                    WHERE pdf_id = $1
                """, pdf_id)

                if not row:
                    # Document was deleted
                    if pdf_id in self._document_cache:
                        del self._document_cache[pdf_id]
                    return True

                hierarchy = row["hierarchy"] if isinstance(row["hierarchy"], list) else []

                # Extract keywords
                doc_keywords = self._extract_keywords(row["document_name"] or "")
                for section in hierarchy:
                    title = section.get("title", "")
                    doc_keywords.extend(self._extract_keywords(title))

                doc_keywords = list(set(doc_keywords))

                entry = DocumentMapEntry(
                    pdf_id=pdf_id,
                    document_name=row["document_name"] or pdf_id,
                    document_type=row["document_type"] or "unknown",
                    total_pages=row["total_pages"] or 0,
                    total_sections=len(hierarchy),
                    sections=hierarchy,
                    keywords=doc_keywords,
                    language=row["language"] or "auto",
                    last_updated=row["analyzed_at"]
                )

                # Update cache
                self._document_cache[pdf_id] = entry

                # Update keyword index
                for keyword in doc_keywords:
                    if keyword not in self._keyword_index:
                        self._keyword_index[keyword] = []
                    if pdf_id not in self._keyword_index[keyword]:
                        self._keyword_index[keyword].append(pdf_id)

                return True
        except Exception as e:
            logger.error(f"DocumentMapService: Failed to refresh document {pdf_id}: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        if not self._initialized:
            await self.initialize()

        return {
            "total_documents": len(self._document_cache),
            "total_keywords": len(self._keyword_index),
            "documents_by_type": self._count_by_type(),
            "initialized": self._initialized
        }

    def _count_by_type(self) -> Dict[str, int]:
        """Count documents by type."""
        counts = {}
        for entry in self._document_cache.values():
            doc_type = entry.document_type
            counts[doc_type] = counts.get(doc_type, 0) + 1
        return counts


# Singleton instance
_document_map_service: Optional[DocumentMapService] = None


def get_document_map_service() -> DocumentMapService:
    """Get the singleton DocumentMapService instance."""
    global _document_map_service
    if _document_map_service is None:
        _document_map_service = DocumentMapService()
    return _document_map_service


async def initialize_document_map_service(pool=None) -> DocumentMapService:
    """
    Initialize the document map service with optional pool.

    Args:
        pool: asyncpg connection pool

    Returns:
        Initialized DocumentMapService
    """
    global _document_map_service
    _document_map_service = DocumentMapService(pool=pool)
    await _document_map_service.initialize()
    return _document_map_service
