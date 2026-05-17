"""检测页面是否更新，避免重复爬取"""
import hashlib
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from storage.metadata_db import MetadataDB


class ChangeDetector:
    """通过 HTTP 头 / 内容哈希判断页面是否变化"""

    # 内容容器选择器（哈希只对比正文，忽略动态部分）
    CONTENT_SELECTORS = [
        ".doc-article-content", ".doc-content", ".J-markdown-box",
        ".markdown-body", ".rst-content", ".md-content",
        "article", "main", '[role="main"]',
        "#content", ".content", ".page-content",
    ]

    def __init__(self, metadata_db: MetadataDB):
        self.db = metadata_db

    def _extract_content_hash(self, html: str) -> str:
        """提取正文内容的哈希（忽略动态元素）"""
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return hashlib.md5(html.encode()).hexdigest()

        # 尝试提取正文容器
        for selector in self.CONTENT_SELECTORS:
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 50:
                # 移除 script/style 标签
                for tag in el.find_all(["script", "style", "noscript"]):
                    tag.decompose()
                text = el.get_text(strip=True)
                return hashlib.md5(text.encode()).hexdigest()

        # fallback: 提取 body 文本
        body = soup.find("body")
        if body:
            for tag in body.find_all(["script", "style", "noscript"]):
                tag.decompose()
            text = body.get_text(strip=True)
            return hashlib.md5(text.encode()).hexdigest()

        return hashlib.md5(html.encode()).hexdigest()

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
                # HEAD 请求检查头
                resp = await client.head(url)

                # 检查 Last-Modified
                last_modified = resp.headers.get("last-modified", "")
                if last_modified and last_modified == page_info.get("last_modified"):
                    return False  # 未修改

                # 检查 ETag
                etag = resp.headers.get("etag", "")
                if etag and etag == page_info.get("etag"):
                    return False  # 未修改

                # 下载内容，提取正文哈希对比
                resp = await client.get(url)

                # 跳过 404/5xx 页面（不更新缓存）
                if resp.status_code >= 400:
                    return False

                content_hash = self._extract_content_hash(resp.text)
                if content_hash == page_info.get("content_hash"):
                    return False  # 内容相同

                return True

        except Exception:
            # 网络异常，保守起见重新爬取
            return True

    def record(self, url: str, html: str, last_modified: str = "", etag: str = "") -> None:
        """记录页面信息，下次对比用"""
        content_hash = self._extract_content_hash(html) if html else ""
        self.db.update_page(url, last_modified=last_modified, etag=etag, content_hash=content_hash)
