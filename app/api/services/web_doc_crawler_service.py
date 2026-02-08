"""
Web Document Crawler Service

docs.tmaxsoft.com (Antora 3.1.12) を1回クロールし、
ページURL・タイトル・見出しのローカルインデックスを構築します。

Usage:
    python -m scripts.crawl_web_docs          # 전체 크롤
    python -m scripts.crawl_web_docs --stats  # 인덱스 통계
"""
import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
WEB_DOC_INDEX_DIR = os.path.join(_PROJECT_ROOT, "uploads", "web_doc_index")

BASE_URL = "https://docs.tmaxsoft.com"
OPENFRAME_INDEX = "/ko/tmaxsoft_docs/main/openframe/index_openframe.html"


@dataclass
class WebDocPage:
    """크롤링된 개별 문서 페이지"""
    url: str
    component: str  # e.g. "openframe_base"
    version: str  # e.g. "7.1_MVS"
    guide: str  # e.g. "base-guide"
    title: str
    headings: List[str] = field(default_factory=list)
    snippet: str = ""  # 본문 200자
    language: str = "ja"
    product_id: str = ""
    keywords: List[str] = field(default_factory=list)  # title + headings에서 추출한 검색 키워드


@dataclass
class WebDocIndex:
    """전체 크롤링 인덱스"""
    pages: List[WebDocPage] = field(default_factory=list)
    crawled_at: str = ""
    total_pages: int = 0
    components: List[str] = field(default_factory=list)


# docs.tmaxsoft.com data-component → 내부 product_id 매핑
_COMPONENT_TO_PRODUCT: Dict[str, str] = {
    # MVS 계열
    "openframe_base": "mvs_openframe_7.1",
    "openframe_batch": "mvs_openframe_7.1",
    "openframe_osc": "mvs_openframe_7.1",
    "openframe_osi": "mvs_openframe_7.1",
    "openframe_hidb": "openframe_hidb_7",
    "openframe_tacf": "openframe_tacf_7",
    "openframe_gw": "mvs_openframe_7.1",
    "openframe_manager": "ofmanager_7",
    "openframe_common": "mvs_openframe_7.1",
    # MSP 계열
    "openframe_base_msp": "msp_openframe_7.3",
    "openframe_ndb_msp": "openframe_ndb_7",
    "openframe_batch_msp": "msp_openframe_7.3",
    "openframe_aim_msp": "openframe_aim_7",
    "openframe_tacf_msp": "openframe_tacf_7",
    "openframe_gw_msp": "msp_openframe_7.3",
    "openframe_common_msp": "msp_openframe_7.3",
    # XSP 계열
    "openframe_base_xsp": "xsp_openframe_7.3",
    "openframe_ndb_xsp": "openframe_ndb_7",
    "openframe_batch_xsp": "xsp_openframe_7.3",
    "openframe_aim_xsp": "openframe_aim_7",
    "openframe_tacf_xsp": "openframe_tacf_7",
    "openframe_gw_xsp": "xsp_openframe_7.3",
    "openframe_common_xsp": "xsp_openframe_7.3",
    # 컴파일러
    "openframe_cobol": "ofcobol_4",
    "openframe_pli": "mvs_openframe_7.1",
    "openframe_asm": "ofasm_4",
}

# 역매핑: product_id → component 리스트
PRODUCT_TO_COMPONENTS: Dict[str, List[str]] = {}
for _c, _p in _COMPONENT_TO_PRODUCT.items():
    PRODUCT_TO_COMPONENTS.setdefault(_p, []).append(_c)


def _extract_component_from_url(url: str) -> str:
    """URL 경로에서 Antora 컴포넌트명 추출"""
    parsed = urlparse(url)
    # /ko/openframe_base/7.1_MVS/base-guide/chapter-introduction.html
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2:
        return parts[1]  # openframe_base
    return ""


def _extract_version_from_url(url: str) -> str:
    """URL 경로에서 버전 추출"""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 3:
        return parts[2]  # 7.1_MVS
    return ""


