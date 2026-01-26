"""
Document Category Service

Categorizes all documents in the database and stores categories in Redis cache.
Enables fast keyword-based category lookup for Agent-Driven RAG pre-search confirmation.

Categories are hierarchical:
- Category (e.g., "Error Codes", "Commands", "Configuration")
  - Subcategory (e.g., "VSAM Errors", "OFASM Commands")
    - Document
      - Sections
"""
import os
import re
import json
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SectionInfo:
    """Section information within a document."""
    section_id: str
    title: str
    level: int
    page_start: int
    page_end: int
    keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentInfo:
    """Document information with sections."""
    pdf_id: str
    document_name: str
    document_type: str
    total_pages: int
    language: str
    keywords: List[str] = field(default_factory=list)
    sections: List[SectionInfo] = field(default_factory=list)
    relevance_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pdf_id": self.pdf_id,
            "document_name": self.document_name,
            "document_type": self.document_type,
            "total_pages": self.total_pages,
            "language": self.language,
            "keywords": self.keywords,
            "sections": [s.to_dict() for s in self.sections],
            "relevance_score": self.relevance_score,
        }


@dataclass
class SubCategory:
    """Subcategory containing related documents."""
    id: str
    name: str
    description: str
    keywords: List[str] = field(default_factory=list)
    documents: List[DocumentInfo] = field(default_factory=list)
    relevance_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "documents": [d.to_dict() for d in self.documents],
            "document_count": len(self.documents),
            "relevance_score": self.relevance_score,
        }


@dataclass
class Category:
    """Top-level category containing subcategories."""
    id: str
    name: str
    name_ko: str
    name_ja: str
    icon: str
    description: str
    subcategories: List[SubCategory] = field(default_factory=list)
    relevance_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "name_ko": self.name_ko,
            "name_ja": self.name_ja,
            "icon": self.icon,
            "description": self.description,
            "subcategories": [s.to_dict() for s in self.subcategories],
            "subcategory_count": len(self.subcategories),
            "document_count": sum(len(s.documents) for s in self.subcategories),
            "relevance_score": self.relevance_score,
        }


@dataclass
class CategoryMatchResult:
    """Result of matching query to categories."""
    query: str
    extracted_keywords: List[str]
    categories: List[Category]
    total_documents: int
    total_sections: int
    processing_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "extracted_keywords": self.extracted_keywords,
            "categories": [c.to_dict() for c in self.categories],
            "total_documents": self.total_documents,
            "total_sections": self.total_sections,
            "processing_time_ms": self.processing_time_ms,
        }


# =============================================================================
# Predefined Category Definitions
# =============================================================================

