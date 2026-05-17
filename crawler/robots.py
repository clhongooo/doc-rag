import re
from urllib.parse import urlparse, urljoin

import httpx


class RobotsChecker:
    def __init__(self, user_agent: str = "*", timeout: int = 10):
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache: dict[str, dict] = {}

    async def _fetch_robots(self, base_url: str) -> dict:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        if robots_url in self._cache:
            return self._cache[robots_url]

        result = {"disallow": [], "crawl_delay": None}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(robots_url, follow_redirects=True)
                if resp.status_code != 200:
                    self._cache[robots_url] = result
                    return result

                text = resp.text
        except Exception:
            self._cache[robots_url] = result
            return result

        current_agent = None
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if ':' not in line:
                continue

            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()

            if key == 'user-agent':
                current_agent = value
            elif key == 'disallow' and current_agent in (self.user_agent, '*'):
                if value:
                    result["disallow"].append(value)
            elif key == 'crawl-delay' and current_agent in (self.user_agent, '*'):
                try:
                    result["crawl_delay"] = float(value)
                except ValueError:
                    pass

        self._cache[robots_url] = result
        return result

    def is_allowed(self, url: str, robots_data: dict) -> bool:
        parsed = urlparse(url)
        path = parsed.path

        for pattern in robots_data.get("disallow", []):
            if pattern and path.startswith(pattern):
                return False

        return True

    def get_crawl_delay(self, robots_data: dict) -> float:
        delay = robots_data.get("crawl_delay")
        return delay if delay is not None else 0.0

    async def check(self, url: str) -> tuple[bool, float]:
        """Returns (is_allowed, crawl_delay)"""
        robots_data = await self._fetch_robots(url)

        if not self.is_allowed(url, robots_data):
            return False, 0.0

        return True, self.get_crawl_delay(robots_data)
