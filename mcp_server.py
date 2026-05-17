"""MCP Server — 将 doc-rag 暴露为 MCP 工具供 Agent 调用

支持两种传输模式：
  - stdio: 本地 Agent 直接调用（默认）
  - sse:   HTTP 端口，远程/多 Agent 共享
"""
import json
import os
import asyncio
from typing import Optional

from mcp.server.fastmcp import FastMCP

from pipeline import RAGPipeline

# 初始化 RAG 管道
pipeline = RAGPipeline()

# 创建 MCP 服务器
mcp = FastMCP("doc-rag", instructions="腾讯云即时通信 IM 文档检索工具")


@mcp.tool()
async def search_docs(question: str, top_k: int = 5) -> str:
    """
    搜索腾讯云 IM 文档并生成回答。

    Args:
        question: 要搜索的问题
        top_k: 返回的相关文档数量（默认 5）

    Returns:
        包含回答和来源的 JSON 字符串
    """
    response = await pipeline.query(question, top_k=top_k)

    result = {
        "answer": response.answer,
        "sources": [
            {"url": s.url, "title": getattr(s, "title", "")}
            for s in response.sources
        ],
    }

    if hasattr(response, "images") and response.images:
        result["images"] = [
            {"url": img.url, "alt": img.alt}
            for img in response.images
        ]

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_doc(url: str) -> str:
    """
    获取指定 URL 的文档内容。

    Args:
        url: 文档 URL

    Returns:
        文档内容的 JSON 字符串
    """
    chunks = pipeline.metadata_db.query_by_url(url)

    if not chunks:
        return json.dumps({"error": f"未找到 URL: {url}"}, ensure_ascii=False)

    # 合并所有 chunks
    content_parts = []
    for chunk in chunks:
        section = chunk.get("section", "")
        if section:
            content_parts.append(f"## {section}")
        # 从 vector_store 获取 chunk 文本
        chunk_data = pipeline.vector_store.get(chunk["id"])
        if chunk_data and chunk_data.get("documents"):
            content_parts.append(chunk_data["documents"][0])

    result = {
        "url": url,
        "title": chunks[0].get("title", ""),
        "content": "\n\n".join(content_parts),
        "chunks": len(chunks),
    }

    # 包含图片和表格
    images = []
    tables = []
    for chunk in chunks:
        images.extend(chunk.get("images", []))
        tables.extend(chunk.get("tables", []))

    if images:
        result["images"] = images
    if tables:
        result["tables"] = tables

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def list_docs(keyword: str = "") -> str:
    """
    列出已索引的文档。

    Args:
        keyword: 过滤关键词（可选）

    Returns:
        文档列表的 JSON 字符串
    """
    conn = pipeline.metadata_db.conn
    cursor = conn.execute(
        "SELECT DISTINCT url, title FROM chunks WHERE url LIKE ? ORDER BY url",
        (f"%{keyword}%",) if keyword else ("%",),
    )
    rows = cursor.fetchall()

    docs = [{"url": row[0], "title": row[1]} for row in rows]

    return json.dumps({
        "count": len(docs),
        "docs": docs,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 根据环境变量选择传输模式
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    port = int(os.getenv("MCP_PORT", "9000"))

    if transport == "sse":
        # HTTP SSE 模式：Agent 通过 HTTP 连接
        print(f"[MCP] SSE 模式，端口 {port}")
        mcp.run(transport="sse", port=port)
    else:
        # stdio 模式：本地 Agent 直接调用
        print("[MCP] stdio 模式")
        mcp.run(transport="stdio")
