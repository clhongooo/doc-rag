# doc-rag

通用文档 RAG 系统 —— 从 Web 文档爬取、解析、切片、索引到问答的一站式解决方案。

## 架构概览

```
URL → Crawler → Parser → Chunker → Storage (ChromaDB + SQLite)
                                         ↓
                              Retriever → Generator → Response
```

**Pipeline 流程**：

1. **Crawl** — 爬取目标网站，自动识别 SPA/静态站并选择合适的爬虫
2. **Parse** — HTML 解析，提取正文、图片、表格、代码块，按 heading 分段
3. **Chunk** — 语义切片，按段落边界分割，保留元数据（图片/表格/代码引用）
4. **Index** — 向量存储（ChromaDB）+ 结构化元数据（SQLite）
5. **Retrieve** — 语义检索 + 标题匹配重排，支持 BM25 混合检索
6. **Generate** — LLM 生成回答，自动附带来源引用和关联图片

## 项目结构

```
doc-rag/
├── run.py              # CLI 入口（ingest / query / status）
├── pipeline.py         # 端到端 RAG Pipeline
├── config.yaml         # 全局配置
├── crawl_all.py        # 批量爬取脚本
├── rebuild_index.py    # 向量索引重建（切换 embedding 模型）
│
├── crawler/            # 爬虫模块
│   ├── base.py         # 基类 + CrawlConfig/CrawlResult
│   ├── router.py       # 自动路由：SPA → Playwright，静态 → HTTP
│   ├── http_crawler.py # 异步 HTTP 爬虫（httpx）
│   ├── playwright.py   # Playwright 爬虫（支持 JS 渲染）
│   ├── cache.py        # 爬取缓存（磁盘持久化）
│   └── sitemap.py      # Sitemap 解析，自动发现子页面
│
├── parser/             # HTML 解析模块
│   ├── html_parser.py  # 主解析器：噪声清理 + heading 分段
│   └── extractor.py    # 图片/表格/代码块提取
│
├── chunker/            # 切片模块
│   ├── base.py         # Chunk 数据模型（ChunkType: text/table/code/mixed）
│   ├── semantic.py     # 语义切片：按段落+表格+代码分别切片
│   └── sliding.py      # 滑动窗口切片（备选）
│
├── storage/            # 存储模块
│   ├── vector_store.py # ChromaDB 向量存储（cosine 相似度）
│   ├── embedding.py    # 中文 Embedding（text2vec-base-chinese）
│   └── metadata_db.py  # SQLite 元数据存储
│
├── retriever/          # 检索模块
│   ├── semantic.py     # 语义检索 + 标题匹配重排
│   └── hybrid.py       # 混合检索（向量 + BM25 加权融合）
│
├── generator/          # 生成模块
│   ├── base.py         # LLM Provider 抽象基类
│   ├── factory.py      # Provider 工厂（Anthropic / OpenAI）
│   ├── anthropic.py    # Anthropic Claude 实现
│   ├── openai.py       # OpenAI 兼容实现（支持本地 llama-server）
│   ├── llm.py          # Generator 主逻辑
│   ├── prompt.py       # System Prompt + 上下文构建
│   └── formatter.py    # 响应格式化（图片/表格/代码/来源提取）
│
├── api/                # Web 服务
│   └── server.py       # FastAPI 服务（REST API + Web UI）
│
├── models/             # 本地 Embedding 模型存放目录
│   └── text2vec-base-chinese/
│
└── data/               # 运行时数据
    ├── chroma/         # 向量数据库
    ├── sqlite/         # 元数据数据库
    └── images/         # 提取的图片
```

## 快速开始

### 安装

```bash
# Python >= 3.9
pip install -e .

# 可选：Playwright（SPA 站点支持）
pip install -e ".[browser]"
playwright install chromium
```

### 配置

编辑 `config.yaml`，主要配置项：

```yaml
# LLM 后端（支持 Anthropic Claude 或本地 OpenAI 兼容服务）
generator:
  provider: "openai"          # anthropic | openai
  model: "qwen3-8b"           # 本地模型
  base_url: "http://localhost:8080/v1"  # llama-server 地址

# 本地 Embedding 模型
storage:
  embedding_model: "models/text2vec-base-chinese"
```

### 使用

```bash
# 1. 爬取并索引文档
python run.py ingest https://cloud.tencent.com/document/product/548/61710

# 2. 查询问答
python run.py query "如何调用推送接口？"

# 3. 查看索引状态
python run.py status
```

### Web API

```bash
# 启动 API 服务
uvicorn api.server:app --host 0.0.0.0 --port 8000

# 查询接口
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "如何接入推送？"}'

# 状态接口
curl http://localhost:8000/api/status
```

浏览器访问 `http://localhost:8000` 即可使用 Web UI。

## 核心特性

### 智能爬虫路由

系统自动检测目标站点类型，选择最优爬虫策略：

- **静态站点** → `HTTPCrawler`（httpx 异步并发，速度更快）
- **SPA 站点** → `PlaywrightCrawler`（JS 渲染，兼容 React/Vue/Next.js 等）

检测信号包括 `data-reactroot`、`__NEXT_DATA__`、`__NUXT__` 等框架特征。

### 语义切片

`SemanticChunker` 按文档结构智能切片，将内容分为四种类型：

| 类型 | 说明 |
|------|------|
| `TEXT` | 纯文本段落，按 token 数限制分割 |
| `TABLE` | 表格数据，转为 Markdown 格式 |
| `CODE` | 代码块，保留语言标注 |
| `MIXED` | 混合内容（段落 + 表格/代码） |

每个 chunk 自动附加文档标题前缀，提升检索匹配质量。

### 中文语义检索

- **Embedding**: `text2vec-base-chinese`（本地推理，无需 API 调用）
- **检索策略**: 语义向量检索 + 标题关键词匹配，双重召回后重排
- **重排逻辑**: 基于标题匹配度提升排序，API 相关查询自动加权技术文档

### 多 LLM 后端

| Provider | 说明 |
|----------|------|
| `anthropic` | Anthropic Claude API |
| `openai` | OpenAI 兼容协议，支持本地部署（llama-server、vLLM 等） |

通过 `config.yaml` 的 `generator.provider` 切换，无需改代码。

## 工具脚本

| 脚本 | 用途 |
|------|------|
| `crawl_all.py` | 批量爬取整个文档目录，自动发现子页面 |
| `rebuild_index.py` | 从旧 embedding 模型迁移到新模型（如英文→中文） |
| `test_cache.py` | 爬取缓存测试 |
| `count_pages.py` | 统计已爬取页面数 |

## 技术栈

- **爬虫**: httpx + BeautifulSoup4 / Playwright
- **解析**: BeautifulSoup4 + lxml + trafilatura
- **切片**: 自定义语义切片器
- **向量存储**: ChromaDB（cosine 相似度）
- **Embedding**: sentence-transformers（text2vec-base-chinese）
- **检索**: 向量语义 + BM25 关键词（rank-bm25）
- **LLM**: Anthropic Claude / OpenAI 兼容 API
- **Web 服务**: FastAPI + uvicorn
- **元数据**: SQLite
