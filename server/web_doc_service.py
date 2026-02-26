"""Web Document Crawler + Search Service

Parses of7/webdoc.md for product URLs, crawls all pages (HTML + PDF),
builds a keyword+IDF index for fast in-memory search.

Adapted from kms-docker-remote WebDocCrawlerService + WebDocSearchService.
PDF support uses PyMuPDF (fitz) for text extraction and section-based chunking.
"""
import asyncio
import hashlib
import json
import logging
import math
import os
import re
import tempfile
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

WEBDOC_MD_PATH = os.environ.get("WEBDOC_MD_PATH", "/data/of7/webdoc.md")
WEB_DOC_INDEX_PATH = os.environ.get("WEB_DOC_INDEX_PATH", "/data/web_doc_index.json")
CRAWL_META_PATH = os.environ.get("CRAWL_META_PATH", "/data/web_doc_crawl_meta.json")


# ── Data Models ──

@dataclass
class WebDocPage:
    url: str
    product: str
    title: str
    headings: List[str] = field(default_factory=list)
    snippet: str = ""
    keywords: List[str] = field(default_factory=list)


@dataclass
class WebDocIndex:
    pages: List[WebDocPage] = field(default_factory=list)
    crawled_at: str = ""
    total_pages: int = 0
    products: List[str] = field(default_factory=list)


@dataclass
class CrawlMeta:
    """URL-level crawl metadata for incremental crawling + PDF caching."""
    url: str
    product: str
    etag: str = ""
    last_modified: str = ""
    pdf_hash: str = ""
    crawled_at: str = ""
    page_count: int = 0


# ── Crawl Metadata Persistence ──

def _load_crawl_meta() -> Dict[str, CrawlMeta]:
    """Load {url: CrawlMeta} from disk."""
    if not os.path.exists(CRAWL_META_PATH):
        return {}
    try:
        with open(CRAWL_META_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            url: CrawlMeta(**entry)
            for url, entry in data.items()
        }
    except Exception as e:
        logger.warning(f"Failed to load crawl meta: {e}")
        return {}


def _save_crawl_meta(meta: Dict[str, CrawlMeta]) -> None:
    """Persist {url: CrawlMeta} to disk."""
    os.makedirs(os.path.dirname(CRAWL_META_PATH) or ".", exist_ok=True)
    with open(CRAWL_META_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {url: asdict(cm) for url, cm in meta.items()},
            f, ensure_ascii=False, indent=2,
        )


# ── Tokenization (from KMS) ──

_TOKEN_RE = re.compile(
    r'[a-z0-9][a-z0-9_\-]*[a-z0-9]|[a-z0-9]'
    r'|[\u30a0-\u30ff]{2,}'    # katakana
    r'|[\u4e00-\u9fff]+'       # kanji
    r'|[\uac00-\ud7af]{2,}'   # hangul
    r'|[\u3040-\u309f]{2,}',  # hiragana
)

_STOPWORDS = frozenset([
    "the", "a", "an", "of", "in", "on", "at", "to", "for",
    "is", "are", "was", "were", "be", "and", "or", "not",
    "it", "this", "that", "with", "from", "by", "as",
    "about", "what", "how", "do", "does",
    "tell", "me", "explain", "please", "describe",
    "の", "は", "が", "を", "に", "で", "と", "も", "や", "か",
    "へ", "から", "まで", "より", "について", "とは",
    "ている", "された", "される", "している", "できる",
    "ですか", "ますか", "ません",
    "教えて", "説明して", "知りたい",
])


def _tokenize(text: str) -> List[str]:
    raw = _TOKEN_RE.findall(text.lower())
    tokens = []
    for t in raw:
        if t in _STOPWORDS:
            continue
        if len(t) == 1 and t.isascii():
            continue
        if len(t) == 1 and '\u4e00' <= t <= '\u9fff':
            continue
        tokens.append(t)
    return tokens


def _extract_keywords(title: str, headings: List[str], snippet: str) -> List[str]:
    text = (title + " " + " ".join(headings) + " " + snippet).lower()
    tokens = _TOKEN_RE.findall(text)
    seen: Set[str] = set()
    result = []
    for t in tokens:
        if t not in seen and not (len(t) == 1 and t.isascii()):
            seen.add(t)
            result.append(t)
    return result[:50]


# ── PDF Processing (from KMS section_chunker) ──

