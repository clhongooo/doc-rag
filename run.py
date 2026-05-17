"""RAG 系统入口脚本"""
import asyncio
import sys

from pipeline import RAGPipeline


async def main():
    pipeline = RAGPipeline()

    if len(sys.argv) < 2:
        print("用法:")
        print("  python run.py ingest <url>     # 爬取并索引文档")
        print("  python run.py query <question>  # 查询问答")
        print("  python run.py status            # 查看索引状态")
        return

    command = sys.argv[1]

    if command == "ingest":
        if len(sys.argv) < 3:
            print("请提供 URL，例如: python run.py ingest https://example.com/docs")
            return
        url = sys.argv[2]
        print(f"开始爬取: {url}")
        result = await pipeline.ingest(url)
        print(f"完成! 爬取 {result['pages_crawled']} 页, 索引 {result['chunks_indexed']} 个 chunks")

    elif command == "query":
        if len(sys.argv) < 3:
            print("请提供问题，例如: python run.py query 如何接入推送？")
            return
        question = sys.argv[2]
        print(f"查询: {question}")
        response = await pipeline.query(question)
        print(f"\n回答:\n{response.answer}")
        print(f"\n来源:")
        for src in response.sources:
            print(f"  - {src.url}")
        if response.images:
            print(f"\n图片:")
            for img in response.images:
                print(f"  - {img.alt}: {img.url}")

    elif command == "status":
        status = pipeline.status()
        print(f"索引状态:")
        print(f"  向量存储: {status['vector_store_count']} chunks")
        print(f"  元数据: {status['metadata_db_count']} chunks")

    else:
        print(f"未知命令: {command}")


if __name__ == "__main__":
    asyncio.run(main())
