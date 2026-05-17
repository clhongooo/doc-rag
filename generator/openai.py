import openai
from typing import Optional

from .base import LLMProvider, LLMResponse, TokenUsage


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "gpt-4o"):
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self.client = openai.AsyncOpenAI(**kwargs)
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=full_messages,
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage=TokenUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
            ),
        )
