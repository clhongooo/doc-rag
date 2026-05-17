"""自动选择合适的爬虫：先用 HTTP 探测，SPA 站自动切换 Playwright"""
import re
import httpx

from .base import BaseCrawler, CrawlConfig, CrawlResult
from .http_crawler import HTTPCrawler
from .playwright import PlaywrightCrawler


# SPA 框架特征
SPA_SIGNALS = [
    r"data-react-helmet",
    r"data-reactroot",
    r"data-v-[a-f0-9]+",
    r"data-vue-",
    r"__NEXT_DATA__",
    r"__NUXT__",
    r"window\.__staticRouterHydrationData",
    r"ng-app",
    r"ember-view",
]


class CrawlerRouter(BaseCrawler):
    """根据页面特征自动选择 HTTPCrawler 或 PlaywrightCrawler"""

    def __init__(self):
        self.http = HTTPCrawler()
        self.playwright = PlaywrightCrawler()

    async def crawl(self, url: str, config: CrawlConfig) -> list[CrawlResult]:
        if await self._is_spa(url, config):
            print(f"[Router] 检测到 SPA 站点，使用 PlaywrightCrawler")
            return await self.playwright.crawl(url, config)
        else:
            print(f"[Router] 静态站点，使用 HTTPCrawler")
            return await self.http.crawl(url, config)

    async def _is_spa(self, url: str, config: CrawlConfig) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=min(config.timeout, 15),
                headers={"User-Agent": config.user_agent},
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                html = resp.text

            for pattern in SPA_SIGNALS:
                if re.search(pattern, html):
                    return True

            return False
        except Exception:
            # 探测失败，保守用 Playwright
            return True
