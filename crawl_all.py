"""批量爬取文档目录"""
import asyncio
import sys
from pathlib import Path

import yaml

from crawler.base import CrawlConfig
from crawler.playwright import PlaywrightCrawler
from parser.html_parser import HTMLParser
from chunker.semantic import SemanticChunker
from storage.vector_store import VectorStore
from storage.metadata_db import MetadataDB


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    return yaml.safe_load(config_path.read_text())


async def main():
    if len(sys.argv) < 2:
        print("用法: python crawl_all.py <目录URL>")
        print("示例: python crawl_all.py https://cloud.tencent.com/document/product/548/61710")
        return

    url = sys.argv[1]
    config = load_config()

    print(f"=" * 60)
    print(f"开始爬取文档目录: {url}")
    print(f"=" * 60)

    # 初始化组件
    crawler = PlaywrightCrawler()
    parser = HTMLParser()
    chunker = SemanticChunker(max_tokens=config["chunker"]["max_tokens"])
    vector_store = VectorStore(persist_dir=config["storage"]["chroma_dir"])
    metadata_db = MetadataDB(db_path=config["storage"]["sqlite_path"])

    crawl_config = CrawlConfig(
        max_depth=config["crawler"]["max_depth"],
        max_concurrent=config["crawler"]["max_concurrent"],
        delay_between_requests=config["crawler"]["delay_between_requests"],
        user_agent=config["crawler"]["user_agent"],
        timeout=config["crawler"]["timeout"],
        cache_enabled=config["crawler"]["cache_enabled"],
        cache_dir=config["crawler"]["cache_dir"],
        cache_ttl=config["crawler"]["cache_ttl"],
        max_retries=config["crawler"]["max_retries"],
        respect_robots=config["crawler"]["respect_robots"],
    )

    # 爬取
    crawl_results = await crawler.crawl(url, crawl_config)
    print(f"\n爬取完成: {len(crawl_results)} 个页面")

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

    print(f"\n" + "=" * 60)
    print(f"索引完成!")
    print(f"  - 页面数: {len(crawl_results)}")
    print(f"  - Chunks: {len(all_chunks)}")
    print(f"  - 向量存储: {vector_store.count()} chunks")
    print(f"=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
