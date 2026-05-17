#!/bin/bash
set -e

echo "=== doc-rag 启动 ==="

# 1. 首次爬取
if [ -f "urls.txt" ] && [ "$(python -c "import chromadb; c=chromadb.PersistentClient(path='data/chroma'); print(c.get_collection('doc_chunks').count())" 2>/dev/null)" = "0" ]; then
    echo "[启动] 首次运行，爬取文档..."
    python crawl_all.py --urls urls.txt
fi

# 2. 启动 cron
echo "[启动] 启动定时更新 (每天凌晨 2 点)"
cron

# 3. 根据模式启动
MODE="${DOC_RAG_MODE:-api}"

case "$MODE" in
    mcp-sse)
        # MCP HTTP 模式：Agent 通过 HTTP 连接
        PORT="${MCP_PORT:-9000}"
        echo "[启动] MCP SSE 模式 (端口 $PORT)"
        exec python mcp_server.py
        ;;
    mcp)
        # MCP stdio 模式：本地 Agent 直接调用
        echo "[启动] MCP stdio 模式"
        exec python mcp_server.py
        ;;
    *)
        # API 模式：HTTP 服务
        echo "[启动] API 模式 (端口 8000)"
        exec python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
        ;;
esac
