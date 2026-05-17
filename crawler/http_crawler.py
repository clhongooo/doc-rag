import asyncio
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .base import BaseCrawler, CrawlConfig, CrawlResult
from .cache import CrawlCache
from .robots import RobotsChecker
from .sitemap import SitemapParser


class HTTPCrawler(BaseCrawler):
    def __init__(self):
        self.sitemap_parser = SitemapParser()
        self._failed_urls: list[dict] = []
        self._domain_semaphores: dict[str, asyncio.Semaphore] = {}
        self._robots_checker: Optional[RobotsChecker] = None

    @property
    def failed_urls(self) -> list[dict]:
        return list(self._failed_urls)

    def _get_domain_semaphore(self, domain: str, max_concurrent: int) -> asyncio.Semaphore:
        if domain not in self._domain_semaphores:
            self._domain_semaphores[domain] = asyncio.Semaphore(max_concurrent)
        return self._domain_semaphores[domain]

    async def crawl(self, url: str, config: CrawlConfig) -> list[CrawlResult]:
        self._failed_urls.clear()
        self._domain_semaphores.clear()

        cache = CrawlCache(config.cache_dir, ttl_seconds=config.cache_ttl) if config.cache_enabled else None

        # robots.txt 检查
        robots_delay = 0.0
        if config.respect_robots:
            self._robots_checker = RobotsChecker(user_agent=config.user_agent)
            allowed, robots_delay = await self._robots_checker.check(url)
            if not allowed:
                print(f"[HTTPCrawler] robots.txt 禁止爬取: {url}")
                return []
            if robots_delay > 0:
                print(f"[HTTPCrawler] robots.txt crawl-delay: {robots_delay}s")
        else:
            self._robots_checker = None

        urls = await self._discover_urls(url, config)
        urls = self._filter_urls(urls, config.url_patterns)

        # 按 robots.txt 过滤
        if self._robots_checker and config.respect_robots:
            robots_data = await self._robots_checker._fetch_robots(url)
            urls = [u for u in urls if self._robots_checker.is_allowed(u, robots_data)]
            effective_delay = max(config.delay_between_requests, robots_delay)
        else:
            effective_delay = config.delay_between_requests

        results = []
        async with httpx.AsyncClient(
            timeout=config.timeout,
            headers={"User-Agent": config.user_agent},
            follow_redirects=True,
        ) as client:
            tasks = [
                self._fetch_with_limit(client, u, config, cache, effective_delay)
                for u in urls
            ]
            results = await asyncio.gather(*tasks)

        valid_results = [r for r in results if r is not None]
        if self._failed_urls:
            print(f"[HTTPCrawler] {len(self._failed_urls)} 个页面抓取失败:")
            for item in self._failed_urls[:10]:
                print(f"  - {item['url']}: {item['error']}")
            if len(self._failed_urls) > 10:
                print(f"  ... 还有 {len(self._failed_urls) - 10} 个")

        return valid_results

    async def _discover_urls(self, url: str, config: CrawlConfig) -> list[str]:
        urls = await self.sitemap_parser.discover(url)
        if urls:
            return urls

        return await self._crawl_links(url, config.max_depth)

    async def _crawl_links(self, url: str, max_depth: int) -> list[str]:
        if max_depth <= 0:
            return [url]

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError:
                return [url]

        soup = BeautifulSoup(resp.text, "html.parser")
        base_domain = urlparse(url).netloc

        links = {url}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(url, href)

            if urlparse(full_url).netloc == base_domain:
                links.add(full_url)

        return list(links)

    def _filter_urls(self, urls: list[str], patterns: list[str]) -> list[str]:
        if not patterns:
            return urls

        compiled = [re.compile(p) for p in patterns]
        return [u for u in urls if any(p.search(u) for p in compiled)]

    def _detect_encoding(self, content_type: str, raw_html: bytes) -> str:
        # 1. HTTP Content-Type header
        if content_type:
            match = re.search(r'charset=([^\s;]+)', content_type, re.IGNORECASE)
            if match:
                return match.group(1).strip('"\'')

        # 2. HTML meta charset
        head = raw_html[:4096].decode('ascii', errors='ignore')
        match = re.search(r'<meta[^>]+charset=["\']?([^"\'\s;>]+)', head, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # 3. XML declaration
        match = re.search(r'<\?xml[^>]+encoding=["\']([^"\']+)["\']', head, re.IGNORECASE)
        if match:
            return match.group(1)

        # 4. chardet fallback
        try:
            import chardet
            detected = chardet.detect(raw_html)
            if detected and detected['confidence'] and detected['confidence'] > 0.5:
                return detected['encoding']
        except ImportError:
            pass

        return 'utf-8'

    async def _fetch_with_limit(
        self,
        client: httpx.AsyncClient,
        url: str,
        config: CrawlConfig,
        cache: Optional[CrawlCache],
        delay: float = 0.5,
    ) -> Optional[CrawlResult]:
        if cache and cache.has(url):
            data = cache.get(url)
            return CrawlResult(**data)

        domain = urlparse(url).netloc
        semaphore = self._get_domain_semaphore(domain, config.max_concurrent)

        last_error = None
        for attempt in range(config.max_retries):
            async with semaphore:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()

                    raw = resp.content
                    encoding = self._detect_encoding(
                        resp.headers.get('content-type', ''), raw
                    )
                    html = raw.decode(encoding, errors='replace')

                    soup = BeautifulSoup(html, "html.parser")
                    title = soup.title.string if soup.title else url

                    result = CrawlResult(
                        url=url,
                        title=title.strip() if title else url,
                        html=html,
                    )

                    if cache:
                        cache.set(url, {
                            "url": result.url,
                            "title": result.title,
                            "html": result.html,
                            "metadata": result.metadata,
                        })

                    await asyncio.sleep(delay)
                    return result

                except httpx.HTTPStatusError as e:
                    last_error = str(e)
                    # 4xx 不重试
                    if 400 <= e.response.status_code < 500:
                        break
                    # 5xx 可恢复，继续重试
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                    last_error = str(e)
                except Exception as e:
                    last_error = str(e)
                    break

            # 指数退避
            if attempt < config.max_retries - 1:
                wait = 2 ** attempt
                await asyncio.sleep(wait)

        self._failed_urls.append({"url": url, "error": last_error or "unknown"})
        return None
