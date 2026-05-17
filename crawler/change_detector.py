"""检测页面是否更新，避免重复爬取"""
import hashlib
from typing import Optional

import httpx

from storage.metadata_db import MetadataDB


class ChangeDetector:
    """通过 HTTP 头 / 内容哈希判断页面是否变化"""

    def __init__(self, metadata_db: MetadataDB):
        self.db = metadata_db

    async def has_changed(self, url: str, timeout: int = 10) -> bool:
        """
        检测页面是否变化。
        返回 True = 需要重新爬取，False = 可跳过。
        """
        page_info = self.db.get_page(url)

        # 首次爬取，必须抓
        if not page_info:
            return True

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                # 用 HEAD 请求检查头（快，不下载内容）
                resp = await client.head(url)

                # 检查 Last-Modified
                last_modified = resp.headers.get("last-modified", "")
                if last_modified and last_modified == page_info.get("last_modified"):
                    return False  # 未修改

                # 检查 ETag
                etag = resp.headers.get("etag", "")
                if etag and etag == page_info.get("etag"):
                    return False  # 未修改

                # 头没有有用信息，下载内容比哈希
                if not last_modified and not etag:
                    resp = await client.get(url)
                    content_hash = hashlib.md5(resp.text.encode()).hexdigest()
                    if content_hash == page_info.get("content_hash"):
                        return False  # 内容相同

                # 有头但不匹配，说明变了
                return True

        except Exception:
            # 网络异常，保守起见重新爬取
            return True

    def record(self, url: str, html: str, last_modified: str = "", etag: str = "") -> None:
        """记录页面信息，下次对比用"""
        content_hash = hashlib.md5(html.encode()).hexdigest() if html else ""
        self.db.update_page(url, last_modified=last_modified, etag=etag, content_hash=content_hash)
