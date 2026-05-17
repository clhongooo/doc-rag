import hashlib

from .base import BaseChunker, Chunk, ChunkMeta, ChunkType


class SlidingChunker(BaseChunker):
    def __init__(self, max_tokens: int = 512, overlap_tokens: int = 64):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, doc) -> list[Chunk]:
        chunks = []
        for section in doc.sections:
            section_chunks = self._chunk_section(doc, section)
            chunks.extend(section_chunks)
        return chunks

    def _chunk_section(self, doc, section) -> list[Chunk]:
        all_text = section.text

        for table in section.tables:
            table_text = self._table_to_text(table)
            all_text += "\n\n" + table_text

        for code_block in section.code_blocks:
            code_text = f"```{code_block.language}\n{code_block.code}\n```"
            all_text += "\n\n" + code_text

        if not all_text.strip():
            return []

        return self._sliding_window(doc, section, all_text)

    def _sliding_window(self, doc, section, text: str) -> list[Chunk]:
        words = text.split()
        chunks = []
        start = 0

        while start < len(words):
            end = start + self.max_tokens
            window_words = words[start:end]
            chunk_text = " ".join(window_words)

            meta = ChunkMeta(
                section=section.heading,
                breadcrumb=section.breadcrumb,
                images=[{"src": img.src, "alt": img.alt, "caption": img.caption} for img in section.images],
                chunk_type=ChunkType.MIXED,
            )

            chunks.append(Chunk(
                id=self._generate_id(chunk_text),
                text=chunk_text,
                metadata=meta,
            ))

            start += self.max_tokens - self.overlap_tokens
            if start >= len(words):
                break

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
        return "\n".join(parts)

    def _generate_id(self, content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()[:16]
