"""通用文档爬虫 — HTTP 优先，SPA 自动降级 Playwright"""
import asyncio
import sys
from pathlib import Path

import yaml

from crawler.base import CrawlConfig, CrawlResult
from crawler.http_crawler import HTTPCrawler
from crawler.playwright import PlaywrightCrawler
from crawler.content_detector import ContentDetector
from parser.html_parser import HTMLParser
from chunker.semantic import SemanticChunker
from storage.vector_store import VectorStore
from storage.embedding import ChineseEmbeddingFunction
from storage.metadata_db import MetadataDB


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    return yaml.safe_load(config_path.read_text())


def parse_args() -> dict:
    """解析 CLI 参数"""
    args = sys.argv[1:]
    result = {
        "urls": [],
        "urls_file": "",
        "strategy": "auto",
        "start_url": "",
    }

    i = 0
    while i < len(args):
        if args[i] == "--urls" and i + 1 < len(args):
            result["urls_file"] = args[i + 1]
            i += 2
        elif args[i] == "--playwright":
            result["strategy"] = "playwright"
            i += 1
        elif args[i] == "--http":
            result["strategy"] = "http"
            i += 1
        elif not args[i].startswith("-"):
            result["urls"].append(args[i])
            i += 1
        else:
            print(f"未知参数: {args[i]}")
            i += 1

    return result


def load_urls_from_file(path: str) -> list[str]:
    """从文件加载 URL 列表（每行一个 URL，忽略空行和注释）"""
    urls = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


async def smart_crawl(
    start_url: str,
    config: CrawlConfig,
    url_list: list[str] = None,
) -> list[CrawlResult]:
    """
    智能爬取：
    1. HTTP 先试（快）
    2. ContentDetector 检测内容
    3. 无内容 → 降级 Playwright
    """
    detector = ContentDetector()
    http_crawler = HTTPCrawler()
    pw_crawler = PlaywrightCrawler()

    # 确定 URL 列表
    if url_list:
        urls = url_list
        print(f"[爬取] 使用传入的 {len(urls)} 个 URL")
    else:
        # 自动发现：先用 HTTP 看能不能拿到链接
        print(f"[爬取] 从 {start_url} 自动发现页面...")
        http_results = await http_crawler.crawl(start_url, config)
        if http_results:
            urls = [r.url for r in http_results]
            print(f"[爬取] HTTP 发现 {len(urls)} 个页面")
        else:
            # HTTP 失败，用 Playwright 发现
            print("[爬取] HTTP 未发现页面，尝试 Playwright 发现...")
            config.urls = [start_url]
            config.strategy = "playwright"
            pw_results = await pw_crawler.crawl(start_url, config)
            urls = [r.url for r in pw_results]
            print(f"[爬取] Playwright 发现 {len(urls)} 个页面")

    # 策略选择
    strategy = config.strategy
    if strategy == "auto":
        # 检测第一个页面判断是否需要 Playwright
        if urls:
            first_url = urls[0]
            print(f"[检测] 测试 {first_url} 是否需要渲染...")
            try:
                import httpx
                async with httpx.AsyncClient(timeout=config.timeout, follow_redirects=True) as client:
                    resp = await client.get(first_url, headers={"User-Agent": config.user_agent})
                    has_content = detector.has_real_content(resp.text)
                    print(f"[检测] HTTP 内容质量: {'有效' if has_content else '需要渲染'}")
                    strategy = "http" if has_content else "playwright"
            except Exception as e:
                print(f"[检测] HTTP 测试失败: {e}，使用 Playwright")
                strategy = "playwright"

    print(f"[策略] {strategy.upper()}")

    # 执行爬取
    if strategy == "http":
        config.urls = urls
        results = await http_crawler.crawl(start_url, config)
    elif strategy == "playwright":
        config.urls = urls
        results = await pw_crawler.crawl(start_url, config)
    else:
        # auto 降级：逐个检测
        results = []
        http_failed = []

        # 先批量 HTTP
        config.urls = urls
        http_results = await http_crawler.crawl(start_url, config)
        http_urls = {r.url for r in http_results}

        for r in http_results:
            if detector.has_real_content(r.html):
                results.append(r)
            else:
                http_failed.append(r.url)

        # HTTP 失败的用 Playwright 补
        if http_failed:
            print(f"\n[降级] {len(http_failed)} 个页面需要 Playwright 渲染")
            config.urls = http_failed
            pw_results = await pw_crawler.crawl(start_url, config)
            results.extend(pw_results)

    return results


async def main():
    args = parse_args()

    if not args["urls"] and not args["urls_file"] and not args["start_url"]:
        print("用法:")
        print("  python crawl_all.py <URL>                     # 自动发现 + 爬取")
        print("  python crawl_all.py --urls urls.txt           # 从文件读取 URL 列表")
        print("  python crawl_all.py URL1 URL2 URL3            # 直接传入 URL")
        print("  python crawl_all.py --playwright <URL>        # 强制 Playwright")
        print("  python crawl_all.py --http <URL>              # 强制 HTTP")
        print()
        print("示例:")
        print("  python crawl_all.py https://docs.python.org/3/")
        print("  python crawl_all.py --urls im_urls.txt")
        return

    config_data = load_config()

    # 加载 URL 列表
    url_list = args["urls"]
    if args["urls_file"]:
        url_list.extend(load_urls_from_file(args["urls_file"]))

    start_url = url_list[0] if url_list else args["start_url"]

    crawl_config = CrawlConfig(
        max_depth=config_data["crawler"]["max_depth"],
        max_concurrent=config_data["crawler"]["max_concurrent"],
        delay_between_requests=config_data["crawler"]["delay_between_requests"],
        user_agent=config_data["crawler"]["user_agent"],
        timeout=config_data["crawler"]["timeout"],
        cache_enabled=config_data["crawler"]["cache_enabled"],
        cache_dir=config_data["crawler"]["cache_dir"],
        cache_ttl=config_data["crawler"]["cache_ttl"],
        max_retries=config_data["crawler"]["max_retries"],
        respect_robots=config_data["crawler"]["respect_robots"],
        strategy=args["strategy"],
    )

    print(f"{'=' * 60}")
    print(f"通用文档爬虫")
    print(f"{'=' * 60}")

    # 爬取
    crawl_results = await smart_crawl(start_url, crawl_config, url_list or None)
    print(f"\n爬取完成: {len(crawl_results)} 个页面")

    if not crawl_results:
        print("未爬取到任何页面")
        return

    # 初始化组件
    parser = HTMLParser()
    chunker = SemanticChunker(max_tokens=config_data["chunker"]["max_tokens"])
    vector_store = VectorStore(
        persist_dir=config_data["storage"]["chroma_dir"],
        embedding_function=ChineseEmbeddingFunction(),
    )
    metadata_db = MetadataDB(db_path=config_data["storage"]["sqlite_path"])

    # 解析 + 切片 + 存储
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

        print(f"[解析 {i+1}/{len(crawl_results)}] {result.title[:40]} - {len(chunks)} chunks")

    # 批量存储
    if all_chunks:
        vector_store.add(all_chunks)
        metadata_db.add(all_chunks)

    print(f"\n{'=' * 60}")
    print(f"索引完成!")
    print(f"  - 页面数: {len(crawl_results)}")
    print(f"  - Chunks: {len(all_chunks)}")
    print(f"  - 向量存储: {vector_store.count()} chunks")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