def _extract_guide_from_url(url: str) -> str:
    """URL 경로에서 가이드명 추출"""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 4:
        return parts[3]  # base-guide
    return ""


def _get_product_id(component: str) -> str:
    """컴포넌트명으로 product_id 조회"""
    if component in _COMPONENT_TO_PRODUCT:
        return _COMPONENT_TO_PRODUCT[component]
    # 부분 매칭 시도
    for key, pid in _COMPONENT_TO_PRODUCT.items():
        if key in component or component in key:
            return pid
    return ""


class WebDocCrawlerService:
    """
    docs.tmaxsoft.com 크롤러

    1. OpenFrame 인덱스 페이지에서 컴포넌트 링크 추출
    2. 각 컴포넌트 페이지에서 sidebar nav-link로 전체 페이지 URL 수집
    3. 각 페이지의 title, headings, snippet 추출
    4. uploads/web_doc_index/index.json 저장
    """

    def __init__(self):
        self._index: Optional[WebDocIndex] = None
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                verify=False,  # docs.tmaxsoft.com SSL 인증서 이슈
                headers={
                    "User-Agent": "KMS-WebDocCrawler/1.0",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "ja,ko,en",
                },
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def index(self) -> Optional[WebDocIndex]:
        return self._index

    def load_index(self) -> Optional[WebDocIndex]:
        """디스크에서 인덱스 로드"""
        index_path = os.path.join(WEB_DOC_INDEX_DIR, "index.json")
        if not os.path.exists(index_path):
            return None
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            pages = [WebDocPage(**p) for p in data.get("pages", [])]
            self._index = WebDocIndex(
                pages=pages,
                crawled_at=data.get("crawled_at", ""),
                total_pages=data.get("total_pages", len(pages)),
                components=data.get("components", []),
            )
            logger.info(f"WebDocIndex loaded: {len(pages)} pages")
            return self._index
        except Exception as e:
            logger.warning(f"Failed to load web doc index: {e}")
            return None

    def save_index(self):
        """인덱스를 디스크에 저장"""
        if not self._index:
            return
        os.makedirs(WEB_DOC_INDEX_DIR, exist_ok=True)
        index_path = os.path.join(WEB_DOC_INDEX_DIR, "index.json")
        data = {
            "pages": [asdict(p) for p in self._index.pages],
            "crawled_at": self._index.crawled_at,
            "total_pages": self._index.total_pages,
            "components": self._index.components,
        }
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"WebDocIndex saved: {self._index.total_pages} pages → {index_path}")

    async def crawl_all(
        self,
        languages: Optional[List[str]] = None,
        concurrency: int = 5,
    ) -> WebDocIndex:
        """
        docs.tmaxsoft.com 전체 크롤링.

        1. OpenFrame 인덱스에서 컴포넌트 인덱스 페이지 URL 추출
        2. 각 컴포넌트의 sidebar nav-link에서 전체 페이지 발견
        3. 각 페이지 크롤링 (title, headings, snippet)
        """
        languages = languages or ["ja"]
        sem = asyncio.Semaphore(concurrency)
        client = await self._get_client()

        all_pages: List[WebDocPage] = []
        components_seen: Set[str] = set()

        for lang in languages:
            # Step 1: 컴포넌트 인덱스 URL 수집
            component_index_urls = await self._discover_component_indexes(client, lang, sem)
            logger.info(f"[{lang}] Discovered {len(component_index_urls)} component index pages")

            # Step 2: 각 컴포넌트 인덱스에서 가이드 링크 → sidebar nav-link로 전체 페이지 발견
            all_page_urls: Dict[str, Set[str]] = {}  # component → set of URLs
            for comp_url in component_index_urls:
                page_urls, component = await self._discover_pages_from_component_index(
                    client, comp_url, lang, sem,
                )
                if component:
                    components_seen.add(component)
                    all_page_urls.setdefault(component, set()).update(page_urls)

            total_urls = sum(len(urls) for urls in all_page_urls.values())
            logger.info(f"[{lang}] Total pages to crawl: {total_urls}")

            # Step 3: 각 페이지 크롤링 (병렬)
            tasks = []
            for component, urls in all_page_urls.items():
                for url in urls:
                    tasks.append(self._crawl_page(client, url, component, lang, sem))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, WebDocPage):
                    all_pages.append(result)
                elif isinstance(result, Exception):
                    logger.debug(f"Crawl error: {result}")

            logger.info(f"[{lang}] Crawled {sum(1 for r in results if isinstance(r, WebDocPage))} pages")

        self._index = WebDocIndex(
            pages=all_pages,
            crawled_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            total_pages=len(all_pages),
            components=sorted(components_seen),
        )
        self.save_index()
        return self._index

    async def _discover_component_indexes(
        self,
        client,
        lang: str,
        sem: asyncio.Semaphore,
    ) -> List[str]:
        """OpenFrame 인덱스에서 컴포넌트 인덱스 URL 추출"""
        index_url = f"{BASE_URL}/{lang}/tmaxsoft_docs/main/openframe/index_openframe.html"
        async with sem:
            try:
                resp = await client.get(index_url)
                if resp.status_code != 200:
                    logger.warning(f"Index page fetch failed: HTTP {resp.status_code}")
                    return []
            except Exception as e:
                logger.warning(f"Index page fetch error: {e}")
                return []

        html = resp.text
        urls = []
        # card-body-openframe 링크 추출 (컴포넌트 인덱스 페이지)
        for match in re.finditer(
            r'href="([^"]+index_of[^"]+\.html)"', html
        ):
            href = match.group(1)
            full_url = urljoin(index_url, href)
            # 언어 경로 치환 (ko → 요청된 lang)
            full_url = re.sub(r'/ko/', f'/{lang}/', full_url)
            urls.append(full_url)

        return urls

    async def _discover_pages_from_component_index(
        self,
        client,
        component_index_url: str,
        lang: str,
        sem: asyncio.Semaphore,
    ) -> tuple:
        """
        컴포넌트 인덱스 페이지에서 가이드 엔트리 링크 추출 후,
        첫 번째 가이드 페이지에서 sidebar nav-link로 전체 페이지 발견.

        컴포넌트 인덱스 구조:
          /ja/tmaxsoft_docs/main/openframe/mvs_components/index_of_base_mvs_7.1.html
            → /ja/openframe_base/7.1_MVS/base-guide/chapter-introduction.html
            → /ja/openframe_base/7.1_MVS/dataset-guide/chapter-introduction.html
            ...
        가이드 페이지에 sidebar(nav-link)가 있음.
        """
        async with sem:
            try:
                resp = await client.get(component_index_url)
                if resp.status_code != 200:
                    return set(), ""
            except Exception:
                return set(), ""

        html = resp.text

        # 가이드 엔트리 링크 추출 (실제 문서 페이지로의 링크)
        guide_entries: Set[str] = set()
        for match in re.finditer(r'href="([^"]+\.html)"', html):
            href = match.group(1)
            if href.startswith("#") or href.startswith("javascript"):
                continue
            full_url = urljoin(component_index_url, href)
            # 같은 도메인 + 실제 컴포넌트 문서 (openframe_* 패턴)
            if (BASE_URL in full_url
                    and "/_/" not in full_url
                    and "/tmaxsoft_docs/" not in full_url
                    and full_url.endswith(".html")):
                guide_entries.add(full_url.split("#")[0])

        if not guide_entries:
            return set(), ""

        # 첫 번째 가이드 엔트리에서 sidebar nav-link 추출 → 전체 페이지 발견
        all_urls: Set[str] = set(guide_entries)
        component = ""

        first_entry = sorted(guide_entries)[0]
        sidebar_urls, component = await self._extract_sidebar_with_component(
            client, first_entry, lang, sem,
        )
        all_urls.update(sidebar_urls)

        return all_urls, component

    async def _extract_sidebar_with_component(
        self,
        client,
        page_url: str,
        lang: str,
        sem: asyncio.Semaphore,
    ) -> tuple:
        """가이드 페이지의 sidebar에서 모든 nav-link URL + data-component 추출"""
        async with sem:
            try:
                resp = await client.get(page_url)
                if resp.status_code != 200:
                    return set(), ""
            except Exception:
                return set(), ""

        html = resp.text
        urls = set()
        for match in re.finditer(r'<a class="nav-link" href="([^"]+)"', html):
            href = match.group(1)
            full_url = urljoin(page_url, href)
            if BASE_URL in full_url:
                urls.add(full_url.split("#")[0])

        comp_match = re.search(r'data-component="([^"]+)"', html)
        component = comp_match.group(1) if comp_match else ""

        return urls, component

    async def _crawl_page(
        self,
        client,
        url: str,
        component: str,
        lang: str,
        sem: asyncio.Semaphore,
    ) -> Optional[WebDocPage]:
        """개별 페이지 크롤링: title, headings, snippet 추출"""
        async with sem:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
            except Exception:
                return None

        html = resp.text
        version = _extract_version_from_url(url)
        guide = _extract_guide_from_url(url)

        # <article> 태그에서 내용 추출 (정규식 기반, bs4 불필요)
        title = ""
        headings = []
        snippet = ""

        # title 추출: <h1 class="page"> 또는 <title>
        h1_match = re.search(r'<h1[^>]*class="page"[^>]*>(.*?)</h1>', html, re.DOTALL)
        if h1_match:
            title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
        else:
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if h1_match:
                title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()
            else:
                title_match = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
                if title_match:
                    title = title_match.group(1).strip().split("|")[0].strip()

        # h2/h3 headings 추출
        for h_match in re.finditer(r'<h[23][^>]*>(.*?)</h[23]>', html, re.DOTALL):
            h_text = re.sub(r'<[^>]+>', '', h_match.group(1)).strip()
            if h_text and len(h_text) < 200:
                headings.append(h_text)

        # article 본문 snippet
        article_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
        if article_match:
            article_text = re.sub(r'<[^>]+>', ' ', article_match.group(1))
            article_text = re.sub(r'\s+', ' ', article_text).strip()
            snippet = article_text[:300]

        # data-component가 있으면 더 정확한 컴포넌트명 사용
        dc_match = re.search(r'data-component="([^"]+)"', html)
        if dc_match:
            component = dc_match.group(1)

        product_id = _get_product_id(component)

        # 검색 키워드 생성 (title + headings에서 의미 토큰 추출)
        keywords = _extract_keywords(title, headings, snippet)

        return WebDocPage(
            url=url,
            component=component,
            version=version,
            guide=guide,
            title=title,
            headings=headings[:20],
            snippet=snippet,
            language=lang,
            product_id=product_id,
            keywords=keywords,
        )


def _extract_keywords(title: str, headings: List[str], snippet: str) -> List[str]:
    """title + headings + snippet에서 검색 키워드 추출"""
    text = (title + " " + " ".join(headings) + " " + snippet).lower()
    # 영문+숫자, 카타카나, 한자, 한국어
    tokens = re.findall(
        r'[a-z0-9][a-z0-9_\-]*[a-z0-9]|[a-z0-9]'
        r'|[\u30a0-\u30ff]{2,}'
        r'|[\u4e00-\u9fff]+'
        r'|[\uac00-\ud7af]{2,}'
        r'|[\u3040-\u309f]{2,}',
        text,
    )
    # 유니크 + 1자 영문 제거
    seen = set()
    result = []
    for t in tokens:
        if t not in seen and not (len(t) == 1 and t.isascii()):
            seen.add(t)
            result.append(t)
    return result[:50]  # 최대 50 키워드


# Singleton
_instance: Optional[WebDocCrawlerService] = None


def get_web_doc_crawler_service() -> WebDocCrawlerService:
    global _instance
    if _instance is None:
        _instance = WebDocCrawlerService()
    return _instance