CATEGORY_DEFINITIONS = [
    {
        "id": "error_codes",
        "name": "Error Codes & Messages",
        "name_ko": "에러 코드 및 메시지",
        "name_ja": "エラーコードとメッセージ",
        "icon": "AlertTriangle",
        "description": "Error codes, error messages, and troubleshooting guides",
        "patterns": [
            r"error[-\s]?code",
            r"[-]?\d{4,5}",  # Error codes like -5212
            r"에러|오류|error|err\b",
            r"exception|fault|failure",
            r"abend|abnormal",
        ],
        "subcategory_patterns": {
            "vsam_errors": {
                "name": "VSAM Errors",
                "patterns": ["vsam", "dsalc", "tlic", "-52", "-51", "-50"],
            },
            "db_errors": {
                "name": "Database Errors",
                "patterns": ["db2", "sql", "database", "ora-", "sqlcode"],
            },
            "system_errors": {
                "name": "System Errors",
                "patterns": ["system", "jcl", "abend", "s0c", "u0"],
            },
            "application_errors": {
                "name": "Application Errors",
                "patterns": ["application", "program", "cobol", "cics"],
            },
        },
    },
    {
        "id": "commands",
        "name": "Commands & Syntax",
        "name_ko": "명령어 및 구문",
        "name_ja": "コマンドと構文",
        "icon": "Terminal",
        "description": "Command references, syntax guides, and usage examples",
        "patterns": [
            r"command|cmd\b|명령어|コマンド",
            r"syntax|구문|構文",
            r"usage|사용법|使用方法",
            r"instruction|지시어|指示語",
            r"directive",
        ],
        "subcategory_patterns": {
            "ofasm_commands": {
                "name": "OFASM Commands",
                "patterns": ["ofasm", "assembler", "asm", "macro"],
            },
            "jcl_commands": {
                "name": "JCL Commands",
                "patterns": ["jcl", "job", "exec", "dd ", "proc"],
            },
            "utility_commands": {
                "name": "Utility Commands",
                "patterns": ["utility", "idcams", "iebgener", "iebcopy", "sort"],
            },
            "system_commands": {
                "name": "System Commands",
                "patterns": ["tso", "ispf", "sdsf", "console"],
            },
        },
    },
    {
        "id": "configuration",
        "name": "Configuration & Setup",
        "name_ko": "설정 및 구성",
        "name_ja": "設定とセットアップ",
        "icon": "Settings",
        "description": "Configuration guides, setup instructions, and parameters",
        "patterns": [
            r"config|설정|構成|設定",
            r"setup|셋업|セットアップ",
            r"install|설치|インストール",
            r"parameter|파라미터|パラメータ",
            r"environment|환경|環境",
        ],
        "subcategory_patterns": {
            "system_config": {
                "name": "System Configuration",
                "patterns": ["system", "server", "region", "osc", "oscobol"],
            },
            "network_config": {
                "name": "Network Configuration",
                "patterns": ["network", "tcp", "vtam", "lu", "connection"],
            },
            "security_config": {
                "name": "Security Configuration",
                "patterns": ["security", "racf", "auth", "permission", "access"],
            },
            "performance_config": {
                "name": "Performance Configuration",
                "patterns": ["performance", "tuning", "buffer", "cache", "memory"],
            },
        },
    },
    {
        "id": "concepts",
        "name": "Concepts & Overview",
        "name_ko": "개념 및 개요",
        "name_ja": "概念と概要",
        "icon": "BookOpen",
        "description": "Conceptual explanations, overviews, and introductions",
        "patterns": [
            r"concept|개념|概念",
            r"overview|개요|概要",
            r"introduction|소개|紹介",
            r"what is|무엇|とは",
            r"architecture|아키텍처|アーキテクチャ",
        ],
        "subcategory_patterns": {
            "architecture": {
                "name": "Architecture",
                "patterns": ["architecture", "structure", "design", "flow"],
            },
            "fundamentals": {
                "name": "Fundamentals",
                "patterns": ["basic", "fundamental", "core", "principle"],
            },
            "glossary": {
                "name": "Glossary & Terms",
                "patterns": ["glossary", "term", "definition", "meaning"],
            },
        },
    },
    {
        "id": "procedures",
        "name": "Procedures & Guides",
        "name_ko": "절차 및 가이드",
        "name_ja": "手順とガイド",
        "icon": "FileText",
        "description": "Step-by-step procedures, how-to guides, and tutorials",
        "patterns": [
            r"procedure|절차|手順",
            r"guide|가이드|ガイド",
            r"how to|방법|方法",
            r"step|단계|ステップ",
            r"tutorial|튜토리얼|チュートリアル",
        ],
        "subcategory_patterns": {
            "migration": {
                "name": "Migration Guides",
                "patterns": ["migration", "migrate", "convert", "transfer"],
            },
            "troubleshooting": {
                "name": "Troubleshooting",
                "patterns": ["troubleshoot", "debug", "diagnose", "resolve"],
            },
            "operation": {
                "name": "Operation Guides",
                "patterns": ["operation", "operate", "manage", "monitor"],
            },
            "development": {
                "name": "Development Guides",
                "patterns": ["develop", "program", "code", "implement"],
            },
        },
    },
    {
        "id": "reference",
        "name": "Reference & API",
        "name_ko": "레퍼런스 및 API",
        "name_ja": "リファレンスとAPI",
        "icon": "Book",
        "description": "API references, technical specifications, and detailed documentation",
        "patterns": [
            r"reference|레퍼런스|リファレンス",
            r"api\b|인터페이스|インターフェース",
            r"specification|스펙|仕様",
            r"manual|매뉴얼|マニュアル",
            r"documentation|문서|ドキュメント",
        ],
        "subcategory_patterns": {
            "api_reference": {
                "name": "API Reference",
                "patterns": ["api", "interface", "function", "method", "call"],
            },
            "data_reference": {
                "name": "Data Reference",
                "patterns": ["data", "format", "structure", "layout", "record"],
            },
            "system_reference": {
                "name": "System Reference",
                "patterns": ["system", "module", "component", "service"],
            },
        },
    },
]


