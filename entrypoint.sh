#!/bin/bash
set -e

echo "=== doc-rag 启动 ==="

# 1. 首次爬取（如果 urls.txt 存在且数据为空）
if [ -f "urls.txt" ] && [ "$(python -c "import chromadb; c=chromadb.PersistentClient(path='data/chroma'); print(c.get_collection('doc_chunks').count())" 2>/dev/null)" = "0" ]; then
    echo "[启动] 首次运行，爬取文档..."
    python crawl_all.py --urls urls.txt
fi

# 2. 启动 cron 定时更新（增量模式）
echo "[启动] 启动定时更新 (每天凌晨 2 点)"
cron

# 3. 根据环境变量选择模式
MODE="${DOC_RAG_MODE:-api}"

if [ "$MODE" = "mcp" ]; then
    # MCP 模式：stdio 传输，供 Agent 调用
    echo "[启动] MCP 模式 (stdio)"
    exec python mcp_server.py
else
    # API 模式：HTTP 服务
    echo "[启动] API 模式 (端口 8000)"
    exec python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
fi
