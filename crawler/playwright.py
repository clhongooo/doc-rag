"""Playwright 爬虫 — 支持 SPA 渲染、URL 列表、浏览器复用"""
import asyncio
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Browser

from .base import BaseCrawler, CrawlConfig, CrawlResult
from .cache import CrawlCache


class PlaywrightCrawler(BaseCrawler):
    """通过 Playwright 渲染 SPA 页面，提取真实内容"""

    # 常见内容容器选择器（按优先级排列）
    DEFAULT_CONTENT_SELECTORS = [
        # 文档框架
        ".doc-article-content", ".doc-content", ".J-markdown-box",
        ".markdown-body", ".rst-content", ".md-content",
        # 通用
        "article", "main", '[role="main"]',
        "#content", ".content", ".page-content",
        # 博客 / 文章
        ".post-content", ".entry-content", ".article-body",
        ".post-body", ".single-content",
        # API 文档
        ".api-content", ".docs-content", ".documentation-content",
    ]

    def __init__(self):
        self.browser: Optional[Browser] = None
        self._playwright = None

    async def start(self):
        """启动浏览器（可复用）"""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=True)

    async def stop(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def crawl(self, url: str, config: CrawlConfig) -> list[CrawlResult]:
        cache = CrawlCache(config.cache_dir, ttl_seconds=config.cache_ttl) if config.cache_enabled else None

        # 确定 URL 列表：优先用传入的 urls，否则自动发现
        if config.urls:
            all_urls = config.urls
            print(f"[Playwright] 使用传入的 {len(all_urls)} 个 URL")
        else:
            # 自动发现（需要启动浏览器）
            if not self.browser:
                await self.start()
            page = await self.browser.new_page()
            try:
                all_urls = await self._discover_urls(page, url, config)
                print(f"[Playwright] 发现 {len(all_urls)} 个文档页面")
            finally:
                await page.close()

        # 逐页爬取
        results = []
        need_browser = not self.browser
        if need_browser:
            await self.start()

        try:
            for i, doc_url in enumerate(all_urls):
                # 缓存命中
                if cache and cache.has(doc_url):
                    data = cache.get(doc_url)
                    results.append(CrawlResult(**data))
                    print(f"[{i+1}/{len(all_urls)}] 缓存: {doc_url}")
                    continue

                try:
                    result = await self._fetch_page(doc_url, config)
                    if result:
                        results.append(result)
                        if cache:
                            cache.set(doc_url, {
                                "url": result.url,
                                "title": result.title,
                                "html": result.html,
                                "metadata": result.metadata,
                            })
                        print(f"[{i+1}/{len(all_urls)}] 完成: {result.title[:40]}")
                    else:
                        print(f"[{i+1}/{len(all_urls)}] 空内容: {doc_url}")
                except Exception as e:
                    print(f"[{i+1}/{len(all_urls)}] 失败: {doc_url} - {e}")

                await asyncio.sleep(config.delay_between_requests)
        finally:
            if need_browser:
                await self.stop()

        return results

    async def fetch_single(self, url: str, config: CrawlConfig) -> Optional[CrawlResult]:
        """爬取单个页面（供外部调用，如 HTTP 降级）"""
        need_browser = not self.browser
        if need_browser:
            await self.start()
        try:
            return await self._fetch_page(url, config)
        finally:
            if need_browser:
                await self.stop()

    async def _discover_urls(self, page: Page, start_url: str, config: CrawlConfig) -> list[str]:
        """从起始 URL 发现子页面"""
        await page.goto(start_url, wait_until="domcontentloaded", timeout=config.timeout * 1000)
        await asyncio.sleep(3)

        # 尝试展开侧边栏（失败则跳过，不影响后续）
        try:
            await self._expand_all_sections(page)
        except Exception as e:
            print(f"[Playwright] 侧边栏展开失败（跳过）: {e}")

        parsed = urlparse(start_url)
        base_domain = parsed.netloc
        path_parts = parsed.path.rstrip("/").split("/")
        path_prefix = "/".join(path_parts[:2]) + "/" if len(path_parts) > 1 else "/"

        all_urls = await page.evaluate("""
            (args) => {
                const { baseDomain, pathPrefix } = args;
                const urls = new Set();
                document.querySelectorAll('a[href]').forEach(a => {
                    try {
                        const url = new URL(a.href, window.location.origin);
                        if (url.hostname === baseDomain && url.pathname.startsWith(pathPrefix)) {
                            urls.add(url.href.split('#')[0]);
                        }
                    } catch(e) {}
                });
                return Array.from(urls);
            }
        """, {"baseDomain": base_domain, "pathPrefix": path_prefix})

        return sorted(set(all_urls))

    async def _expand_all_sections(self, page: Page) -> None:
        """展开侧边栏所有折叠节点（可选，失败不影响主流程）"""
        expand_selectors = [
            '.tree-toggle', '.expand-btn', '.arrow-icon',
            '[data-toggle="collapse"]', '.parent-node',
            '[class*="expand"]', '[class*="toggle"]',
        ]

        for _ in range(3):
            expanded = False
            for selector in expand_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for el in elements:
                        try:
                            if await el.is_visible():
                                await el.click()
                                expanded = True
                                await asyncio.sleep(0.2)
                        except Exception:
                            pass
                except Exception:
                    pass
            if not expanded:
                break
            await asyncio.sleep(0.5)

    async def _fetch_page(self, url: str, config: CrawlConfig) -> Optional[CrawlResult]:
        """渲染单个页面并提取内容"""
        try:
            page = await self.browser.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=config.timeout * 1000)

                # 等待正文加载
                selectors_to_try = config.content_selector.split(",") if config.content_selector else self.DEFAULT_CONTENT_SELECTORS
                try:
                    await page.wait_for_selector(
                        ", ".join(selectors_to_try[:5]),  # 取前5个尝试
                        timeout=10000,
                    )
                except Exception:
                    await asyncio.sleep(3)

                title = await page.title()

                # 按优先级尝试选择器提取内容
                content_html = await page.evaluate("""
                    (selectors) => {
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el && el.innerText && el.innerText.trim().length > 50) {
                                return el.innerHTML;
                            }
                        }
                        return '';
                    }
                """, selectors_to_try)

                # fallback: main 或 body
                if not content_html or len(content_html) < 100:
                    content_html = await page.evaluate("""
                        () => {
                            const main = document.querySelector('main') || document.body;
                            return main ? main.innerHTML : '';
                        }
                    """)

                return CrawlResult(
                    url=url,
                    title=title or url,
                    html=content_html,
                )
            finally:
                await page.close()

        except Exception as e:
            print(f"[Playwright] 抓取失败 {url}: {e}")
            return None
