"""
Web Content Service for URL-based RAG
Handles URL fetching, content extraction, and web source management
"""
import uuid
import hashlib
import asyncio
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from urllib.parse import urlparse, urljoin
import time

import httpx

# Optional imports with fallbacks
try:
    import trafilatura
    from trafilatura import extract, fetch_url
    from trafilatura.settings import use_config
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from ..models.web_source import (
    WebSource, WebSourceStatus, WebSourceCreate, WebSourceBulkCreate,
    WebSourceMetadata, WebSourceStats, ContentType, ExtractorType,
    ExtractionResult, LinkInfo, ImageFromWeb, WebSourceListItem
)


class WebContentExtractor:
    """Content extraction utilities"""

    def __init__(self):
        if TRAFILATURA_AVAILABLE:
            self.trafilatura_config = use_config()
            self.trafilatura_config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")

    async def extract_with_trafilatura(
        self,
        html_content: str,
        url: str
    ) -> ExtractionResult:
        """Extract content using Trafilatura"""
        if not TRAFILATURA_AVAILABLE:
            return ExtractionResult(
                success=False,
                error_message="Trafilatura not installed"
            )

        start_time = time.time()
        try:
            # Run in thread pool since trafilatura is sync
            text = await asyncio.to_thread(
                extract,
                html_content,
                include_comments=False,
                include_tables=True,
                include_images=False,
                include_links=False,
                output_format="txt",
                config=self.trafilatura_config
            )

            if text is None:
                text = ""

            extraction_time = int((time.time() - start_time) * 1000)

            return ExtractionResult(
                text_content=text,
                html_content=html_content,
                word_count=len(text.split()) if text else 0,
                char_count=len(text) if text else 0,
                extraction_time_ms=extraction_time,
                extractor_used=ExtractorType.TRAFILATURA,
                success=True
            )
        except Exception as e:
            return ExtractionResult(
                success=False,
                error_message=str(e),
                extractor_used=ExtractorType.TRAFILATURA
            )

    async def extract_with_beautifulsoup(
        self,
        html_content: str,
        url: str
    ) -> ExtractionResult:
        """Extract content using BeautifulSoup"""
        if not BS4_AVAILABLE:
            return ExtractionResult(
                success=False,
                error_message="BeautifulSoup not installed"
            )

        start_time = time.time()
        try:
            soup = BeautifulSoup(html_content, 'lxml')

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Get text content
            text = soup.get_text(separator='\n', strip=True)

            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = '\n'.join(lines)

            extraction_time = int((time.time() - start_time) * 1000)

            return ExtractionResult(
                text_content=text,
                html_content=html_content,
                word_count=len(text.split()) if text else 0,
                char_count=len(text) if text else 0,
                extraction_time_ms=extraction_time,
                extractor_used=ExtractorType.BEAUTIFULSOUP,
                success=True
            )
        except Exception as e:
            return ExtractionResult(
                success=False,
                error_message=str(e),
                extractor_used=ExtractorType.BEAUTIFULSOUP
            )

    def extract_metadata(self, html_content: str, url: str) -> WebSourceMetadata:
        """Extract metadata from HTML"""
        if not BS4_AVAILABLE:
            return WebSourceMetadata()

        try:
            soup = BeautifulSoup(html_content, 'lxml')
            metadata = WebSourceMetadata()

            # Title
            title_tag = soup.find('title')
            if title_tag:
                metadata.title = title_tag.get_text(strip=True)

            # Meta tags
            for meta in soup.find_all('meta'):
                name = meta.get('name', '').lower()
                prop = meta.get('property', '').lower()
                content = meta.get('content', '')

                if name == 'description' or prop == 'og:description':
                    metadata.description = content
                elif name == 'author':
                    metadata.author = content
                elif name == 'keywords':
                    metadata.keywords = [k.strip() for k in content.split(',')]
                elif prop == 'og:site_name':
                    metadata.site_name = content
                elif prop == 'og:image':
                    metadata.og_image = content
                elif prop == 'article:published_time':
                    try:
                        metadata.published_date = datetime.fromisoformat(
                            content.replace('Z', '+00:00')
                        )
                    except:
                        pass
                elif prop == 'article:modified_time':
                    try:
                        metadata.modified_date = datetime.fromisoformat(
                            content.replace('Z', '+00:00')
                        )
                    except:
                        pass

            # Language
            html_tag = soup.find('html')
            if html_tag:
                metadata.language = html_tag.get('lang')

            # Canonical URL
            canonical = soup.find('link', rel='canonical')
            if canonical:
                metadata.canonical_url = canonical.get('href')

            # Detect content type
            metadata.content_type = self._detect_content_type(url, metadata)

            return metadata
        except Exception:
            return WebSourceMetadata()

    def _detect_content_type(
        self,
        url: str,
        metadata: WebSourceMetadata
    ) -> ContentType:
        """Detect content type based on URL and metadata"""
        url_lower = url.lower()
        domain = urlparse(url).netloc.lower()

        if 'blog' in url_lower or 'blog' in domain:
            return ContentType.BLOG
        elif 'docs' in url_lower or 'documentation' in url_lower:
            return ContentType.DOCUMENTATION
        elif 'wiki' in domain or 'wikipedia' in domain:
            return ContentType.WIKI
        elif 'news' in domain or '/news/' in url_lower:
            return ContentType.NEWS
        elif '/article/' in url_lower or 'article' in (metadata.description or '').lower():
            return ContentType.ARTICLE
        else:
            return ContentType.GENERIC

    def extract_links(self, html_content: str, base_url: str) -> List[LinkInfo]:
        """Extract links from HTML"""
        if not BS4_AVAILABLE:
            return []

        try:
            soup = BeautifulSoup(html_content, 'lxml')
            base_domain = urlparse(base_url).netloc
            links = []

            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue

                # Make absolute URL
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)

                # Only keep http/https links
                if parsed.scheme not in ['http', 'https']:
                    continue

                is_internal = parsed.netloc == base_domain

                links.append(LinkInfo(
                    url=full_url,
                    text=a.get_text(strip=True)[:200],
                    is_internal=is_internal
                ))

            # Remove duplicates
            seen = set()
            unique_links = []
            for link in links:
                if link.url not in seen:
                    seen.add(link.url)
                    unique_links.append(link)

            return unique_links[:100]  # Limit to 100 links
        except Exception:
            return []

    def extract_images(self, html_content: str, base_url: str) -> List[ImageFromWeb]:
        """Extract images from HTML"""
        if not BS4_AVAILABLE:
            return []

        try:
            soup = BeautifulSoup(html_content, 'lxml')
            images = []

            for img in soup.find_all('img'):
                src = img.get('src', '')
                if not src:
                    continue

                # Make absolute URL
                full_url = urljoin(base_url, src)

                images.append(ImageFromWeb(
                    url=full_url,
                    alt_text=img.get('alt', '')[:200],
                    caption="",
                    width=int(img.get('width')) if img.get('width', '').isdigit() else None,
                    height=int(img.get('height')) if img.get('height', '').isdigit() else None
                ))

            return images[:50]  # Limit to 50 images
        except Exception:
            return []


