from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Image:
    src: str
    alt: str = ""
    caption: str = ""


@dataclass
class Table:
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    caption: str = ""


@dataclass
class CodeBlock:
    language: str = ""
    code: str = ""


@dataclass
class Section:
    heading: str
    level: int
    text: str = ""
    images: list[Image] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    code_blocks: list[CodeBlock] = field(default_factory=list)
    breadcrumb: list[str] = field(default_factory=list)


@dataclass
class DocContent:
    url: str
    title: str
    sections: list[Section] = field(default_factory=list)


class BaseParser(ABC):
    @abstractmethod
    def parse(self, url: str, title: str, html: str) -> DocContent:
        ...
