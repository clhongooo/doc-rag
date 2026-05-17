#!/bin/bash
set -e

echo "=== doc-rag 启动 ==="

# 1. 首次爬取（优先 urls.txt，其次 CRAWL_URLS 环境变量）
HAS_DATA=$(python -c "import chromadb; c=chromadb.PersistentClient(path='data/chroma'); print(c.get_collection('doc_chunks').count())" 2>/dev/null || echo "0")

if [ "$HAS_DATA" = "0" ]; then
    if [ -f "urls.txt" ]; then
        echo "[启动] 首次运行，从 urls.txt 爬取..."
        python crawl_all.py --urls urls.txt
    elif [ -n "$CRAWL_URLS" ]; then
        echo "[启动] 首次运行，从 CRAWL_URLS 环境变量爬取..."
        python crawl_all.py
    else
        echo "[启动] 无 URL 配置，跳过爬取"
    fi
fi

# 2. 启动 cron
echo "[启动] 启动定时更新 (每天凌晨 2 点)"
cron

# 3. 根据模式启动
MODE="${DOC_RAG_MODE:-api}"

case "$MODE" in
    mcp-sse)
        PORT="${MCP_PORT:-9000}"
        echo "[启动] MCP SSE 模式 (端口 $PORT)"
        exec python mcp_server.py
        ;;
    mcp)
        echo "[启动] MCP stdio 模式"
        exec python mcp_server.py
        ;;
    *)
        echo "[启动] API 模式 (端口 8000)"
        exec python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
        ;;
esac
