from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: TokenUsage


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        ...
