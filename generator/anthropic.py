import anthropic
from typing import Optional

from .base import LLMProvider, LLMResponse, TokenUsage


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.AsyncAnthropic(**kwargs)
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResponse:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        response = await self.client.messages.create(**kwargs)

        if response is None:
            raise RuntimeError(
                f"LLM API 返回空响应，请检查 api_key 和 base_url 配置。"
                f"\nmodel={self.model}, base_url={self.client.base_url}"
            )

        if not response.content:
            raise RuntimeError(
                f"LLM API 返回空 content，stop_reason={response.stop_reason}"
            )

        if response.stop_reason == "content_filter":
            # 内容过滤时返回兜底提示，不崩溃
            return LLMResponse(
                content="抱歉，由于内容安全策略限制，暂时无法回答该问题。请尝试换一种方式提问。",
                model=self.model,
                usage=TokenUsage(input_tokens=0, output_tokens=0),
            )

        if response.usage is None:
            raise RuntimeError(
                f"LLM API 返回空 usage，response.stop_reason={response.stop_reason}"
            )

        # 跳过 ThinkingBlock，取第一个 TextBlock
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text
                break

        return LLMResponse(
            content=text,
            model=response.model,
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )
