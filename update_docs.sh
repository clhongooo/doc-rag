#!/bin/bash
# 定时更新文档脚本
# 用法: ./update_docs.sh [URLs文件]
set -e

cd /app

URLS_FILE="${1:-urls.txt}"

if [ ! -f "$URLS_FILE" ]; then
    echo "[$(date)] 错误: $URLS_FILE 不存在"
    exit 1
fi

echo "[$(date)] 开始更新文档..."
python crawl_all.py --urls "$URLS_FILE"
echo "[$(date)] 更新完成"
