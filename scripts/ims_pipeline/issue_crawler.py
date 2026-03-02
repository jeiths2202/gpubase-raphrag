"""
Phase 2: IMS 이슈 페이지 크롤 → .txt 저장
RequestsBasedCrawler의 HTTP 패턴을 재사용하되 CLI에서 직접 실행.
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .config import (
    CRAWL_TIMEOUT,
    DEFAULT_CONCURRENCY,
    DEFAULT_CREDENTIALS,
    IMS_BASE_URL,
    IMS_ISSUE_VIEW_PATH,
    IMS_LOGIN_PATH,
    OUTPUT_DIR,
    REQUEST_DELAY,
)

logger = logging.getLogger(__name__)


# ── HTML 파싱 (RequestsBasedCrawler 패턴 재사용) ──────────────────


def _get_table_field(html: str, soup: BeautifulSoup, label: str) -> str:
    """IMS HTML 테이블에서 라벨에 해당하는 값 추출."""
    # tableHeaderTitle 패턴
    pattern = rf'<td[^>]*class=["\']tableHeaderTitle["\'][^>]*>\s*{label}\s*</td>\s*<td[^>]*>(.*?)</td>'
    match = re.search(pattern, html, re.DOTALL | re.I)
    if match:
        return re.sub(r'<[^>]+>', '', match.group(1)).replace('&nbsp;', ' ').strip()

    # th/td 패턴
    pattern2 = rf'<th[^>]*>\s*{label}\s*</th>\s*<td[^>]*>(.*?)</td>'
    match2 = re.search(pattern2, html, re.DOTALL | re.I)
    if match2:
        return re.sub(r'<[^>]+>', '', match2.group(1)).replace('&nbsp;', ' ').strip()

    # BeautifulSoup fallback
    for td in soup.find_all('td', class_='tableHeaderTitle'):
        if label.lower() in td.get_text(strip=True).lower():
            next_td = td.find_next_sibling('td')
            if next_td:
                return next_td.get_text(strip=True).replace('\xa0', ' ')

    return ''


def _clean_html(raw: str) -> str:
    """HTML 태그 제거 + 엔티티 디코딩."""
    text = re.sub(r'<[^>]+>', ' ', raw)
    for old, new in [
        ('&nbsp;', ' '), ('&#39;', "'"), ('&lt;', '<'),
        ('&gt;', '>'), ('&#64;', '@'), ('&amp;', '&'),
    ]:
        text = text.replace(old, new)
    return re.sub(r'\s+', ' ', text).strip()


def _parse_issue_html(html: str, issue_id: str) -> dict:
    """
    IMS 이슈 상세 HTML 파싱 → description + action_log 딕셔너리.
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Subject
    subject = ''
    subj_td = soup.find('td', class_='tableHeaderTitle', string=re.compile(r'Subject', re.I))
    if subj_td:
        val = subj_td.find_next_sibling('td')
        if val:
            subject = val.get_text(strip=True).replace('\xa0', ' ')
    if not subject:
        subject = _get_table_field(html, soup, 'Subject')

    # Issue Details (description)
    description = ''
    desc_match = re.search(
        r'id=["\']IssueDescriptionDiv["\'][^>]*>(.*?)</div>\s*<!--',
        html, re.DOTALL | re.I,
    )
    if desc_match:
        description = _clean_html(desc_match.group(1))

    # Action Log
    action_texts: list[str] = []
    for match in re.findall(
        r'<div[^>]*class=["\'][^"\']*commDescTR[^"\']*["\'][^>]*>(.*?)</div>',
        html, re.DOTALL | re.I,
    ):
        text = _clean_html(match)
        if text and len(text) > 5:
            action_texts.append(text)

    if not action_texts:
        comments_match = re.search(
            r'<div[^>]*id=["\']CommentsDiv["\'][^>]*>(.*?)</div>\s*(?:</div>|<table)',
            html, re.DOTALL | re.I,
        )
        if comments_match:
            text = _clean_html(comments_match.group(1))
            if text and len(text) > 10:
                action_texts.append(text)

    action_log = '\n---\n'.join(action_texts)[:10000]

    # 추가 메타데이터
    product = _get_table_field(html, soup, 'Product')
    version = _get_table_field(html, soup, 'Version')
    module = _get_table_field(html, soup, 'Module')
    status = _get_table_field(html, soup, 'Status')
    category = _get_table_field(html, soup, 'Category') or _get_table_field(html, soup, 'Type')

    return {
        'subject': subject,
        'description': description[:5000],
        'action_log': action_log,
        'product': product,
        'version': version,
        'module': module,
        'status': status,
        'category': category,
    }


# ── 구조화 텍스트 변환 ────────────────────────────────────────────


def issue_to_text(meta: dict, crawled: dict) -> str:
    """이슈 메타 + 크롤 결과 → 검색 가능한 구조화 텍스트."""
    ims_id = meta.get('ims_id', '')
    product = crawled.get('product') or meta.get('product', '')
    version = crawled.get('version') or meta.get('version', '')
    module = crawled.get('module') or meta.get('module', '')
    category = crawled.get('category') or meta.get('category', '')
    subject = crawled.get('subject') or meta.get('subject', '')
    status = crawled.get('status') or meta.get('status', '')
    customer = meta.get('customer', '')
    issued_date = meta.get('issued_date', '')
    description = crawled.get('description', '')
    action_log = crawled.get('action_log', '')

    lines = [
        f"=== IMS Issue {ims_id} ===",
        f"Product: {product}",
        f"Version: {version}",
        f"Module: {module}",
        f"Category: {category}",
        f"Subject: {subject}",
        f"Customer: {customer}",
        f"Status: {status}",
        f"Date: {issued_date}",
    ]

    if description:
        lines.append('')
        lines.append('## 상세 내용')
        lines.append(description)

    if action_log:
        lines.append('')
        lines.append('## 조치 이력')
        lines.append(action_log)

    return '\n'.join(lines)


