"""统计指定 URL 下的子页面数量（扫描导航树）"""
import asyncio
import sys
from urllib.parse import urlparse

from playwright.async_api import async_playwright


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://cloud.tencent.com/document/product/269"

    print(f"正在探测: {url}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 多轮展开折叠节点
        for _ in range(3):
            expanded = False
            for sel in ["[class*='expand']", "[class*='toggle']"]:
                for el in await page.query_selector_all(sel):
                    try:
                        if await el.is_visible():
                            await el.click()
                            expanded = True
                            await asyncio.sleep(0.2)
                    except:
                        pass
            if not expanded:
                break
            await asyncio.sleep(0.5)

        # 收集所有文档链接（基于 URL 路径前缀匹配）
        base_path = urlparse(url).path.rstrip("/")
        # 如果是叶子页面，取父级路径做前缀
        parts = base_path.rsplit("/", 1)
        if len(parts) > 1 and parts[-1].isdigit():
            prefix = parts[0] + "/"
        else:
            prefix = base_path + "/"

        links = await page.evaluate("""(prefix) => {
            const urls = new Map();
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href.split('#')[0];
                const path = new URL(href).pathname;
                if (path.startsWith(prefix) && !urls.has(href)) {
                    urls.set(href, a.innerText.trim().substring(0, 50));
                }
            });
            return Array.from(urls.entries());
        }""", prefix)

        await browser.close()

    print(f"共发现 {len(links)} 个子页面:\n")
    for i, (href, text) in enumerate(sorted(links, key=lambda x: x[0]), 1):
        print(f"  {i:3d}. [{text}] {href}")


if __name__ == "__main__":
    asyncio.run(main())