class WebContentService:
    """Service for managing web sources"""

    # In-memory storage (replace with database in production)
    _web_sources: Dict[str, WebSource] = {}

    def __init__(self):
        self.extractor = WebContentExtractor()
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; KMS-RAG-Bot/1.0; +https://kms.example.com/bot)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6',
            }
        )

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()

    async def fetch_url(self, url: str) -> Tuple[Optional[str], int, Optional[str]]:
        """
        Fetch content from URL

        Returns:
            Tuple of (html_content, status_code, error_message)
        """
        try:
            response = await self.http_client.get(url)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                if 'text/html' in content_type or 'application/xhtml' in content_type:
                    return response.text, response.status_code, None
                else:
                    return None, response.status_code, f"Unsupported content type: {content_type}"
            else:
                return None, response.status_code, f"HTTP {response.status_code}"
        except httpx.TimeoutException:
            return None, 0, "Request timeout"
        except httpx.RequestError as e:
            return None, 0, f"Request error: {str(e)}"
        except Exception as e:
            return None, 0, f"Unexpected error: {str(e)}"

    def _compute_content_hash(self, content: str) -> str:
        """Compute hash of content for change detection"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]

    async def create_web_source(
        self,
        request: WebSourceCreate,
        user_id: Optional[str] = None
    ) -> WebSource:
        """Create a new web source and start processing"""
        parsed_url = urlparse(request.url)
        web_source_id = f"ws_{uuid.uuid4().hex[:12]}"

        # Create initial web source
        web_source = WebSource(
            id=web_source_id,
            url=request.url,
            display_name=request.name or parsed_url.netloc + parsed_url.path[:50],
            domain=parsed_url.netloc,
            status=WebSourceStatus.PENDING,
            tags=request.tags,
            extractor=request.extractor,
            include_images=request.include_images,
            include_links=request.include_links,
            created_by=user_id
        )

        self._web_sources[web_source_id] = web_source

        # Start async processing
        asyncio.create_task(self._process_web_source(web_source_id))

        return web_source

    async def create_bulk_web_sources(
        self,
        request: WebSourceBulkCreate,
        user_id: Optional[str] = None
    ) -> List[WebSource]:
        """Create multiple web sources"""
        sources = []
        for url in request.urls:
            single_request = WebSourceCreate(
                url=url,
                tags=request.tags,
                extractor=request.extractor
            )
            source = await self.create_web_source(single_request, user_id)
            sources.append(source)
        return sources

    async def _process_web_source(self, web_source_id: str):
        """Process a web source (fetch, extract, chunk, embed)"""
        web_source = self._web_sources.get(web_source_id)
        if not web_source:
            return

        try:
            # Step 1: Fetch
            web_source.status = WebSourceStatus.FETCHING
            self._web_sources[web_source_id] = web_source

            fetch_start = time.time()
            html_content, status_code, error = await self.fetch_url(web_source.url)
            fetch_time = int((time.time() - fetch_start) * 1000)

            web_source.http_status_code = status_code
            web_source.stats.fetch_time_ms = fetch_time

            if html_content is None:
                web_source.status = WebSourceStatus.ERROR
                web_source.error_message = error
                self._web_sources[web_source_id] = web_source
                return

            # Compute content hash
            web_source.content_hash = self._compute_content_hash(html_content)

            # Step 2: Extract content
            web_source.status = WebSourceStatus.EXTRACTING
            self._web_sources[web_source_id] = web_source

            # Extract metadata
            web_source.metadata = self.extractor.extract_metadata(
                html_content, web_source.url
            )

            # Update display name with title if available
            if web_source.metadata.title and not web_source.display_name.startswith('http'):
                web_source.display_name = web_source.metadata.title[:100]

            # Extract main content
            if web_source.extractor == ExtractorType.TRAFILATURA:
                extraction = await self.extractor.extract_with_trafilatura(
                    html_content, web_source.url
                )
            else:
                extraction = await self.extractor.extract_with_beautifulsoup(
                    html_content, web_source.url
                )

            if not extraction.success:
                # Fallback to other extractor
                if web_source.extractor == ExtractorType.TRAFILATURA:
                    extraction = await self.extractor.extract_with_beautifulsoup(
                        html_content, web_source.url
                    )
                else:
                    extraction = await self.extractor.extract_with_trafilatura(
                        html_content, web_source.url
                    )

            if not extraction.success or not extraction.text_content:
                web_source.status = WebSourceStatus.ERROR
                web_source.error_message = extraction.error_message or "No content extracted"
                self._web_sources[web_source_id] = web_source
                return

            web_source.extracted_text = extraction.text_content
            web_source.stats.word_count = extraction.word_count
            web_source.stats.char_count = extraction.char_count
            web_source.stats.extraction_time_ms = extraction.extraction_time_ms

            # Extract links if requested
            if web_source.include_links:
                web_source.extracted_links = self.extractor.extract_links(
                    html_content, web_source.url
                )
                web_source.stats.link_count = len(web_source.extracted_links)

            # Extract images if requested
            if web_source.include_images:
                web_source.extracted_images = self.extractor.extract_images(
                    html_content, web_source.url
                )
                web_source.stats.image_count = len(web_source.extracted_images)

            web_source.fetched_at = datetime.utcnow()

            # Step 3: Chunking
            web_source.status = WebSourceStatus.CHUNKING
            self._web_sources[web_source_id] = web_source

            chunks = await self._chunk_content(extraction.text_content, web_source.url)
            web_source.stats.chunk_count = len(chunks)

            # Step 4: Embedding and indexing to Neo4j
            web_source.status = WebSourceStatus.EMBEDDING
            self._web_sources[web_source_id] = web_source

            # Index to Neo4j with embeddings
            indexed = await self._index_to_neo4j(web_source, chunks)
            if not indexed:
                print(f"[WebContentService] Warning: Neo4j indexing skipped for {web_source_id}")

            # Done
            web_source.status = WebSourceStatus.READY
            web_source.processed_at = datetime.utcnow()
            web_source.stats.last_fetched = datetime.utcnow()
            web_source.updated_at = datetime.utcnow()
            self._web_sources[web_source_id] = web_source

        except Exception as e:
            web_source.status = WebSourceStatus.ERROR
            web_source.error_message = str(e)
            self._web_sources[web_source_id] = web_source

    async def _chunk_content(
        self,
        content: str,
        source_url: str
    ) -> List[Dict[str, Any]]:
        """
        Chunk content for embedding using semantic chunking.
        """
        # Split by paragraphs first
        paragraphs = content.split('\n\n')
        chunks = []
        chunk_size = 1000  # Target chunk size in characters
        overlap_words = 20  # Number of words to overlap

        current_chunk = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += "\n\n" + para if current_chunk else para
            else:
                if current_chunk:
                    chunks.append({
                        "id": f"wc_{uuid.uuid4().hex[:8]}",
                        "content": current_chunk.strip(),
                        "source_url": source_url,
                        "index": len(chunks)
                    })
                # Start new chunk with overlap from end of previous
                words = current_chunk.split()
                actual_overlap = min(overlap_words, len(words) // 4)
                overlap_text = ' '.join(words[-actual_overlap:]) if actual_overlap > 0 else ""
                current_chunk = overlap_text + " " + para if overlap_text else para

        # Add remaining content
        if current_chunk.strip():
            chunks.append({
                "id": f"wc_{uuid.uuid4().hex[:8]}",
                "content": current_chunk.strip(),
                "source_url": source_url,
                "index": len(chunks)
            })

        return chunks

    async def _index_to_neo4j(
        self,
        web_source: WebSource,
        chunks: List[Dict[str, Any]]
    ) -> bool:
        """
        Index web source and chunks to Neo4j with embeddings.
        """
        try:
            from .web_source_indexer import get_web_source_indexer

            indexer = get_web_source_indexer()
            success = await indexer.index_web_source(
                web_source_id=web_source.id,
                url=web_source.url,
                title=web_source.metadata.title or web_source.display_name,
                content=web_source.extracted_text or "",
                chunks=chunks,
                metadata={
                    "domain": web_source.domain,
                    "content_type": web_source.metadata.content_type.value if web_source.metadata.content_type else "generic",
                    "language": web_source.metadata.language,
                    "author": web_source.metadata.author,
                    "tags": web_source.tags
                }
            )
            return success
        except Exception as e:
            print(f"[WebContentService] Neo4j indexing failed: {e}")
            return False

    async def get_web_source(self, web_source_id: str) -> Optional[WebSource]:
        """Get web source by ID"""
        return self._web_sources.get(web_source_id)

    async def list_web_sources(
        self,
        user_id: Optional[str] = None,
        status: Optional[WebSourceStatus] = None,
        domain: Optional[str] = None,
        tags: Optional[List[str]] = None,
        page: int = 1,
        limit: int = 20
    ) -> Tuple[List[WebSourceListItem], int]:
        """List web sources with filtering"""
        sources = list(self._web_sources.values())

        # Apply filters
        if user_id:
            sources = [s for s in sources if s.created_by == user_id]
        if status:
            sources = [s for s in sources if s.status == status]
        if domain:
            sources = [s for s in sources if domain.lower() in s.domain.lower()]
        if tags:
            sources = [s for s in sources if any(t in s.tags for t in tags)]

        # Sort by created_at descending
        sources.sort(key=lambda x: x.created_at, reverse=True)

        total = len(sources)
        start = (page - 1) * limit
        end = start + limit

        # Convert to list items
        list_items = [
            WebSourceListItem(
                id=s.id,
                url=s.url,
                display_name=s.display_name,
                domain=s.domain,
                status=s.status,
                chunk_count=s.stats.chunk_count,
                word_count=s.stats.word_count,
                tags=s.tags,
                created_at=s.created_at,
                fetched_at=s.fetched_at,
                error_message=s.error_message
            )
            for s in sources[start:end]
        ]

        return list_items, total

    async def refresh_web_source(
        self,
        web_source_id: str,
        force: bool = False
    ) -> Tuple[bool, str]:
        """Refresh web source content"""
        web_source = self._web_sources.get(web_source_id)
        if not web_source:
            return False, "Web source not found"

        if web_source.status in [WebSourceStatus.FETCHING, WebSourceStatus.EXTRACTING,
                                  WebSourceStatus.CHUNKING, WebSourceStatus.EMBEDDING]:
            return False, "Processing in progress"

        # Fetch new content
        html_content, status_code, error = await self.fetch_url(web_source.url)
        if html_content is None:
            return False, error or "Failed to fetch content"

        # Check if content changed
        new_hash = self._compute_content_hash(html_content)
        if not force and new_hash == web_source.content_hash:
            web_source.stats.last_checked = datetime.utcnow()
            self._web_sources[web_source_id] = web_source
            return True, "Content unchanged"

        # Content changed - reprocess
        web_source.content_hash = new_hash
        self._web_sources[web_source_id] = web_source

        asyncio.create_task(self._process_web_source(web_source_id))
        return True, "Refresh started"

    async def delete_web_source(
        self,
        web_source_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        """Delete a web source and its index from Neo4j"""
        web_source = self._web_sources.get(web_source_id)
        if not web_source:
            return False

        # Check ownership if user_id provided
        if user_id and web_source.created_by and web_source.created_by != user_id:
            return False

        # Delete from in-memory storage
        del self._web_sources[web_source_id]

        # Delete from Neo4j
        try:
            from .web_source_indexer import get_web_source_indexer
            indexer = get_web_source_indexer()
            await indexer.delete_web_source_index(web_source_id)
        except Exception as e:
            print(f"[WebContentService] Neo4j deletion failed: {e}")

        return True

    async def search_web_sources(
        self,
        query: str,
        limit: int = 20
    ) -> List[WebSourceListItem]:
        """Search web sources by content or metadata"""
        query_lower = query.lower()
        results = []

        for source in self._web_sources.values():
            if source.status != WebSourceStatus.READY:
                continue

            # Search in title, URL, tags, and content
            score = 0
            if query_lower in source.display_name.lower():
                score += 3
            if query_lower in source.url.lower():
                score += 2
            if any(query_lower in tag.lower() for tag in source.tags):
                score += 2
            if source.extracted_text and query_lower in source.extracted_text.lower():
                score += 1

            if score > 0:
                results.append((score, source))

        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)

        return [
            WebSourceListItem(
                id=s.id,
                url=s.url,
                display_name=s.display_name,
                domain=s.domain,
                status=s.status,
                chunk_count=s.stats.chunk_count,
                word_count=s.stats.word_count,
                tags=s.tags,
                created_at=s.created_at,
                fetched_at=s.fetched_at,
                error_message=s.error_message
            )
            for _, s in results[:limit]
        ]


# Singleton instance
_web_content_service: Optional[WebContentService] = None


def get_web_content_service() -> WebContentService:
    """Get or create web content service instance"""
    global _web_content_service
    if _web_content_service is None:
        _web_content_service = WebContentService()
    return _web_content_service
