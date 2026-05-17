"""[已弃用] 爬取腾讯云 IM 文档 - 请使用 crawl_all.py（支持 SPA 自动降级）

用法:
    python crawl_all.py --urls im_urls.txt
    python crawl_all.py https://cloud.tencent.com/document/product/269

此文件保留用于兼容，新的通用爬虫已支持:
    - HTTP 优先，SPA 自动降级 Playwright
    - URL 列表输入
    - 浏览器复用
    - 内容质量检测
"""
import asyncio
import sys
import time
from pathlib import Path

import yaml

from crawler.base import CrawlResult
from crawler.cache import CrawlCache
from parser.html_parser import HTMLParser
from chunker.semantic import SemanticChunker
from storage.vector_store import VectorStore
from storage.embedding import ChineseEmbeddingFunction
from storage.metadata_db import MetadataDB


# 从 Tavily map + 根页面提取的全部 /document/product/269/* URL
IM_DOC_URLS = [
    "https://cloud.tencent.com/document/product/269/1497",
    "https://cloud.tencent.com/document/product/269/1498",
    "https://cloud.tencent.com/document/product/269/1499",
    "https://cloud.tencent.com/document/product/269/1500",
    "https://cloud.tencent.com/document/product/269/1501",
    "https://cloud.tencent.com/document/product/269/1502",
    "https://cloud.tencent.com/document/product/269/1518",
    "https://cloud.tencent.com/document/product/269/1519",
    "https://cloud.tencent.com/document/product/269/1520",
    "https://cloud.tencent.com/document/product/269/1522",
    "https://cloud.tencent.com/document/product/269/1523",
    "https://cloud.tencent.com/document/product/269/1606",
    "https://cloud.tencent.com/document/product/269/1608",
    "https://cloud.tencent.com/document/product/269/1614",
    "https://cloud.tencent.com/document/product/269/1617",
    "https://cloud.tencent.com/document/product/269/1623",
    "https://cloud.tencent.com/document/product/269/1632",
    "https://cloud.tencent.com/document/product/269/1671",
    "https://cloud.tencent.com/document/product/269/2282",
    "https://cloud.tencent.com/document/product/269/2716",
    "https://cloud.tencent.com/document/product/269/2720",
    "https://cloud.tencent.com/document/product/269/3571",
    "https://cloud.tencent.com/document/product/269/3662",
    "https://cloud.tencent.com/document/product/269/3663",
    "https://cloud.tencent.com/document/product/269/11673",
    "https://cloud.tencent.com/document/product/269/18799",
    "https://cloud.tencent.com/document/product/269/31408",
    "https://cloud.tencent.com/document/product/269/31409",
    "https://cloud.tencent.com/document/product/269/31999",
    "https://cloud.tencent.com/document/product/269/32429",
    "https://cloud.tencent.com/document/product/269/32458",
    "https://cloud.tencent.com/document/product/269/32472",
    "https://cloud.tencent.com/document/product/269/32473",
    "https://cloud.tencent.com/document/product/269/32474",
    "https://cloud.tencent.com/document/product/269/32577",
    "https://cloud.tencent.com/document/product/269/32578",
    "https://cloud.tencent.com/document/product/269/32579",
    "https://cloud.tencent.com/document/product/269/32671",
    "https://cloud.tencent.com/document/product/269/32688",
    "https://cloud.tencent.com/document/product/269/33099",
    "https://cloud.tencent.com/document/product/269/33544",
    "https://cloud.tencent.com/document/product/269/36852",
    "https://cloud.tencent.com/document/product/269/36887",
    "https://cloud.tencent.com/document/product/269/37059",
    "https://cloud.tencent.com/document/product/269/37190",
    "https://cloud.tencent.com/document/product/269/37411",
    "https://cloud.tencent.com/document/product/269/38453",
    "https://cloud.tencent.com/document/product/269/38492",
    "https://cloud.tencent.com/document/product/269/42440",
    "https://cloud.tencent.com/document/product/269/44498",
    "https://cloud.tencent.com/document/product/269/44499",
    "https://cloud.tencent.com/document/product/269/46181",
    "https://cloud.tencent.com/document/product/269/51940",
    "https://cloud.tencent.com/document/product/269/54106",
    "https://cloud.tencent.com/document/product/269/54111",
    "https://cloud.tencent.com/document/product/269/59590",
    "https://cloud.tencent.com/document/product/269/63008",
    "https://cloud.tencent.com/document/product/269/68091",
    "https://cloud.tencent.com/document/product/269/68286",
    "https://cloud.tencent.com/document/product/269/68823",
    "https://cloud.tencent.com/document/product/269/75260",
    "https://cloud.tencent.com/document/product/269/75261",
    "https://cloud.tencent.com/document/product/269/75269",
    "https://cloud.tencent.com/document/product/269/75270",
    "https://cloud.tencent.com/document/product/269/75283",
    "https://cloud.tencent.com/document/product/269/75284",
    "https://cloud.tencent.com/document/product/269/75285",
    "https://cloud.tencent.com/document/product/269/75286",
    "https://cloud.tencent.com/document/product/269/75287",
    "https://cloud.tencent.com/document/product/269/75288",
    "https://cloud.tencent.com/document/product/269/75289",
    "https://cloud.tencent.com/document/product/269/75290",
    "https://cloud.tencent.com/document/product/269/75291",
    "https://cloud.tencent.com/document/product/269/75294",
    "https://cloud.tencent.com/document/product/269/75295",
    "https://cloud.tencent.com/document/product/269/75315",
    "https://cloud.tencent.com/document/product/269/75318",
    "https://cloud.tencent.com/document/product/269/75321",
    "https://cloud.tencent.com/document/product/269/75327",
    "https://cloud.tencent.com/document/product/269/75343",
    "https://cloud.tencent.com/document/product/269/75366",
    "https://cloud.tencent.com/document/product/269/75394",
    "https://cloud.tencent.com/document/product/269/75400",
    "https://cloud.tencent.com/document/product/269/75409",
    "https://cloud.tencent.com/document/product/269/75416",
    "https://cloud.tencent.com/document/product/269/75417",
    "https://cloud.tencent.com/document/product/269/75419",
    "https://cloud.tencent.com/document/product/269/75429",
    "https://cloud.tencent.com/document/product/269/75511",
    "https://cloud.tencent.com/document/product/269/75979",
    "https://cloud.tencent.com/document/product/269/77270",
    "https://cloud.tencent.com/document/product/269/77389",
    "https://cloud.tencent.com/document/product/269/77392",
    "https://cloud.tencent.com/document/product/269/77536",
    "https://cloud.tencent.com/document/product/269/77764",
    "https://cloud.tencent.com/document/product/269/79074",
    "https://cloud.tencent.com/document/product/269/79076",
    "https://cloud.tencent.com/document/product/269/79077",
    "https://cloud.tencent.com/document/product/269/79078",
    "https://cloud.tencent.com/document/product/269/79079",
    "https://cloud.tencent.com/document/product/269/79080",
    "https://cloud.tencent.com/document/product/269/79139",
    "https://cloud.tencent.com/document/product/269/79588",
    "https://cloud.tencent.com/document/product/269/79703",
    "https://cloud.tencent.com/document/product/269/79721",
    "https://cloud.tencent.com/document/product/269/81038",
    "https://cloud.tencent.com/document/product/269/81906",
    "https://cloud.tencent.com/document/product/269/81908",
    "https://cloud.tencent.com/document/product/269/81910",
    "https://cloud.tencent.com/document/product/269/82462",
    "https://cloud.tencent.com/document/product/269/83556",
    "https://cloud.tencent.com/document/product/269/83795",
    "https://cloud.tencent.com/document/product/269/84296",
    "https://cloud.tencent.com/document/product/269/84480",
    "https://cloud.tencent.com/document/product/269/85676",
    "https://cloud.tencent.com/document/product/269/85833",
    "https://cloud.tencent.com/document/product/269/85834",
    "https://cloud.tencent.com/document/product/269/85835",
    "https://cloud.tencent.com/document/product/269/85837",
    "https://cloud.tencent.com/document/product/269/85839",
    "https://cloud.tencent.com/document/product/269/86374",
    "https://cloud.tencent.com/document/product/269/86462",
    "https://cloud.tencent.com/document/product/269/86463",
    "https://cloud.tencent.com/document/product/269/86464",
    "https://cloud.tencent.com/document/product/269/86465",
    "https://cloud.tencent.com/document/product/269/86986",
    "https://cloud.tencent.com/document/product/269/88897",
    "https://cloud.tencent.com/document/product/269/90141",
    "https://cloud.tencent.com/document/product/269/90175",
    "https://cloud.tencent.com/document/product/269/90479",
    "https://cloud.tencent.com/document/product/269/92654",
    "https://cloud.tencent.com/document/product/269/92658",
    "https://cloud.tencent.com/document/product/269/92662",
    "https://cloud.tencent.com/document/product/269/94368",
    "https://cloud.tencent.com/document/product/269/94369",
    "https://cloud.tencent.com/document/product/269/94373",
    "https://cloud.tencent.com/document/product/269/94433",
    "https://cloud.tencent.com/document/product/269/95131",
    "https://cloud.tencent.com/document/product/269/96056",
    "https://cloud.tencent.com/document/product/269/96059",
    "https://cloud.tencent.com/document/product/269/97653",
    "https://cloud.tencent.com/document/product/269/100621",
    "https://cloud.tencent.com/document/product/269/100645",
    "https://cloud.tencent.com/document/product/269/100650",
    "https://cloud.tencent.com/document/product/269/101439",
    "https://cloud.tencent.com/document/product/269/101971",
    "https://cloud.tencent.com/document/product/269/102299",
    "https://cloud.tencent.com/document/product/269/102326",
    "https://cloud.tencent.com/document/product/269/102561",
    "https://cloud.tencent.com/document/product/269/103557",
    "https://cloud.tencent.com/document/product/269/103558",
    "https://cloud.tencent.com/document/product/269/103732",
    "https://cloud.tencent.com/document/product/269/103733",
    "https://cloud.tencent.com/document/product/269/103734",
    "https://cloud.tencent.com/document/product/269/103946",
    "https://cloud.tencent.com/document/product/269/104816",
    "https://cloud.tencent.com/document/product/269/105570",
    "https://cloud.tencent.com/document/product/269/105571",
    "https://cloud.tencent.com/document/product/269/105582",
    "https://cloud.tencent.com/document/product/269/105712",
    "https://cloud.tencent.com/document/product/269/106486",
    "https://cloud.tencent.com/document/product/269/109892",
    "https://cloud.tencent.com/document/product/269/109899",
    "https://cloud.tencent.com/document/product/269/110762",
    "https://cloud.tencent.com/document/product/269/111769",
    "https://cloud.tencent.com/document/product/269/111803",
    "https://cloud.tencent.com/document/product/269/112884",
    "https://cloud.tencent.com/document/product/269/113912",
    "https://cloud.tencent.com/document/product/269/116538",
    "https://cloud.tencent.com/document/product/269/117335",
    "https://cloud.tencent.com/document/product/269/117847",
    "https://cloud.tencent.com/document/product/269/118065",
    "https://cloud.tencent.com/document/product/269/121069",
    "https://cloud.tencent.com/document/product/269/123364",
    "https://cloud.tencent.com/document/product/269/123942",
    "https://cloud.tencent.com/document/product/269/124295",
    "https://cloud.tencent.com/document/product/269/124308",
    "https://cloud.tencent.com/document/product/269/124570",
    "https://cloud.tencent.com/document/product/269/124571",
    "https://cloud.tencent.com/document/product/269/124918",
    "https://cloud.tencent.com/document/product/269/124919",
    "https://cloud.tencent.com/document/product/269/124920",
    "https://cloud.tencent.com/document/product/269/125817",
    "https://cloud.tencent.com/document/product/269/129148",
    "https://cloud.tencent.com/document/product/269/129588",
]