# ── 인증 + 크롤 ──────────────────────────────────────────────────


class IMSCrawlerSession:
    """CLI용 간단한 IMS 크롤러 세션. 평문 자격증명 직접 사용."""

    def __init__(self, base_url: str = IMS_BASE_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,ja;q=0.6',
        })
        self._authenticated = False

    def authenticate(self, username: str, password: str) -> bool:
        """IMS 로그인 (JSESSIONID 획득)."""
        login_url = f"{self.base_url}{IMS_LOGIN_PATH}"
        self.session.get(login_url, timeout=30)  # 쿠키 초기화
        resp = self.session.post(
            login_url,
            data={'id': username, 'password': password},
            allow_redirects=True,
            timeout=30,
        )
        if '/login' in resp.url or '/auth/login' in resp.url:
            logger.error("Authentication failed - redirected to login")
            return False

        jsid = self.session.cookies.get('JSESSIONID', '')[:20]
        logger.info(f"Authenticated (JSESSIONID={jsid}...)")
        self._authenticated = True
        return True

    def fetch_issue(self, ims_id: str) -> dict:
        """단일 이슈 상세 HTML 크롤 → 파싱 결과 딕셔너리."""
        if not self._authenticated:
            raise RuntimeError("Not authenticated. Call authenticate() first.")

        url = f"{self.base_url}{IMS_ISSUE_VIEW_PATH}"
        resp = self.session.post(
            url,
            data={'issueId': ims_id, 'menuCode': 'issue_search'},
            headers={'Referer': f"{self.base_url}/tody/ims/issue/issueSearchList.do"},
            timeout=CRAWL_TIMEOUT,
        )
        resp.raise_for_status()
        return _parse_issue_html(resp.text, ims_id)


# ── 배치 크롤 ─────────────────────────────────────────────────────


async def crawl_issues(
    index_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    credentials_path: Optional[Path] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    force: bool = False,
    limit: Optional[int] = None,
) -> dict:
    """
    이슈 상세 페이지 크롤 → .txt 저장.

    Returns:
        stats dict: {total, crawled, skipped, failed}
    """
    output_dir = output_dir or OUTPUT_DIR
    index_path = index_path or (output_dir / "index.json")
    credentials_path = credentials_path or DEFAULT_CREDENTIALS

    if not index_path.exists():
        raise FileNotFoundError(f"index.json not found: {index_path}")
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {credentials_path}\n"
            f"Create it with: {{\"username\": \"...\", \"password\": \"...\"}}"
        )

    # 인덱스 로드
    issues = json.loads(index_path.read_text(encoding="utf-8"))
    if limit:
        issues = issues[:limit]
    logger.info(f"Loaded {len(issues)} issues from index")

    # 자격증명 로드
    creds = json.loads(credentials_path.read_text(encoding="utf-8"))
    username = creds["username"]
    password = creds["password"]

    # 이미 크롤된 파일 건너뛰기
    if not force:
        to_crawl = []
        skipped = 0
        for meta in issues:
            txt_path = output_dir / f"{meta['ims_id']}.txt"
            if txt_path.exists() and txt_path.stat().st_size > 0:
                skipped += 1
            else:
                to_crawl.append(meta)
        logger.info(f"Skipping {skipped} already crawled, {len(to_crawl)} to crawl")
    else:
        to_crawl = issues
        skipped = 0

    if not to_crawl:
        logger.info("Nothing to crawl.")
        return {"total": len(issues), "crawled": 0, "skipped": skipped, "failed": 0}

    # 인증
    crawler = IMSCrawlerSession()
    success = await asyncio.to_thread(crawler.authenticate, username, password)
    if not success:
        raise RuntimeError("IMS authentication failed")

    # 순차 크롤 (서버 부하 방지 + 세마포어 대신 delay)
    sem = asyncio.Semaphore(concurrency)
    stats = {"total": len(issues), "crawled": 0, "skipped": skipped, "failed": 0}

    async def _crawl_one(meta: dict) -> None:
        async with sem:
            ims_id = meta["ims_id"]
            txt_path = output_dir / f"{ims_id}.txt"
            try:
                crawled = await asyncio.to_thread(crawler.fetch_issue, ims_id)
                text = issue_to_text(meta, crawled)
                txt_path.write_text(text, encoding="utf-8")
                stats["crawled"] += 1
                logger.info(f"[{stats['crawled']}/{len(to_crawl)}] {ims_id}: {meta.get('subject', '')[:40]}")
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"Failed {ims_id}: {e}")

            # polite delay
            await asyncio.sleep(REQUEST_DELAY)

    tasks = [_crawl_one(m) for m in to_crawl]
    await asyncio.gather(*tasks)

    logger.info(
        f"Crawl complete: {stats['crawled']} crawled, "
        f"{stats['skipped']} skipped, {stats['failed']} failed"
    )
    return stats


def run(
    credentials: Optional[str] = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    force: bool = False,
    limit: Optional[int] = None,
) -> dict:
    """CLI 진입점 (동기 래퍼)."""
    return asyncio.run(crawl_issues(
        credentials_path=Path(credentials) if credentials else None,
        concurrency=concurrency,
        force=force,
        limit=limit,
    ))
