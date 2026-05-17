"""Web 界面 - 带 Markdown 渲染和图片显示"""
import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from pipeline import RAGPipeline

app = FastAPI()
pipeline = RAGPipeline()


class QueryRequest(BaseModel):
    question: str


@app.post("/api/query")
async def query(req: QueryRequest):
    response = await pipeline.query(req.question)
    return {
        "answer": response.answer,
        "sources": [{"url": s.url, "title": getattr(s, "title", "")} for s in response.sources],
        "images": [{"url": img.url, "alt": img.alt} for img in response.images] if response.images else [],
        "timings": response.timings,
    }


@app.get("/api/status")
async def status():
    return pipeline.status()


@app.get("/")
async def index():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text())
