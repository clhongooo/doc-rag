FROM python:3.11-slim

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl gnupg cron \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器
RUN playwright install chromium

# 复制项目代码（包含 models/ 目录）
COPY . .

# 创建数据目录
RUN mkdir -p data/chroma data/sqlite data/images .cache /var/log

# 如果 models/ 不存在则下载 embedding 模型（390MB）
RUN if [ ! -d "models/text2vec-base-chinese" ]; then \
        echo "下载 embedding 模型..."; \
        python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('shibing624/text2vec-base-chinese')"; \
    fi

# 设置定时任务
COPY crontab /etc/cron.d/doc-rag-cron
RUN chmod 0644 /etc/cron.d/doc-rag-cron && crontab /etc/cron.d/doc-rag-cron

# 启动脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
