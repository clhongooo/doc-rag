import hashlib

from .base import BaseChunker, Chunk, ChunkMeta, ChunkType


class SemanticChunker(BaseChunker):
    def __init__(self, max_tokens: int = 512, max_chunks_per_doc: int = 50):
        self.max_tokens = max_tokens
        self.max_chunks_per_doc = max_chunks_per_doc

    def chunk(self, doc) -> list[Chunk]:
        chunks = []

        # 跳过纯表格页面（如词汇表）
        total_tables = sum(len(s.tables) for s in doc.sections)
        if total_tables > 20:
            return chunks

        for section in doc.sections:
            section_chunks = self._chunk_section(doc, section)
            chunks.extend(section_chunks)

            if len(chunks) >= self.max_chunks_per_doc:
                chunks = chunks[:self.max_chunks_per_doc]
                break

        return chunks

    def _chunk_section(self, doc, section) -> list[Chunk]:
        text_chunks = self._chunk_text(section)

        table_chunks = self._chunk_tables(doc, section)
        code_chunks = self._chunk_code(doc, section)

        all_chunks = text_chunks + table_chunks + code_chunks

        if len(all_chunks) > 1:
            for chunk in all_chunks:
                chunk.metadata.chunk_type = ChunkType.MIXED

        return all_chunks

    def _chunk_text(self, section) -> list[Chunk]:
        if not section.text.strip():
            return []

        words = section.text.split()
        chunks = []
        current_words = []
        current_len = 0

        for word in words:
            word_tokens = len(word) // 4 + 1
            if current_len + word_tokens > self.max_tokens and current_words:
                chunks.append(self._make_text_chunk(section, " ".join(current_words)))
                current_words = []
                current_len = 0

            current_words.append(word)
            current_len += word_tokens

        if current_words:
            chunks.append(self._make_text_chunk(section, " ".join(current_words)))

        return chunks

    def _make_text_chunk(self, section, text: str) -> Chunk:
        # 在 chunk 文本中加入文档标题，提升 embedding 匹配质量
        title = section.breadcrumb[0] if section.breadcrumb else ""
        prefix = f"[{title}] " if title else ""
        content = f"{prefix}## {section.heading}\n\n{text}" if section.heading else f"{prefix}{text}"
        meta = ChunkMeta(
            section=section.heading,
            breadcrumb=section.breadcrumb,
            images=[{"src": img.src, "alt": img.alt, "caption": img.caption} for img in section.images],
            chunk_type=ChunkType.TEXT,
        )
        return Chunk(
            id=self._generate_id(content),
            text=content,
            metadata=meta,
        )

    def _chunk_tables(self, doc, section) -> list[Chunk]:
        chunks = []
        for table in section.tables:
            table_text = self._table_to_text(table)
            meta = ChunkMeta(
                section=section.heading,
                breadcrumb=section.breadcrumb,
                tables=[{
                    "headers": table.headers,
                    "rows": table.rows,
                    "caption": table.caption,
                }],
                chunk_type=ChunkType.TABLE,
            )
            chunks.append(Chunk(
                id=self._generate_id(table_text),
                text=table_text,
                metadata=meta,
            ))
        return chunks

    def _table_to_text(self, table) -> str:
        parts = []
        if table.caption:
            parts.append(f"表格说明：{table.caption}")

        if table.headers:
            parts.append(" | ".join(table.headers))
            parts.append("-" * 40)

        for row in table.rows[:20]:
            parts.append(" | ".join(row))

        if len(table.rows) > 20:
            parts.append(f"... 共 {len(table.rows)} 行")

        return "\n".join(parts)

    def _chunk_code(self, doc, section) -> list[Chunk]:
        chunks = []
        for code_block in section.code_blocks:
            code_text = f"```{code_block.language}\n{code_block.code}\n```"
            meta = ChunkMeta(
                section=section.heading,
                breadcrumb=section.breadcrumb,
                code_blocks=[{
                    "language": code_block.language,
                    "code": code_block.code,
                }],
                chunk_type=ChunkType.CODE,
            )
            chunks.append(Chunk(
                id=self._generate_id(code_text),
                text=code_text,
                metadata=meta,
            ))
        return chunks

    def _generate_id(self, content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()[:16]