JS_EXTRACT = """() => {
    const selectors = [
        '.doc-article-content', '.J-markdown-box',
        '.doc-content', '.markdown-body',
        'article', 'main',
    ];
    for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.innerText && el.innerText.trim().length > 50) {
            return el.innerHTML;
        }
    }
    return document.body.innerHTML;
}"""


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    return yaml.safe_load(config_path.read_text())


async def crawl_all(urls: list[str], config: dict) -> list[CrawlResult]:
    """复用单个浏览器实例，逐页抓取"""
    from playwright.async_api import async_playwright

    timeout_s = config["crawler"]["timeout"]
    delay = config["crawler"]["delay_between_requests"]
    cache_enabled = config["crawler"]["cache_enabled"]
    cache_dir = config["crawler"]["cache_dir"]
    cache_ttl = config["crawler"]["cache_ttl"]

    cache = CrawlCache(cache_dir, ttl_seconds=cache_ttl) if cache_enabled else None
    results = []
    failed = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for i, url in enumerate(urls):
            # 缓存检查
            if cache and cache.has(url):
                data = cache.get(url)
                results.append(CrawlResult(**data))
                print(f"[{i+1}/{len(urls)}] 缓存: {url.split('/')[-1]}", flush=True)
                continue

            page = None
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)

                # 等待内容渲染
                try:
                    await page.wait_for_selector(
                        '.doc-article-content, .J-markdown-box, .doc-content',
                        timeout=8000,
                    )
                except Exception:
                    await asyncio.sleep(3)

                title = await page.title()
                content_html = await page.evaluate(JS_EXTRACT)

                result = CrawlResult(
                    url=url,
                    title=title or url,
                    html=content_html,
                )

                if cache:
                    cache.set(url, {
                        "url": result.url,
                        "title": result.title,
                        "html": result.html,
                        "metadata": result.metadata,
                    })

                results.append(result)
                print(f"[{i+1}/{len(urls)}] {result.title[:50]}", flush=True)

            except Exception as e:
                failed.append({"url": url, "error": str(e)})
                print(f"[{i+1}/{len(urls)}] FAIL: {url.split('/')[-1]} - {str(e)[:60]}", flush=True)
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass

            await asyncio.sleep(delay)

        await browser.close()

    if failed:
        print(f"\n失败 {len(failed)} 个:", flush=True)
        for item in failed[:10]:
            print(f"  {item['url'].split('/')[-1]}: {item['error'][:80]}", flush=True)

    return results


