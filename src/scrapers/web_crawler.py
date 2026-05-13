import asyncio
import re
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

import config.settings as settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Pages that are more likely to contain owner/contact info — crawled first
_PRIORITY_PATHS = {"/about", "/about-us", "/team", "/contact", "/contact-us", "/our-team", "/who-we-are"}

# Social media and directory sites that block crawlers or won't contain owner info
_BLOCKED_DOMAINS = {
    "facebook.com", "m.facebook.com",
    "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com",
    "yelp.com", "yellowpages.com", "bbb.org",
    "google.com", "maps.google.com",
}


def is_social_or_directory_url(url: str) -> bool:
    """Return True if the URL points to a social media or directory site, not a real business website."""
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
        return any(domain == blocked or domain.endswith("." + blocked) for blocked in _BLOCKED_DOMAINS)
    except Exception:
        return False


async def crawl_domain(start_url: str) -> str:
    """
    Crawls start_url and same-domain links up to CRAWL_MAX_DEPTH.
    Returns concatenated visible text from all crawled pages (truncated to ~50k chars).
    """
    base = _normalize_url(start_url)
    if not base:
        return ""

    domain = urlparse(base).netloc
    if domain in _BLOCKED_DOMAINS:
        logger.info(f"Skipping blocked domain: {domain}")
        return ""

    visited: Set[str] = set()
    queue: List[tuple[str, int]] = []

    queue.append((base, 0))
    for path in _PRIORITY_PATHS:
        queue.append((urljoin(base, path), 1))

    page_texts: Dict[str, str] = {}

    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=httpx.Timeout(connect=8.0, read=settings.REQUEST_TIMEOUT_SECONDS),
        follow_redirects=True,
    ) as client:
        while queue and len(page_texts) < settings.CRAWL_MAX_PAGES:
            url, depth = queue.pop(0)
            url = _normalize_url(url)
            if not url or url in visited:
                continue
            if urlparse(url).netloc != domain:
                continue

            visited.add(url)
            logger.debug(f"Crawling [{depth}] {url}")

            html, ok = await _fetch(client, url)
            if not ok:
                continue

            text = _extract_text(html)
            if text:
                page_texts[url] = text

            if depth < settings.CRAWL_MAX_DEPTH:
                links = _extract_same_domain_links(html, url, domain)
                for link in links:
                    if link not in visited and len(queue) < 200:
                        queue.append((link, depth + 1))

            await asyncio.sleep(settings.CRAWL_DELAY_SECONDS)

    combined = "\n\n---\n\n".join(
        f"[PAGE: {url}]\n{text}" for url, text in page_texts.items()
    )
    logger.info(f"Crawled {len(page_texts)} pages from {domain} ({len(combined)} chars)")

    return combined[:50_000]


async def _fetch(client: httpx.AsyncClient, url: str) -> tuple[str, bool]:
    try:
        resp = await client.get(url)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            if "html" in content_type:
                return resp.text, True
        logger.debug(f"Skipped {url} (status={resp.status_code})")
        return "", False
    except httpx.RequestError as exc:
        logger.debug(f"Fetch error {url}: {exc}")
        return "", False


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _extract_same_domain_links(html: str, base_url: str, domain: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc == domain and parsed.scheme in ("http", "https"):
            links.append(_normalize_url(full))
    return links


def _normalize_url(url: str) -> str:
    try:
        p = urlparse(url)
        normalized = urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", p.params, p.query, ""))
        return normalized
    except Exception:
        return ""
