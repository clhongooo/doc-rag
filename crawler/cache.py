import hashlib
import json
import time
from pathlib import Path
from typing import Optional


class CrawlCache:
    def __init__(self, cache_dir: str = ".cache", ttl_seconds: int = 86400):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _key(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _is_expired(self, cache_file: Path) -> bool:
        if self.ttl_seconds <= 0:
            return False
        mtime = cache_file.stat().st_mtime
        return (time.time() - mtime) > self.ttl_seconds

    def get(self, url: str) -> Optional[dict]:
        cache_file = self.cache_dir / f"{self._key(url)}.json"
        if cache_file.exists() and not self._is_expired(cache_file):
            return json.loads(cache_file.read_text())
        return None

    def set(self, url: str, data: dict) -> None:
        cache_file = self.cache_dir / f"{self._key(url)}.json"
        cache_file.write_text(json.dumps(data, ensure_ascii=False))

    def has(self, url: str) -> bool:
        cache_file = self.cache_dir / f"{self._key(url)}.json"
        return cache_file.exists() and not self._is_expired(cache_file)
