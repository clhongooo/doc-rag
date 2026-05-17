#!/bin/bash
set -e

echo "=== doc-rag 启动 ==="

# 1. 首次爬取（如果 urls.txt 存在且数据为空）
if [ -f "urls.txt" ] && [ "$(python -c "import chromadb; c=chromadb.PersistentClient(path='data/chroma'); print(c.get_collection('doc_chunks').count())" 2>/dev/null)" = "0" ]; then
    echo "[启动] 首次运行，爬取文档..."
    python crawl_all.py --urls urls.txt
fi

# 2. 启动 cron 定时更新（增量模式，自动跳过未变化页面）
echo "[启动] 启动定时更新 (每天凌晨 2 点)"
cron

# 3. 启动 API 服务
echo "[启动] 启动 API 服务 (端口 8000)"
exec python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
