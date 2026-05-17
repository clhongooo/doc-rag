import asyncio
import re
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Browser

from .base import BaseCrawler, CrawlConfig, CrawlResult
from .cache import CrawlCache


class PlaywrightCrawler(BaseCrawler):
    def __init__(self):
        self.browser: Optional[Browser] = None

    async def crawl(self, url: str, config: CrawlConfig) -> list[CrawlResult]:
        cache = CrawlCache(config.cache_dir, ttl_seconds=config.cache_ttl) if config.cache_enabled else None

        async with async_playwright() as p:
            self.browser = await p.chromium.launch(headless=True)
            page = await self.browser.new_page()

            all_urls = await self._discover_all_urls(page, url, config)
            print(f"发现 {len(all_urls)} 个文档页面")

            results = []
            for i, doc_url in enumerate(all_urls):
                if cache and cache.has(doc_url):
                    data = cache.get(doc_url)
                    results.append(CrawlResult(**data))
                    print(f"[{i+1}/{len(all_urls)}] 缓存: {doc_url}")
                    continue

                try:
                    result = await self._fetch_page(page, doc_url, config)
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
                except Exception as e:
                    print(f"[{i+1}/{len(all_urls)}] 失败: {doc_url} - {e}")

                await asyncio.sleep(config.delay_between_requests)

            await self.browser.close()
            self.browser = None

        return results

    async def _discover_all_urls(self, page: Page, start_url: str, config: CrawlConfig) -> list[str]:
        await page.goto(start_url, wait_until="domcontentloaded", timeout=config.timeout * 1000)
        await asyncio.sleep(3)

        await self._expand_all_sections(page)

        parsed = urlparse(start_url)
        base_domain = parsed.netloc
        # 提取路径前缀：如 /docs/api/ → /docs/
        path_parts = parsed.path.rstrip('/').split('/')
        if len(path_parts) > 1:
            path_prefix = '/'.join(path_parts[:2]) + '/'
        else:
            path_prefix = '/'

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
        expand_selectors = [
            '.tree-toggle',
            '.expand-btn',
            '.arrow-icon',
            '[data-toggle="collapse"]',
            '.parent-node',
            '[class*="expand"]',
            '[class*="toggle"]',
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
                        except:
                            pass
                except:
                    pass
            if not expanded:
                break
            await asyncio.sleep(0.5)

    async def _fetch_page(self, page: Page, url: str, config: CrawlConfig) -> Optional[CrawlResult]:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=config.timeout * 1000)

            # 等待正文内容加载
            try:
                await page.wait_for_selector(
                    '.doc-content, .doc-article-content, .markdown-body, article, '
                    '#content, .content, .page-content, .post-content, .entry-content, '
                    '.article-body, [role="main"], main',
                    timeout=10000,
                )
            except:
                await asyncio.sleep(3)

            title = await page.title()

            # 通用正文提取：尝试多种常见框架的选择器
            content_html = await page.evaluate("""
                () => {
                    const selectors = [
                        // 常见文档框架
                        '.doc-article-content', '.doc-content', '.markdown-body',
                        '.J-markdown-box',
                        // 通用内容容器
                        'article', '#content', '.content', '.page-content',
                        'main', '[role="main"]',
                        // 博客/文章框架
                        '.post-content', '.entry-content', '.article-body',
                        '.post-body', '.single-content',
                        // 通用 class 匹配
                        '.doc-body', '.docs-article', '.docs-content',
                        '.documentation-content', '.api-content',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText && el.innerText.trim().length > 50) {
                            return el.innerHTML;
                        }
                    }
                    return '';
                }
            """)

            # fallback: 尝试 main > body
            if not content_html or len(content_html) < 100:
                content_html = await page.evaluate("""
                    () => {
                        const main = document.querySelector('main') || document.body;
                        return main.innerHTML;
                    }
                """)

            return CrawlResult(
                url=url,
                title=title or url,
                html=content_html,
            )

        except Exception as e:
            print(f"抓取失败 {url}: {e}")
            return None