_SECTION_PATTERNS = [
    re.compile(r'^(\d+\.(?:\d+\.)*)\s*([^\n]+)', re.MULTILINE),   # "2.3.2. Title"
    re.compile(r'^(第\d+章)\s*([^\n]+)', re.MULTILINE),            # Japanese chapter
    re.compile(r'^(Chapter\s+\d+)\s*([^\n]+)', re.MULTILINE),     # English chapter
]

PDF_MAX_CHUNK = 1500
PDF_MIN_CHUNK = 200
PDF_OVERLAP = 100


def _pdf_extract_text(pdf_path: str) -> List[Tuple[int, str]]:
    """Extract per-page text from PDF using PyMuPDF (fitz)."""
    import fitz
    doc = fitz.open(pdf_path)
    pages = []
    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        if text.strip():
            pages.append((page_num, text))
    doc.close()
    return pages


def _pdf_find_sections(text: str) -> List[Tuple[int, str, str]]:
    """Find section headers in text → [(position, section_id, title), ...]"""
    sections = []
    for pattern in _SECTION_PATTERNS:
        for match in pattern.finditer(text):
            section_id = match.group(1).strip().rstrip('.')
            section_title = match.group(2).strip()
            if len(section_title) > 2 and not any(x in section_title for x in ['...', '●', '>>-']):
                sections.append((match.start(), section_id, section_title))
    sections.sort(key=lambda x: x[0])
    return sections


def _split_large_text(content: str, header: str) -> List[str]:
    """Split large section into chunks at natural boundaries."""
    available = PDF_MAX_CHUNK - len(header)
    chunks = []
    start = 0
    while start < len(content):
        end = min(start + available, len(content))
        if end < len(content):
            last_break = max(
                content.rfind('。', start, end),
                content.rfind('.', start, end),
                content.rfind('\n\n', start, end),
                content.rfind('\n', start, end),
            )
            if last_break > start + available * 0.5:
                end = last_break + 1
        chunk = content[start:end].strip()
        if chunk:
            chunks.append(header + chunk)
        start = end - PDF_OVERLAP if end < len(content) else len(content)
    return chunks if chunks else [header + content]


def _pdf_to_chunks(pdf_path: str) -> List[dict]:
    """Extract PDF → section-based chunks → list of {title, headings, snippet}.

    Each chunk becomes a WebDocPage entry for indexing.
    """
    pages = _pdf_extract_text(pdf_path)
    if not pages:
        return []

    full_text = "\n".join(text for _, text in pages)
    sections = _pdf_find_sections(full_text)

    chunks = []

    if not sections:
        # Fallback: fixed-size chunking
        start = 0
        idx = 0
        while start < len(full_text):
            end = min(start + PDF_MAX_CHUNK, len(full_text))
            if end < len(full_text):
                lb = full_text.rfind('\n', start, end)
                if lb > start + PDF_MAX_CHUNK * 0.5:
                    end = lb
            chunk = full_text[start:end].strip()
            if chunk and len(chunk) >= PDF_MIN_CHUNK:
                # First line as title, rest as snippet
                lines = chunk.split('\n', 1)
                chunks.append({
                    "title": lines[0].strip()[:200],
                    "headings": [],
                    "snippet": chunk[:500],
                })
            idx += 1
            start = end - PDF_OVERLAP if end < len(full_text) else len(full_text)
        return chunks

    # Section-based chunking
    for i, (pos, section_id, section_title) in enumerate(sections):
        next_pos = sections[i + 1][0] if i + 1 < len(sections) else len(full_text)
        content = full_text[pos:next_pos].strip()

        # Remove section header line from content
        content_lines = content.split('\n')
        if content_lines and section_id in content_lines[0]:
            content_lines = content_lines[1:]
        content = '\n'.join(content_lines).strip()

        if len(content) < PDF_MIN_CHUNK:
            continue

        header = f"[{section_id}. {section_title}]\n\n"

        if len(content) <= PDF_MAX_CHUNK:
            chunks.append({
                "title": f"{section_id}. {section_title}",
                "headings": [section_title],
                "snippet": (header + content)[:500],
            })
        else:
            sub_chunks = _split_large_text(content, header)
            for j, sub in enumerate(sub_chunks):
                part_label = f" (part {j+1}/{len(sub_chunks)})" if len(sub_chunks) > 1 else ""
                chunks.append({
                    "title": f"{section_id}. {section_title}{part_label}",
                    "headings": [section_title],
                    "snippet": sub[:500],
                })

    return chunks


