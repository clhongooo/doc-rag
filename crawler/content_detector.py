"""检测 HTML 是否包含真实文档内容（区分 SPA 空壳 / 反爬 JS / 有效内容）"""
import re
from bs4 import BeautifulSoup


class ContentDetector:
    """判断 HTML 内容质量，决定是否需要 Playwright 渲染"""

    # 反爬 / 无内容特征（正则模式）
    BOT_PATTERNS = [
        r"function a\(a\)\{",             # 腾讯云反爬 JS
        r"EO_Bot_Ssid",                    # 腾讯云 bot 检测
        r"__NEXT_DATA__",                  # Next.js 空壳（未 hydration）
        r"window\.__INITIAL_STATE__",      # SSR 空壳
        r'<div id="root"></div>',           # React 空壳
        r'<div id="app"></div>',            # Vue 空壳
        r"window\.__remixContext",          # Remix 空壳
    ]

    # 常见文档内容容器选择器
    CONTENT_SELECTORS = [
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

    def has_real_content(self, html: str) -> bool:
        """HTML 是否包含可提取的真实文档内容"""
        if not html or len(html) < 200:
            return False

        # 检查反爬特征
        for pattern in self.BOT_PATTERNS:
            if re.search(pattern, html):
                return False

        # 检查内容容器
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return False

        for selector in self.CONTENT_SELECTORS:
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 50:
                return True

        # fallback: body 文本长度
        body = soup.find("body")
        if body:
            text = body.get_text(strip=True)
            # 排除纯 JS 页面（文本全是 function/var/const）
            js_ratio = len(re.findall(r"\b(function|var|const|let|return)\b", text)) / max(len(text.split()), 1)
            if len(text) > 200 and js_ratio < 0.3:
                return True

        return False

    def extract_title(self, html: str) -> str:
        """从 HTML 提取标题"""
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return ""
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return ""
