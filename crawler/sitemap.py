import httpx
from bs4 import BeautifulSoup


class SitemapParser:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    async def parse(self, sitemap_url: str) -> list[str]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(sitemap_url)
                resp.raise_for_status()
            except httpx.HTTPError:
                return []

        soup = BeautifulSoup(resp.text, "lxml-xml")

        urls = []
        for loc in soup.find_all("loc"):
            urls.append(loc.text.strip())

        for sitemap in soup.find_all("sitemap"):
            loc = sitemap.find("loc")
            if loc:
                nested_urls = await self.parse(loc.text.strip())
                urls.extend(nested_urls)

        return urls

    async def discover(self, base_url: str) -> list[str]:
        common_paths = [
            "/sitemap.xml",
            "/sitemap_index.xml",
            "/sitemap/0.xml",
        ]

        for path in common_paths:
            url = base_url.rstrip("/") + path
            urls = await self.parse(url)
            if urls:
                return urls

        return []
