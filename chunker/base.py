from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class ChunkType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    CODE = "code"
    MIXED = "mixed"


@dataclass
class ChunkMeta:
    url: str = ""
    title: str = ""
    section: str = ""
    breadcrumb: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    code_blocks: list[dict] = field(default_factory=list)
    chunk_type: ChunkType = ChunkType.TEXT


@dataclass
class Chunk:
    id: str = ""
    text: str = ""
    metadata: ChunkMeta = field(default_factory=ChunkMeta)


class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, doc) -> list[Chunk]:
        ...