# =============================================================================
# Document Category Service
# =============================================================================

class DocumentCategoryService:
    """
    Service for categorizing documents and providing keyword-based category lookup.

    Uses Redis for caching categorization results.
    """

    CACHE_KEY_PREFIX = "doc_category:"
    CACHE_KEY_ALL_CATEGORIES = "doc_category:all_categories"
    CACHE_KEY_KEYWORD_INDEX = "doc_category:keyword_index"
    CACHE_KEY_DOCUMENT_INDEX = "doc_category:document_index"
    CACHE_KEY_LAST_UPDATE = "doc_category:last_update"
    CACHE_TTL_HOURS = 24  # Cache for 24 hours

    def __init__(self, pool=None, redis_client=None):
        """
        Initialize Document Category Service.

        Args:
            pool: asyncpg connection pool
            redis_client: Redis async client
        """
        self._pool = pool
        self._redis = redis_client
        self._initialized = False
        self._categories: List[Category] = []
        self._keyword_index: Dict[str, List[Tuple[str, str, float]]] = {}  # keyword -> [(category_id, subcategory_id, score)]
        self._document_index: Dict[str, Dict[str, Any]] = {}  # pdf_id -> document info

    async def _ensure_connections(self):
        """Ensure database and Redis connections."""
        # PostgreSQL
        if self._pool is None:
            try:
                import asyncpg
                from ..core.config import api_settings

                dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
                self._pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
                logger.info("DocumentCategoryService: Connected to PostgreSQL")
            except Exception as e:
                logger.error(f"DocumentCategoryService: Failed to connect to PostgreSQL: {e}")

        # Redis
        if self._redis is None:
            try:
                import redis.asyncio as redis

                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
                self._redis = await redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
                logger.info(f"DocumentCategoryService: Connected to Redis at {redis_url}")
            except Exception as e:
                logger.warning(f"DocumentCategoryService: Redis not available: {e}, using in-memory cache")
                self._redis = None

    async def initialize(self, force_rebuild: bool = False) -> bool:
        """
        Initialize the service and build/load category cache.

        Args:
            force_rebuild: Force rebuild even if cache exists

        Returns:
            True if successful
        """
        if self._initialized and not force_rebuild:
            return True

        try:
            await self._ensure_connections()

            # Try to load from Redis cache first
            if not force_rebuild and await self._load_from_cache():
                self._initialized = True
                logger.info("DocumentCategoryService: Loaded from Redis cache")
                return True

            # Build categories from database
            await self._build_categories()
            self._initialized = True

            # Save to Redis cache
            await self._save_to_cache()

            logger.info(f"DocumentCategoryService: Built {len(self._categories)} categories, "
                       f"{len(self._keyword_index)} keywords indexed")
            return True

        except Exception as e:
            logger.error(f"DocumentCategoryService: Initialization failed: {e}")
            return False

    async def _load_from_cache(self) -> bool:
        """Load categories from Redis cache."""
        if self._redis is None:
            return False

        try:
            # Check if cache exists and is fresh
            last_update = await self._redis.get(self.CACHE_KEY_LAST_UPDATE)
            if not last_update:
                return False

            # Load categories
            categories_json = await self._redis.get(self.CACHE_KEY_ALL_CATEGORIES)
            if not categories_json:
                return False

            categories_data = json.loads(categories_json)
            self._categories = self._parse_categories(categories_data)

            # Load keyword index
            keyword_index_json = await self._redis.get(self.CACHE_KEY_KEYWORD_INDEX)
            if keyword_index_json:
                self._keyword_index = json.loads(keyword_index_json)

            # Load document index
            document_index_json = await self._redis.get(self.CACHE_KEY_DOCUMENT_INDEX)
            if document_index_json:
                self._document_index = json.loads(document_index_json)

            return True

        except Exception as e:
            logger.warning(f"DocumentCategoryService: Failed to load from cache: {e}")
            return False

    async def _save_to_cache(self):
        """Save categories to Redis cache."""
        if self._redis is None:
            return

        try:
            ttl = timedelta(hours=self.CACHE_TTL_HOURS)

            # Save categories
            categories_data = [c.to_dict() for c in self._categories]
            await self._redis.set(
                self.CACHE_KEY_ALL_CATEGORIES,
                json.dumps(categories_data, ensure_ascii=False),
                ex=int(ttl.total_seconds())
            )

            # Save keyword index
            await self._redis.set(
                self.CACHE_KEY_KEYWORD_INDEX,
                json.dumps(self._keyword_index, ensure_ascii=False),
                ex=int(ttl.total_seconds())
            )

            # Save document index
            await self._redis.set(
                self.CACHE_KEY_DOCUMENT_INDEX,
                json.dumps(self._document_index, ensure_ascii=False),
                ex=int(ttl.total_seconds())
            )

            # Save update timestamp
            await self._redis.set(
                self.CACHE_KEY_LAST_UPDATE,
                datetime.now(timezone.utc).isoformat(),
                ex=int(ttl.total_seconds())
            )

            logger.info("DocumentCategoryService: Saved to Redis cache")

        except Exception as e:
            logger.warning(f"DocumentCategoryService: Failed to save to cache: {e}")

    def _parse_categories(self, data: List[Dict]) -> List[Category]:
        """Parse category data from JSON."""
        categories = []
        for cat_data in data:
            subcategories = []
            for sub_data in cat_data.get("subcategories", []):
                documents = []
                for doc_data in sub_data.get("documents", []):
                    sections = [
                        SectionInfo(**s) for s in doc_data.get("sections", [])
                    ]
                    documents.append(DocumentInfo(
                        pdf_id=doc_data["pdf_id"],
                        document_name=doc_data["document_name"],
                        document_type=doc_data["document_type"],
                        total_pages=doc_data["total_pages"],
                        language=doc_data.get("language", "auto"),
                        keywords=doc_data.get("keywords", []),
                        sections=sections,
                        relevance_score=doc_data.get("relevance_score", 0.0),
                    ))
                subcategories.append(SubCategory(
                    id=sub_data["id"],
                    name=sub_data["name"],
                    description=sub_data.get("description", ""),
                    keywords=sub_data.get("keywords", []),
                    documents=documents,
                    relevance_score=sub_data.get("relevance_score", 0.0),
                ))
            categories.append(Category(
                id=cat_data["id"],
                name=cat_data["name"],
                name_ko=cat_data.get("name_ko", cat_data["name"]),
                name_ja=cat_data.get("name_ja", cat_data["name"]),
                icon=cat_data.get("icon", "Folder"),
                description=cat_data.get("description", ""),
                subcategories=subcategories,
                relevance_score=cat_data.get("relevance_score", 0.0),
            ))
        return categories

    async def _build_categories(self):
        """Build categories from database documents."""
        if self._pool is None:
            logger.error("DocumentCategoryService: No database connection")
            return

        # Fetch all documents with structure
        documents = await self._fetch_all_documents()
        logger.info(f"DocumentCategoryService: Fetched {len(documents)} documents")

        # Initialize categories from definitions
        self._categories = []
        self._keyword_index = defaultdict(list)
        self._document_index = {}

        for cat_def in CATEGORY_DEFINITIONS:
            category = Category(
                id=cat_def["id"],
                name=cat_def["name"],
                name_ko=cat_def.get("name_ko", cat_def["name"]),
                name_ja=cat_def.get("name_ja", cat_def["name"]),
                icon=cat_def.get("icon", "Folder"),
                description=cat_def.get("description", ""),
            )

            # Build subcategories
            for sub_id, sub_def in cat_def.get("subcategory_patterns", {}).items():
                subcategory = SubCategory(
                    id=f"{cat_def['id']}:{sub_id}",
                    name=sub_def["name"],
                    description=f"Documents related to {sub_def['name']}",
                    keywords=sub_def.get("patterns", []),
                )
                category.subcategories.append(subcategory)

                # Index keywords
                for keyword in sub_def.get("patterns", []):
                    self._keyword_index[keyword.lower()].append(
                        (category.id, subcategory.id, 1.0)
                    )

            self._categories.append(category)

            # Index category patterns
            for pattern in cat_def.get("patterns", []):
                self._keyword_index[pattern.lower()].append(
                    (category.id, None, 0.8)
                )

        # Categorize documents
        for doc in documents:
            self._categorize_document(doc)
            self._document_index[doc["pdf_id"]] = doc

    async def _fetch_all_documents(self) -> List[Dict[str, Any]]:
        """Fetch all documents from database with structure information."""
        documents = []

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    pdf_id, document_name, document_type, hierarchy,
                    total_pages, language, analyzed_at
                FROM pdf_structure_analysis
                WHERE hierarchy IS NOT NULL
                ORDER BY analyzed_at DESC
            """)

            for row in rows:
                hierarchy = row["hierarchy"] if isinstance(row["hierarchy"], list) else []

                # Extract keywords from document name
                doc_name = row["document_name"] or row["pdf_id"]
                doc_keywords = self._extract_keywords(doc_name)

                # Extract keywords from sections
                sections = []
                for section in hierarchy:
                    title = section.get("title", "")
                    section_keywords = self._extract_keywords(title)
                    doc_keywords.extend(section_keywords)

                    sections.append({
                        "section_id": section.get("id", ""),
                        "title": title,
                        "level": section.get("level", 1),
                        "page_start": section.get("page_start", 1),
                        "page_end": section.get("page_end", 1),
                        "keywords": section_keywords,
                    })

                documents.append({
                    "pdf_id": row["pdf_id"],
                    "document_name": doc_name,
                    "document_type": row["document_type"] or "unknown",
                    "total_pages": row["total_pages"] or 0,
                    "language": row["language"] or "auto",
                    "keywords": list(set(doc_keywords)),
                    "sections": sections,
                })

        return documents

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text."""
        if not text:
            return []

        keywords = []
        text_lower = text.lower()

        # Extract error codes (e.g., -5212, ERROR-001, ORA-12345)
        error_codes = re.findall(r'[-]?\d{3,5}|[a-z]{2,4}[-_]?\d{3,5}', text_lower, re.IGNORECASE)
        keywords.extend(error_codes)

        # Extract technical terms (uppercase words, acronyms)
        tech_terms = re.findall(r'\b[A-Z]{2,}(?:[a-z]*[A-Z]+)*\b', text)
        keywords.extend([t.lower() for t in tech_terms])

        # Extract meaningful words (filter common words)
        words = re.findall(r'\b[a-zA-Z가-힣ぁ-んァ-ン一-龥]{2,}\b', text)
        stop_words = {
            'the', 'and', 'for', 'with', 'this', 'that', 'from', 'have',
            'are', 'was', 'were', 'been', 'being', 'chapter', 'section',
            'page', 'table', 'figure', 'part', 'appendix',
        }
        for word in words:
            if word.lower() not in stop_words and len(word) > 2:
                keywords.append(word.lower())

        return list(set(keywords))

    def _categorize_document(self, doc: Dict[str, Any]):
        """Categorize a document into appropriate categories."""
        doc_text = f"{doc['document_name']} {' '.join(doc['keywords'])}"
        doc_text_lower = doc_text.lower()

        for category in self._categories:
            cat_def = next(
                (c for c in CATEGORY_DEFINITIONS if c["id"] == category.id),
                None
            )
            if not cat_def:
                continue

            # Check if document matches category patterns
            category_match_score = 0.0
            for pattern in cat_def.get("patterns", []):
                if re.search(pattern, doc_text_lower, re.IGNORECASE):
                    category_match_score = max(category_match_score, 0.5)
                    break

            if category_match_score == 0:
                continue

            # Find best matching subcategory
            best_subcategory = None
            best_score = 0.0

            for subcategory in category.subcategories:
                sub_id = subcategory.id.split(":")[-1]
                sub_def = cat_def.get("subcategory_patterns", {}).get(sub_id, {})

                score = 0.0
                for pattern in sub_def.get("patterns", []):
                    if pattern.lower() in doc_text_lower:
                        score += 0.3
                    for keyword in doc.get("keywords", []):
                        if pattern.lower() in keyword.lower():
                            score += 0.2

                if score > best_score:
                    best_score = score
                    best_subcategory = subcategory

            # Add document to best matching subcategory
            if best_subcategory and best_score > 0.2:
                doc_info = DocumentInfo(
                    pdf_id=doc["pdf_id"],
                    document_name=doc["document_name"],
                    document_type=doc["document_type"],
                    total_pages=doc["total_pages"],
                    language=doc["language"],
                    keywords=doc.get("keywords", [])[:20],  # Limit keywords
                    sections=[
                        SectionInfo(**s) for s in doc.get("sections", [])[:10]  # Limit sections
                    ],
                    relevance_score=best_score,
                )
                best_subcategory.documents.append(doc_info)

                # Index document keywords
                for keyword in doc.get("keywords", []):
                    self._keyword_index[keyword.lower()].append(
                        (category.id, best_subcategory.id, best_score)
                    )

    async def match_query_to_categories(
        self,
        query: str,
        max_categories: int = 5,
        max_subcategories: int = 3,
        max_documents_per_subcategory: int = 5,
        min_score: float = 0.1,
    ) -> CategoryMatchResult:
        """
        Match a user query to relevant categories.

        Args:
            query: User's search query
            max_categories: Maximum categories to return
            max_subcategories: Maximum subcategories per category
            max_documents_per_subcategory: Maximum documents per subcategory
            min_score: Minimum relevance score

        Returns:
            CategoryMatchResult with matched categories
        """
        import time
        start_time = time.time()

        if not self._initialized:
            await self.initialize()

        # Extract keywords from query
        query_keywords = self._extract_keywords(query)
        query_lower = query.lower()

        # Add original query words
        query_words = re.findall(r'\b\w+\b', query_lower)
        query_keywords.extend(query_words)
        query_keywords = list(set(query_keywords))

        # Score categories based on keyword matches
        category_scores: Dict[str, float] = defaultdict(float)
        subcategory_scores: Dict[str, float] = defaultdict(float)
        document_scores: Dict[str, float] = defaultdict(float)

        for keyword in query_keywords:
            # Check keyword index
            if keyword in self._keyword_index:
                for cat_id, sub_id, score in self._keyword_index[keyword]:
                    category_scores[cat_id] += score
                    if sub_id:
                        subcategory_scores[sub_id] += score

            # Pattern matching for error codes
            if re.match(r'[-]?\d{3,5}', keyword):
                category_scores["error_codes"] += 1.0

            # Check document index
            for pdf_id, doc in self._document_index.items():
                doc_keywords = doc.get("keywords", [])
                if keyword in [k.lower() for k in doc_keywords]:
                    document_scores[pdf_id] += 0.5

        # Also check category patterns directly
        for cat_def in CATEGORY_DEFINITIONS:
            for pattern in cat_def.get("patterns", []):
                try:
                    if re.search(pattern, query_lower, re.IGNORECASE):
                        category_scores[cat_def["id"]] += 0.5
                except re.error:
                    if pattern in query_lower:
                        category_scores[cat_def["id"]] += 0.5

        # Build result categories with scores
        result_categories = []
        total_documents = 0
        total_sections = 0

        for category in self._categories:
            if category_scores.get(category.id, 0) < min_score:
                continue

            # Clone category with relevant subcategories
            result_subcategories = []

            for subcategory in category.subcategories:
                sub_score = subcategory_scores.get(subcategory.id, 0)

                # Include if subcategory has score or category has high score
                if sub_score > 0 or category_scores[category.id] > 0.5:
                    # Filter and score documents
                    scored_docs = []
                    for doc in subcategory.documents:
                        doc_score = document_scores.get(doc.pdf_id, 0)
                        # Also check direct keyword match
                        for kw in query_keywords:
                            if kw in [k.lower() for k in doc.keywords]:
                                doc_score += 0.3
                            if kw in doc.document_name.lower():
                                doc_score += 0.5

                        if doc_score > 0 or sub_score > 0.3:
                            doc_copy = DocumentInfo(
                                pdf_id=doc.pdf_id,
                                document_name=doc.document_name,
                                document_type=doc.document_type,
                                total_pages=doc.total_pages,
                                language=doc.language,
                                keywords=doc.keywords,
                                sections=doc.sections,
                                relevance_score=doc_score + sub_score,
                            )
                            scored_docs.append(doc_copy)

                    if scored_docs:
                        # Sort by score and limit
                        scored_docs.sort(key=lambda x: x.relevance_score, reverse=True)
                        limited_docs = scored_docs[:max_documents_per_subcategory]

                        result_subcategory = SubCategory(
                            id=subcategory.id,
                            name=subcategory.name,
                            description=subcategory.description,
                            keywords=subcategory.keywords,
                            documents=limited_docs,
                            relevance_score=sub_score + category_scores[category.id],
                        )
                        result_subcategories.append(result_subcategory)
                        total_documents += len(limited_docs)
                        total_sections += sum(len(d.sections) for d in limited_docs)

            if result_subcategories:
                # Sort subcategories by score and limit
                result_subcategories.sort(key=lambda x: x.relevance_score, reverse=True)
                limited_subcategories = result_subcategories[:max_subcategories]

                result_category = Category(
                    id=category.id,
                    name=category.name,
                    name_ko=category.name_ko,
                    name_ja=category.name_ja,
                    icon=category.icon,
                    description=category.description,
                    subcategories=limited_subcategories,
                    relevance_score=category_scores[category.id],
                )
                result_categories.append(result_category)

        # Sort categories by score and limit
        result_categories.sort(key=lambda x: x.relevance_score, reverse=True)
        result_categories = result_categories[:max_categories]

        processing_time = (time.time() - start_time) * 1000

        return CategoryMatchResult(
            query=query,
            extracted_keywords=query_keywords,
            categories=result_categories,
            total_documents=total_documents,
            total_sections=total_sections,
            processing_time_ms=processing_time,
        )

    async def get_all_categories(self) -> List[Category]:
        """Get all available categories (without documents for overview)."""
        if not self._initialized:
            await self.initialize()

        # Return categories with just counts, no full document lists
        result = []
        for category in self._categories:
            cat_copy = Category(
                id=category.id,
                name=category.name,
                name_ko=category.name_ko,
                name_ja=category.name_ja,
                icon=category.icon,
                description=category.description,
                subcategories=[
                    SubCategory(
                        id=sub.id,
                        name=sub.name,
                        description=sub.description,
                        keywords=sub.keywords[:5],
                        documents=[],  # Empty for overview
                        relevance_score=0,
                    )
                    for sub in category.subcategories
                ],
            )
            result.append(cat_copy)

        return result

    async def refresh(self) -> bool:
        """Refresh categories from database."""
        self._initialized = False
        return await self.initialize(force_rebuild=True)

    async def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        if not self._initialized:
            await self.initialize()

        total_documents = sum(
            len(sub.documents)
            for cat in self._categories
            for sub in cat.subcategories
        )

        return {
            "initialized": self._initialized,
            "total_categories": len(self._categories),
            "total_subcategories": sum(len(c.subcategories) for c in self._categories),
            "total_documents": total_documents,
            "total_keywords_indexed": len(self._keyword_index),
            "cache_enabled": self._redis is not None,
        }


# =============================================================================
# Singleton Instance
# =============================================================================

_document_category_service: Optional[DocumentCategoryService] = None


def get_document_category_service() -> DocumentCategoryService:
    """Get the singleton DocumentCategoryService instance."""
    global _document_category_service
    if _document_category_service is None:
        _document_category_service = DocumentCategoryService()
    return _document_category_service


async def initialize_document_category_service(
    pool=None,
    redis_client=None,
    force_rebuild: bool = False
) -> DocumentCategoryService:
    """
    Initialize the document category service.

    Args:
        pool: asyncpg connection pool
        redis_client: Redis async client
        force_rebuild: Force rebuild cache

    Returns:
        Initialized DocumentCategoryService
    """
    global _document_category_service
    _document_category_service = DocumentCategoryService(pool=pool, redis_client=redis_client)
    await _document_category_service.initialize(force_rebuild=force_rebuild)
    return _document_category_service