async def main():
    config = load_config()

    print("=" * 60, flush=True)
    print("腾讯云 IM 文档爬取 (Playwright)", flush=True)
    print(f"目标: {len(IM_DOC_URLS)} 个文档页面", flush=True)
    print("=" * 60, flush=True)

    t0 = time.perf_counter()

    # 阶段 1: 爬取
    crawl_results = await crawl_all(IM_DOC_URLS, config)
    t1 = time.perf_counter()
    print(f"\n[爬取] {len(crawl_results)} 页面 ({t1 - t0:.0f}s)", flush=True)

    if not crawl_results:
        print("无数据，退出", flush=True)
        return

    # 阶段 2: 解析 + 切片 + 存储
    parser = HTMLParser()
    chunker = SemanticChunker(max_tokens=config["chunker"]["max_tokens"])
    embedding_fn = ChineseEmbeddingFunction()
    vector_store = VectorStore(
        persist_dir=config["storage"]["chroma_dir"],
        embedding_function=embedding_fn,
    )
    metadata_db = MetadataDB(db_path=config["storage"]["sqlite_path"])

    all_chunks = []
    for i, result in enumerate(crawl_results):
        doc = parser.parse(result.url, result.title, result.html)
        for section in doc.sections:
            section.breadcrumb = [doc.title, section.heading]
        chunks = chunker.chunk(doc)
        for chunk in chunks:
            chunk.metadata.url = result.url
            chunk.metadata.title = result.title
        all_chunks.extend(chunks)
        print(f"[{i+1}/{len(crawl_results)}] {result.title[:40]} -> {len(chunks)} chunks", flush=True)

    if all_chunks:
        vector_store.add(all_chunks)
        metadata_db.add(all_chunks)

    t2 = time.perf_counter()
    print(f"\n{'=' * 60}", flush=True)
    print(f"完成!", flush=True)
    print(f"  页面: {len(crawl_results)}  Chunks: {len(all_chunks)}", flush=True)
    print(f"  向量库: {vector_store.count()} chunks", flush=True)
    print(f"  耗时: 爬取 {t1-t0:.0f}s + 索引 {t2-t1:.0f}s = {t2-t0:.0f}s", flush=True)
    print(f"{'=' * 60}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
