from bs4 import BeautifulSoup, Tag

from .base import DocContent, Section
from .extractor import ContentExtractor


class HTMLParser:
    def __init__(self):
        self.extractor = ContentExtractor()

    def parse(self, url: str, title: str, html: str) -> DocContent:
        soup = BeautifulSoup(html, "html.parser")

        # 先定位正文内容容器（跳过导航/侧边栏等外壳）
        content_selectors = [
            "doc-article-content", "J-markdown-box", "doc-content",
            "markdown-body", "article", "main",
        ]
        for sel in content_selectors:
            container = soup.find(class_=sel) or soup.find(sel)
            if container and len(container.get_text(strip=True)) > 100:
                soup = container
                break

        # 在内容容器内清理噪声（避免误删包含内容的祖先元素）
        self._remove_noise(soup)

        sections = self._split_by_heading(soup)
        return DocContent(url=url, title=title, sections=sections)

    def _remove_noise(self, soup: BeautifulSoup) -> None:
        for tag in soup.find_all(["nav", "footer", "header", "aside"]):
            tag.decompose()

        for tag in soup.find_all(class_=lambda c: c and any(
            x in c for x in [
                "sidebar", "menu", "breadcrumb", "pagination", "toc",
                "share", "feedback", "comment", "recommend",
                "rno-header", "rno-footer", "rno-side",
            ]
        )):
            tag.decompose()

        # 移除 base64 图片
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src.startswith("data:"):
                img.decompose()

        # 移除包含分享/反馈文本的元素
        for tag in soup.find_all(string=lambda t: t and any(
            x in t for x in ["微信扫一扫", "新浪微博", "复制链接", "链接复制成功", "我的收藏"]
        )):
            parent = tag.parent
            if parent:
                parent.decompose()

    def _split_by_heading(self, soup: BeautifulSoup) -> list[Section]:
        # 移除无用标题及其内容
        skip_headings = {"本页目录", "相关文档", "文档信息", "最近更新", "意见反馈"}
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            if heading.get_text(strip=True) in skip_headings:
                for sibling in list(heading.next_siblings):
                    if hasattr(sibling, "name") and sibling.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                        break
                    if hasattr(sibling, "decompose"):
                        sibling.decompose()
                heading.decompose()

        # 收集所有 heading 及其在 DOM 中的顺序位置
        heading_tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        if not heading_tags:
            full_text = soup.get_text(separator="\n", strip=True)
            if not full_text:
                return []
            section = Section(heading="Main", level=1, text=full_text)
            section.images = self.extractor.extract_images(soup)
            section.tables = self.extractor.extract_tables(soup)
            section.code_blocks = self.extractor.extract_code_blocks(soup)
            return [section]

        # 建立 heading 在 tree 中的 DFS 顺序
        # 遍历整个 DOM 树，记录每个元素的出现顺序
        ordered_elements = []
        self._dfs_collect(soup, ordered_elements)

        # 找到每个 heading 在有序列表中的位置，并计算其子树结束位置
        heading_positions = []
        for h in heading_tags:
            try:
                start_pos = ordered_elements.index(h)
                # heading 的子树结束位置 = 下一个非后代元素的位置
                end_pos = start_pos + 1
                while end_pos < len(ordered_elements):
                    el = ordered_elements[end_pos]
                    # 检查 el 是否是 h 的后代
                    if self._is_descendant(el, h):
                        end_pos += 1
                    else:
                        break
                heading_positions.append((start_pos, end_pos, h))
            except ValueError:
                continue

        if not heading_positions:
            full_text = soup.get_text(separator="\n", strip=True)
            return [Section(heading="Main", level=1, text=full_text)]

        sections = []
        for i, (start_pos, subtree_end, h) in enumerate(heading_positions):
            h_text = h.get_text(strip=True)
            level = int(h.name[1])

            # 收集该 heading 子树之后到下一个 heading 子树之间的元素
            next_start = heading_positions[i + 1][0] if i + 1 < len(heading_positions) else len(ordered_elements)
            section_elements = ordered_elements[subtree_end:next_start]

            # 构建子 soup
            section_html = "".join(str(el) for el in section_elements if isinstance(el, Tag))
            section_soup = BeautifulSoup(section_html, "html.parser")

            section_text = section_soup.get_text(separator="\n", strip=True)
            if not section_text:
                continue

            section = Section(heading=h_text, level=level, text=section_text)
            section.images = self.extractor.extract_images(section_soup)
            section.tables = self.extractor.extract_tables(section_soup)
            section.code_blocks = self.extractor.extract_code_blocks(section_soup)
            sections.append(section)

        if not sections:
            full_text = soup.get_text(separator="\n", strip=True)
            sections = [Section(heading="Main", level=1, text=full_text)]

        return sections

    def _dfs_collect(self, node, result: list) -> None:
        """深度优先遍历收集所有元素节点"""
        if isinstance(node, Tag):
            result.append(node)
            for child in node.children:
                self._dfs_collect(child, result)

    def _is_descendant(self, child, parent) -> bool:
        """检查 child 是否是 parent 的后代"""
        node = child.parent
        while node is not None:
            if node is parent:
                return True
            node = node.parent
        return False
