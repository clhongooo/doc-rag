from dataclasses import dataclass, field


@dataclass
class ImageRef:
    url: str
    alt: str = ""
    caption: str = ""


@dataclass
class TableData:
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    caption: str = ""


@dataclass
class CodeData:
    language: str = ""
    code: str = ""


@dataclass
class SourceRef:
    url: str
    title: str = ""
    section: str = ""


@dataclass
class RAGResponse:
    answer: str
    images: list[ImageRef] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    code_blocks: list[CodeData] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)


def format_response(answer: str, chunks: list[dict], metadata_db, llm_response) -> RAGResponse:
    images = []
    tables = []
    code_blocks = []
    sources = []

    seen_sources = set()
    for chunk in chunks:
        url = chunk["metadata"].get("url", "")
        if url and url not in seen_sources:
            sources.append(SourceRef(
                url=url,
                title=chunk["metadata"].get("title", ""),
                section=chunk["metadata"].get("section", ""),
            ))
            seen_sources.add(url)

        meta = metadata_db.get(chunk["id"])
        if not meta:
            continue

        for img in meta.get("images", []):
            img_ref = ImageRef(url=img["src"], alt=img.get("alt", ""), caption=img.get("caption", ""))
            if not any(i.url == img_ref.url for i in images):
                images.append(img_ref)

        for table in meta.get("tables", []):
            tables.append(TableData(
                headers=table.get("headers", []),
                rows=table.get("rows", []),
                caption=table.get("caption", ""),
            ))

        for code in meta.get("code_blocks", []):
            code_blocks.append(CodeData(
                language=code.get("language", ""),
                code=code.get("code", ""),
            ))

    return RAGResponse(
        answer=answer,
        images=images,
        tables=tables,
        code_blocks=code_blocks,
        sources=sources,
        model=llm_response.model,
        usage={
            "input_tokens": llm_response.usage.input_tokens,
            "output_tokens": llm_response.usage.output_tokens,
        },
    )