async def crawl_pdf(
    client,
    url: str,
    product: str,
    sem: asyncio.Semaphore,
    crawl_meta: Optional[Dict[str, CrawlMeta]] = None,
) -> Tuple[List[WebDocPage], bool]:
    """Download a PDF, extract text, chunk into WebDocPage entries.

    Returns (pages, changed).  When the PDF hash matches the cached value
    the function returns ([], False) so the caller can keep existing chunks.
    """
    async with sem:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"PDF download failed ({resp.status_code}): {url}")
                return [], True
            pdf_bytes = resp.content
        except Exception as e:
            logger.warning(f"PDF download error {url}: {e}")
            return [], True

    # ── PDF hash caching ──
    new_hash = hashlib.sha256(pdf_bytes).hexdigest()
    if crawl_meta is not None:
        prev = crawl_meta.get(url)
        if prev and prev.pdf_hash == new_hash:
            logger.info(f"PDF unchanged (hash match), reusing cache: {url}")
            return [], False  # caller keeps existing pages

    # Write to temp file and process
    pages = []
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        chunks = _pdf_to_chunks(tmp_path)
        logger.info(f"PDF chunked: {len(chunks)} chunks from {url}")

        # Derive a base title from the URL filename
        pdf_filename = url.rsplit("/", 1)[-1] if "/" in url else url

        for i, chunk in enumerate(chunks):
            title = chunk["title"] or f"{pdf_filename} chunk {i+1}"
            headings = chunk.get("headings", [])
            snippet = chunk.get("snippet", "")
            keywords = _extract_keywords(title, headings, snippet)

            pages.append(WebDocPage(
                url=f"{url}#chunk-{i+1}",
                product=product,
                title=title,
                headings=headings[:20],
                snippet=snippet,
                keywords=keywords,
            ))
    except Exception as e:
        logger.error(f"PDF processing error {url}: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # Update meta with new hash
    if crawl_meta is not None:
        crawl_meta[url] = CrawlMeta(
            url=url, product=product, pdf_hash=new_hash,
            crawled_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            page_count=len(pages),
        )

    return pages, True


def _is_pdf_url(url: str) -> bool:
    """Check if URL points to a PDF file."""
    parsed = urlparse(url)
    return parsed.path.lower().endswith('.pdf')


# ── Webdoc.md Parser ──

def parse_webdoc_md(path: str = WEBDOC_MD_PATH) -> Dict[str, List[str]]:
    """Parse webdoc.md → {product: [url, ...]}"""
    if not os.path.exists(path):
        logger.warning(f"webdoc.md not found: {path}")
        return {}

    result: Dict[str, List[str]] = {}
    current_product = None

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("** "):
                current_product = line[3:].strip()
                if current_product and current_product not in result:
                    result[current_product] = []
            elif line.startswith("http") and current_product:
                result[current_product].append(line)

    return result


# ── Crawler ──

# Sentinel: server returned 304 Not Modified (page unchanged)
_NOT_MODIFIED: str = "__304__"


async def _fetch(
    client,
    url: str,
    sem: asyncio.Semaphore,
    crawl_meta: Optional[Dict[str, CrawlMeta]] = None,
) -> Optional[str]:
    """Fetch URL with conditional-GET support (ETag / Last-Modified).

    Returns HTML string, _NOT_MODIFIED sentinel, or None on error.
    """
    async with sem:
        try:
            headers: Dict[str, str] = {}
            if crawl_meta is not None:
                prev = crawl_meta.get(url)
                if prev:
                    if prev.etag:
                        headers["If-None-Match"] = prev.etag
                    if prev.last_modified:
                        headers["If-Modified-Since"] = prev.last_modified

            resp = await client.get(url, headers=headers)

            if resp.status_code == 304:
                logger.debug(f"304 Not Modified: {url}")
                return _NOT_MODIFIED

            if resp.status_code == 200:
                # Store new ETag / Last-Modified in meta
                if crawl_meta is not None:
                    new_etag = resp.headers.get("etag", "")
                    new_lm = resp.headers.get("last-modified", "")
                    if new_etag or new_lm:
                        meta = crawl_meta.get(url) or CrawlMeta(url=url, product="")
                        meta.etag = new_etag
                        meta.last_modified = new_lm
                        meta.crawled_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
                        crawl_meta[url] = meta
                return resp.text
        except Exception as e:
            logger.debug(f"Fetch error {url}: {e}")
    return None


def _extract_page_info(html: str, url: str) -> tuple:
    """Extract title, headings, snippet from HTML using regex (no bs4)."""
    title = ""
    headings = []
    snippet = ""

    # title: <h1> or <title>
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    if h1:
        title = re.sub(r'<[^>]+>', '', h1.group(1)).strip()
    else:
        t = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
        if t:
            title = t.group(1).strip().split("|")[0].strip()

    # h2/h3 headings
    for m in re.finditer(r'<h[23][^>]*>(.*?)</h[23]>', html, re.DOTALL):
        h_text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if h_text and len(h_text) < 200:
            headings.append(h_text)

    # snippet from <article>, <main>, or <body>
    for tag in ('article', 'main', 'body'):
        m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', html, re.DOTALL)
        if m:
            text = re.sub(r'<[^>]+>', ' ', m.group(1))
            text = re.sub(r'\s+', ' ', text).strip()
            snippet = text[:300]
            break

    return title, headings, snippet


def _discover_links(html: str, base_url: str) -> Set[str]:
    """Find all same-origin page links from HTML."""
    parsed_base = urlparse(base_url)
    # For GitHub Pages: restrict to same path prefix
    base_path_prefix = parsed_base.path.rsplit("/", 1)[0] if "/" in parsed_base.path else ""

    links: Set[str] = set()
    for m in re.finditer(r'href="([^"#]+)"', html):
        href = m.group(1)
        if href.startswith("javascript") or href.startswith("mailto"):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        # Same host only
        if parsed.netloc != parsed_base.netloc:
            continue
        # Must be under the same base path prefix
        if base_path_prefix and not parsed.path.startswith(base_path_prefix):
            continue
        # Only .html or path-ending pages (no anchors, no assets)
        if parsed.path.endswith(('.html', '/')):
            links.add(full.split("#")[0])
        elif '.' not in parsed.path.rsplit('/', 1)[-1]:
            # Path without extension (could be a page)
            links.add(full.split("#")[0])

    return links


async def crawl_site(
    client,
    entry_url: str,
    product: str,
    sem: asyncio.Semaphore,
    max_pages: int = 500,
    crawl_meta: Optional[Dict[str, CrawlMeta]] = None,
) -> Tuple[List[WebDocPage], int, List[str]]:
    """Crawl a single site starting from entry_url.

    Returns (pages, skipped_count, skipped_urls).
    """
    visited: Set[str] = set()
    to_visit: Set[str] = {entry_url}
    pages: List[WebDocPage] = []
    skipped = 0
    skipped_urls: List[str] = []

    while to_visit and len(visited) < max_pages:
        # Batch: crawl up to 10 at a time
        batch = list(to_visit)[:10]
        to_visit -= set(batch)

        tasks = [_fetch(client, url, sem, crawl_meta) for url in batch]
        results = await asyncio.gather(*tasks)

        for url, html in zip(batch, results):
            visited.add(url)
            if html is None:
                continue
            if html is _NOT_MODIFIED:
                skipped += 1
                skipped_urls.append(url)
                continue

            title, headings, snippet = _extract_page_info(html, url)
            if not title and not snippet:
                continue

            keywords = _extract_keywords(title, headings, snippet)
            pages.append(WebDocPage(
                url=url,
                product=product,
                title=title,
                headings=headings[:20],
                snippet=snippet,
                keywords=keywords,
            ))

            # Discover new links
            new_links = _discover_links(html, entry_url)
            for link in new_links:
                if link not in visited:
                    to_visit.add(link)

    # Update meta for the entry URL with page count
    if crawl_meta is not None and pages:
        meta = crawl_meta.get(entry_url) or CrawlMeta(url=entry_url, product=product)
        meta.product = product
        meta.crawled_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        meta.page_count = len(pages)
        crawl_meta[entry_url] = meta

    return pages, skipped, skipped_urls


def _merge_index(existing_path: str, new_pages: List[WebDocPage], product: str) -> None:
    """Replace pages for `product` in the existing index, keep other products intact."""
    existing_pages: List[dict] = []
    existing_products: Set[str] = set()

    if os.path.exists(existing_path):
        try:
            with open(existing_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            existing_pages = data.get("pages", [])
        except Exception:
            existing_pages = []

    # Remove old pages for this product
    kept = [p for p in existing_pages if p.get("product", "") != product]
    # Add new pages
    merged = kept + [asdict(p) for p in new_pages]

    for p in merged:
        existing_products.add(p.get("product", ""))

    os.makedirs(os.path.dirname(existing_path) or ".", exist_ok=True)
    with open(existing_path, "w", encoding="utf-8") as f:
        json.dump({
            "pages": merged,
            "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_pages": len(merged),
            "products": sorted(existing_products),
        }, f, ensure_ascii=False, indent=2)


async def crawl_all(
    webdoc_path: str = WEBDOC_MD_PATH,
    concurrency: int = 5,
    product: str = "",
) -> WebDocIndex:
    """Crawl URLs from webdoc.md and build/update index.

    Args:
        product: If non-empty, only crawl URLs for this product and merge
                 results into the existing index.  Empty = crawl all.
    """
    import httpx

    product_urls = parse_webdoc_md(webdoc_path)
    if not product_urls:
        return WebDocIndex()

    # Filter to specific product if requested
    if product:
        product_lower = product.lower()
        filtered = {
            p: urls for p, urls in product_urls.items()
            if p.lower() == product_lower
        }
        if not filtered:
            logger.warning(f"Product '{product}' not found in webdoc.md")
            return WebDocIndex()
        product_urls = filtered

    crawl_meta = _load_crawl_meta()
    sem = asyncio.Semaphore(concurrency)
    all_pages: List[WebDocPage] = []
    products_seen: Set[str] = set()
    stats = {"html_crawled": 0, "html_skipped": 0, "pdf_crawled": 0, "pdf_cached": 0}

    # Pre-load existing index so cached PDFs can reuse their pages
    _existing_pages_by_url: Dict[str, List[WebDocPage]] = {}
    if os.path.exists(WEB_DOC_INDEX_PATH):
        try:
            with open(WEB_DOC_INDEX_PATH, "r", encoding="utf-8") as f:
                _existing_data = json.load(f)
            for p in _existing_data.get("pages", []):
                base_url = p["url"].split("#")[0]
                _existing_pages_by_url.setdefault(base_url, []).append(
                    WebDocPage(**p)
                )
        except Exception:
            pass

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        verify=False,
        headers={
            "User-Agent": "OfCode-WebDocCrawler/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    ) as client:
        for prod, urls in product_urls.items():
            products_seen.add(prod)
            for url in urls:
                if _is_pdf_url(url):
                    logger.info(f"PDF crawl {prod}: {url}")
                    pages, changed = await crawl_pdf(
                        client, url, prod, sem, crawl_meta,
                    )
                    if not changed:
                        # PDF unchanged — reuse existing pages from index
                        cached_pages = _existing_pages_by_url.get(url, [])
                        all_pages.extend(cached_pages)
                        stats["pdf_cached"] += 1
                        logger.info(f"  → PDF cached (hash match), reused {len(cached_pages)} chunks")
                    else:
                        all_pages.extend(pages)
                        stats["pdf_crawled"] += 1
                        logger.info(f"  → {len(pages)} chunks (new/changed)")
                else:
                    logger.info(f"HTML crawl {prod}: {url}")
                    pages, skipped, skipped_urls = await crawl_site(
                        client, url, prod, sem, crawl_meta=crawl_meta,
                    )
                    all_pages.extend(pages)
                    # Recover 304-skipped pages from existing index
                    for s_url in skipped_urls:
                        cached = _existing_pages_by_url.get(s_url, [])
                        all_pages.extend(cached)
                    stats["html_crawled"] += len(pages)
                    stats["html_skipped"] += skipped
                    logger.info(
                        f"  → {len(pages)} pages, {skipped} skipped (304)"
                    )

    _save_crawl_meta(crawl_meta)

    # ── Index persistence ──
    if product:
        # Selective crawl: merge into existing index
        _merge_index(WEB_DOC_INDEX_PATH, all_pages, product)
        # Re-read the merged index to return accurate totals
        try:
            with open(WEB_DOC_INDEX_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            index = WebDocIndex(
                pages=[WebDocPage(**p) for p in data.get("pages", [])],
                crawled_at=data.get("crawled_at", ""),
                total_pages=data.get("total_pages", 0),
                products=data.get("products", []),
            )
        except Exception:
            index = WebDocIndex(pages=all_pages, total_pages=len(all_pages))
    else:
        # Full crawl: rebuild the whole index
        index = WebDocIndex(
            pages=all_pages,
            crawled_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            total_pages=len(all_pages),
            products=sorted(products_seen),
        )
        os.makedirs(os.path.dirname(WEB_DOC_INDEX_PATH) or ".", exist_ok=True)
        with open(WEB_DOC_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "pages": [asdict(p) for p in index.pages],
                "crawled_at": index.crawled_at,
                "total_pages": index.total_pages,
                "products": index.products,
            }, f, ensure_ascii=False, indent=2)

    logger.info(
        f"WebDocIndex saved: {index.total_pages} pages → {WEB_DOC_INDEX_PATH} "
        f"(html={stats['html_crawled']}, html_304={stats['html_skipped']}, "
        f"pdf={stats['pdf_crawled']}, pdf_cached={stats['pdf_cached']})"
    )
    return index


# ── Search Service (from KMS WebDocSearchService) ──

class WebDocSearchService:
    TITLE_WEIGHT = 3.0
    CONTENT_WEIGHT = 1.0

    def __init__(self):
        self._pages: List[dict] = []
        self._loaded = False

    def load_index(self, path: str = WEB_DOC_INDEX_PATH) -> bool:
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._pages = []
            for p in data.get("pages", []):
                searchable = (
                    p.get("title", "") + " "
                    + " ".join(p.get("headings", [])) + " "
                    + p.get("snippet", "")
                ).lower()
                kw_set = frozenset(p.get("keywords", []))
                self._pages.append({
                    "url": p["url"],
                    "title": p.get("title", ""),
                    "title_lower": p.get("title", "").lower(),
                    "headings": p.get("headings", []),
                    "snippet": p.get("snippet", ""),
                    "product": p.get("product", ""),
                    "searchable": searchable,
                    "kw_set": kw_set,
                })
            self._loaded = True
            logger.info(f"WebDocSearchService loaded: {len(self._pages)} pages")
            return True
        except Exception as e:
            logger.warning(f"Failed to load web doc index: {e}")
            return False

    def reload(self):
        self._loaded = False
        self._pages = []
        self.load_index()

    def search(
        self,
        query: str,
        product: str = "",
        top_k: int = 5,
    ) -> List[dict]:
        if not self._loaded:
            self.load_index()
        if not self._pages:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        candidates = self._pages
        if product:
            product_lower = product.lower()
            filtered = [p for p in candidates if p["product"].lower() == product_lower]
            if filtered:
                candidates = filtered

        if not candidates:
            return []

        # IDF
        total = len(candidates)
        df: Dict[str, int] = {t: 0 for t in tokens}
        for page in candidates:
            s = page["searchable"]
            for t in tokens:
                if t in s:
                    df[t] += 1

        idf: Dict[str, float] = {}
        for t in tokens:
            idf[t] = math.log((total + 1) / (df[t] + 1)) + 1.0

        max_possible = sum(idf[t] * self.TITLE_WEIGHT for t in tokens)
        if max_possible <= 0:
            return []

        scored = []
        for page in candidates:
            title_lower = page["title_lower"]
            searchable = page["searchable"]
            score = 0.0
            matched = 0

            for t in tokens:
                if t in title_lower:
                    score += self.TITLE_WEIGHT * idf[t]
                    matched += 1
                elif t in searchable:
                    score += self.CONTENT_WEIGHT * idf[t]
                    matched += 1

            if score <= 0:
                continue

            if len(tokens) > 1:
                coverage = matched / len(tokens)
                score *= (0.5 + 0.5 * coverage)

            normalized = min(score / max_possible, 1.0)
            scored.append((normalized, score, page))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for norm_score, raw_score, page in scored[:top_k]:
            results.append({
                "url": page["url"],
                "title": page["title"],
                "product": page["product"],
                "score": round(norm_score, 4),
                "headings": page["headings"][:5],
                "snippet": page["snippet"][:200],
            })

        return results

    def get_status(self) -> dict:
        products: Dict[str, int] = {}
        for p in self._pages:
            prod = p.get("product", "unknown")
            products[prod] = products.get(prod, 0) + 1
        return {
            "loaded": self._loaded,
            "total_pages": len(self._pages),
            "products": products,
            "index_path": WEB_DOC_INDEX_PATH,
            "index_exists": os.path.exists(WEB_DOC_INDEX_PATH),
        }
