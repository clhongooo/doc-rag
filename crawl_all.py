"""通用文档爬虫 — HTTP 优先，SPA 自动降级，增量更新"""
import asyncio
import hashlib
import os
import sys
from pathlib import Path

import yaml

from crawler.base import CrawlConfig, CrawlResult
from crawler.http_crawler import HTTPCrawler
from crawler.playwright import PlaywrightCrawler
from crawler.content_detector import ContentDetector
from crawler.change_detector import ChangeDetector
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
        "force": False,
        "depth": 0,  # 0=不发现子页面, >0=自动发现
    }

    i = 0
    while i < len(args):
        if args[i] == "--urls" and i + 1 < len(args):
            result["urls_file"] = args[i + 1]
            i += 2
        elif args[i] == "--depth" and i + 1 < len(args):
            result["depth"] = int(args[i + 1])
            i += 2
        elif args[i] == "--playwright":
            result["strategy"] = "playwright"
            i += 1
        elif args[i] == "--http":
            result["strategy"] = "http"
            i += 1
        elif args[i] == "--force":
            result["force"] = True
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


def load_urls_from_env() -> list[str]:
    """从环境变量加载 URL 列表（逗号或换行分隔）"""
    raw = os.getenv("CRAWL_URLS", "")
    if not raw:
        return []
    urls = []
    for item in raw.replace("\n", ",").split(","):
        item = item.strip()
        if item and item.startswith("http"):
            urls.append(item)
    return urls


async def filter_changed_urls(urls: list[str], change_detector: ChangeDetector, force: bool = False) -> list[str]:
    """过滤出有变化的 URL"""
    if force:
        print(f"[变更检测] 强制模式，爬取全部 {len(urls)} 个 URL")
        return urls

    print(f"[变更检测] 检查 {len(urls)} 个 URL 是否更新...")
    changed = []
    skipped = 0

    for i, url in enumerate(urls):
        try:
            if await change_detector.has_changed(url):
                changed.append(url)
            else:
                skipped += 1
                if (i + 1) % 20 == 0:
                    print(f"  进度: {i+1}/{len(urls)} (跳过 {skipped})")
        except Exception:
            changed.append(url)  # 异常时保守爬取

    print(f"[变更检测] 需更新: {len(changed)}, 可跳过: {skipped}")
    return changed


async def smart_crawl(
    start_url: str,
    config: CrawlConfig,
    url_list: list[str] = None,
    force: bool = False,
    depth: int = 0,
) -> list[CrawlResult]:
    """
    智能爬取：
    1. HTTP 先试（快）
    2. ContentDetector 检测内容
    3. 无内容 → 降级 Playwright
    4. ChangeDetector 检测变化，跳过未更新页面
    """
    detector = ContentDetector()
    http_crawler = HTTPCrawler()
    pw_crawler = PlaywrightCrawler()
    metadata_db = MetadataDB(db_path="data/sqlite/metadata.db")
    change_detector = ChangeDetector(metadata_db)

    # 确定 URL 列表
    if url_list:
        if depth > 0:
            # 从每个 URL 发现子页面
            print(f"[爬取] 从 {len(url_list)} 个 URL 发现子页面 (深度 {depth})...")
            discovered = set()
            for seed_url in url_list:
                config_copy = CrawlConfig(
                    max_depth=depth,
                    max_concurrent=config.max_concurrent,
                    delay_between_requests=config.delay_between_requests,
                    user_agent=config.user_agent,
                    timeout=config.timeout,
                    cache_enabled=config.cache_enabled,
                    cache_dir=config.cache_dir,
                    cache_ttl=config.cache_ttl,
                    max_retries=config.max_retries,
                    respect_robots=config.respect_robots,
                    strategy="http",
                )
                try:
                    results = await http_crawler.crawl(seed_url, config_copy)
                    for r in results:
                        discovered.add(r.url)
                    print(f"  {seed_url}: 发现 {len(results)} 个页面")
                except Exception as e:
                    print(f"  {seed_url}: 发现失败 - {e}")
            urls = list(discovered)
            print(f"[爬取] 共发现 {len(urls)} 个唯一页面")
        else:
            urls = url_list
            print(f"[爬取] 使用传入的 {len(urls)} 个 URL (depth=0, 不发现子页面)")
    else:
        # 自动发现
        print(f"[爬取] 从 {start_url} 自动发现页面...")
        http_results = await http_crawler.crawl(start_url, config)
        if http_results:
            urls = [r.url for r in http_results]
            print(f"[爬取] HTTP 发现 {len(urls)} 个页面")
        else:
            print("[爬取] HTTP 未发现页面，尝试 Playwright 发现...")
            config.urls = [start_url]
            config.strategy = "playwright"
            pw_results = await pw_crawler.crawl(start_url, config)
            urls = [r.url for r in pw_results]
            print(f"[爬取] Playwright 发现 {len(urls)} 个页面")

    # 增量检测：过滤未变化的 URL
    urls = await filter_changed_urls(urls, change_detector, force)
    if not urls:
        print("[爬取] 所有页面未更新，跳过")
        return []

    # 策略选择
    strategy = config.strategy
    if strategy == "auto":
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
        results = []
        http_failed = []
        config.urls = urls
        http_results = await http_crawler.crawl(start_url, config)

        for r in http_results:
            if detector.has_real_content(r.html):
                results.append(r)
            else:
                http_failed.append(r.url)

        if http_failed:
            print(f"\n[降级] {len(http_failed)} 个页面需要 Playwright 渲染")
            config.urls = http_failed
            pw_results = await pw_crawler.crawl(start_url, config)
            results.extend(pw_results)

    # 记录爬取结果（用于下次对比）
    for r in results:
        change_detector.record(r.url, r.html)

    metadata_db.close()
    return results


async def main():
    args = parse_args()

    # 加载 URL：CLI 参数 > 环境变量 > urls.txt
    url_list = list(args["urls"])
    if args["urls_file"]:
        url_list.extend(load_urls_from_file(args["urls_file"]))
    if not url_list:
        url_list.extend(load_urls_from_env())
    if not url_list and not args["start_url"]:
        print("用法:")
        print("  python crawl_all.py <URL>                     # 自动发现 + 爬取")
        print("  python crawl_all.py --urls urls.txt           # 从文件读取 URL 列表")
        print("  python crawl_all.py --depth 2 <URL>           # 从 URL 发现子页面（深度 2）")
        print("  python crawl_all.py URL1 URL2 URL3            # 直接传入 URL")
        print("  CRAWL_URLS=url1,url2 python crawl_all.py      # 环境变量传入")
        print()
        print("参数:")
        print("  --depth N     自动发现子页面的深度 (默认 0=不发现)")
        print("  --force       强制全量爬取（忽略变更检测）")
        print("  --playwright  强制使用 Playwright")
        print("  --http        强制使用 HTTP")
        return

    config_data = load_config()

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
    crawl_results = await smart_crawl(start_url, crawl_config, url_list or None, args["force"], depth=args["depth"])
    print(f"\n爬取完成: {len(crawl_results)} 个页面")

    if not crawl_results:
        print("所有页面未更新或无内容")
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
