import os
from dataclasses import dataclass
from typing import Optional

from .anthropic import AnthropicProvider
from .base import LLMProvider
from .openai import OpenAIProvider


@dataclass
class GeneratorConfig:
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.3
    api_key: Optional[str] = None
    base_url: Optional[str] = None


def create_llm_provider(config: GeneratorConfig) -> LLMProvider:
    api_key = config.api_key or os.getenv("LLM_API_KEY")
    base_url = config.base_url

    if config.provider == "anthropic":
        return AnthropicProvider(api_key=api_key, base_url=base_url, model=config.model)
    elif config.provider == "openai":
        return OpenAIProvider(api_key=api_key, base_url=base_url, model=config.model)
    else:
        raise ValueError(f"Unknown provider: {config.provider}")
