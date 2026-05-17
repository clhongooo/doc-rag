from bs4 import BeautifulSoup, Tag

from .base import CodeBlock, Image, Table


class ContentExtractor:
    def extract_images(self, soup: BeautifulSoup) -> list[Image]:
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if not src or src.startswith("data:"):
                continue

            alt = img.get("alt", "")
            caption = self._find_caption(img)
            images.append(Image(src=src, alt=alt, caption=caption))
        return images

    def extract_tables(self, soup: BeautifulSoup) -> list[Table]:
        tables = []
        for table in soup.find_all("table"):
            headers = []
            rows = []

            thead = table.find("thead")
            if thead:
                for th in thead.find_all("th"):
                    headers.append(th.get_text(strip=True))

            tbody = table.find("tbody") or table
            for tr in tbody.find_all("tr"):
                row = []
                for td in tr.find_all(["td", "th"]):
                    row.append(td.get_text(strip=True))
                if row:
                    rows.append(row)

            caption = ""
            cap_tag = table.find("caption")
            if cap_tag:
                caption = cap_tag.get_text(strip=True)

            if headers or rows:
                tables.append(Table(headers=headers, rows=rows, caption=caption))
        return tables

    def extract_code_blocks(self, soup: BeautifulSoup) -> list[CodeBlock]:
        code_blocks = []
        for pre in soup.find_all("pre"):
            code = pre.find("code")
            if not code:
                continue

            language = ""
            class_list = code.get("class", [])
            for cls in class_list:
                if cls.startswith("language-") or cls.startswith("lang-"):
                    language = cls.split("-", 1)[1]
                    break

            code_text = code.get_text()
            if code_text.strip():
                code_blocks.append(CodeBlock(language=language, code=code_text))
        return code_blocks

    def _find_caption(self, img_tag: Tag) -> str:
        parent = img_tag.parent
        if parent and parent.name == "figure":
            figcaption = parent.find("figcaption")
            if figcaption:
                return figcaption.get_text(strip=True)

        next_sibling = img_tag.next_sibling
        if next_sibling and isinstance(next_sibling, Tag) and next_sibling.name == "figcaption":
            return next_sibling.get_text(strip=True)

        return ""
