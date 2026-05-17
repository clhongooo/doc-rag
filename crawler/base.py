from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CrawlConfig:
    max_depth: int = 3
    max_concurrent: int = 5
    delay_between_requests: float = 1.0
    user_agent: str = "DocRag/0.1 (compatible; bot)"
    timeout: int = 30
    cache_enabled: bool = True
    cache_dir: str = ".cache"
    cache_ttl: int = 86400
    url_patterns: list[str] = field(default_factory=list)
    max_retries: int = 3
    respect_robots: bool = True


@dataclass
class CrawlResult:
    url: str
    title: str
    html: str
    metadata: dict = field(default_factory=dict)


class BaseCrawler(ABC):
    @abstractmethod
    async def crawl(self, url: str, config: CrawlConfig) -> list[CrawlResult]:
        ...
