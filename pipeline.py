"""端到端 RAG 管道"""
import time
import yaml
from pathlib import Path
from typing import Optional

from crawler.base import CrawlConfig
from crawler.router import CrawlerRouter
from parser.html_parser import HTMLParser
from chunker.semantic import SemanticChunker
from storage.vector_store import VectorStore
from storage.embedding import ChineseEmbeddingFunction
from storage.metadata_db import MetadataDB
from retriever.semantic import SemanticRetriever
from retriever.hybrid import HybridRetriever
from generator.llm import Generator
from generator.factory import GeneratorConfig


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    return yaml.safe_load(config_path.read_text())


class RAGPipeline:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or load_config()
        self.crawler = CrawlerRouter()
        self.parser = HTMLParser()
        self.chunker = SemanticChunker(max_tokens=self.config["chunker"]["max_tokens"])

        # 使用中文 embedding
        self.embedding_fn = ChineseEmbeddingFunction()
        self.vector_store = VectorStore(
            persist_dir=self.config["storage"]["chroma_dir"],
            embedding_function=self.embedding_fn,
        )
        self.metadata_db = MetadataDB(db_path=self.config["storage"]["sqlite_path"])
        self.retriever = SemanticRetriever(self.vector_store)
        self.generator = Generator(config=GeneratorConfig(
            provider=self.config["generator"]["provider"],
            model=self.config["generator"]["model"],
            max_tokens=self.config["generator"]["max_tokens"],
            temperature=self.config["generator"]["temperature"],
            api_key=self.config["generator"].get("api_key"),
            base_url=self.config["generator"].get("base_url"),
        ))

    async def ingest(self, url: str) -> dict:
        crawl_config = CrawlConfig(
            max_depth=self.config["crawler"]["max_depth"],
            max_concurrent=self.config["crawler"]["max_concurrent"],
            delay_between_requests=self.config["crawler"]["delay_between_requests"],
            user_agent=self.config["crawler"]["user_agent"],
            timeout=self.config["crawler"]["timeout"],
            cache_enabled=self.config["crawler"]["cache_enabled"],
            cache_dir=self.config["crawler"]["cache_dir"],
            cache_ttl=self.config["crawler"]["cache_ttl"],
            max_retries=self.config["crawler"]["max_retries"],
            respect_robots=self.config["crawler"]["respect_robots"],
        )

        crawl_results = await self.crawler.crawl(url, crawl_config)

        all_chunks = []
        for result in crawl_results:
            doc = self.parser.parse(result.url, result.title, result.html)

            for section in doc.sections:
                section.breadcrumb = [doc.title, section.heading]

            chunks = self.chunker.chunk(doc)
            for chunk in chunks:
                chunk.metadata.url = result.url
                chunk.metadata.title = result.title
            all_chunks.extend(chunks)

        self.vector_store.add(all_chunks)
        self.metadata_db.add(all_chunks)

        return {
            "pages_crawled": len(crawl_results),
            "chunks_indexed": len(all_chunks),
        }

    async def query(self, question: str, top_k: int = None) -> dict:
        if top_k is None:
            top_k = self.config.get("retriever", {}).get("top_k", 20)

        timings = {}

        # 阶段1: 检索
        t0 = time.perf_counter()
        chunks = self.retriever.retrieve(question, top_k=top_k)
        timings["retrieve_ms"] = round((time.perf_counter() - t0) * 1000)

        # 阶段2: 生成
        t0 = time.perf_counter()
        response = await self.generator.generate(question, chunks, self.metadata_db)
        timings["generate_ms"] = round((time.perf_counter() - t0) * 1000)

        # 总耗时
        timings["total_ms"] = timings["retrieve_ms"] + timings["generate_ms"]

        response.timings = timings
        return response

    def status(self) -> dict:
        return {
            "vector_store_count": self.vector_store.count(),
            "metadata_db_count": self.metadata_db.count(),
        }
