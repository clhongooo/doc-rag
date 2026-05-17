from dataclasses import dataclass

from .base import LLMResponse
from .factory import GeneratorConfig, create_llm_provider
from .formatter import RAGResponse, format_response
from .prompt import SYSTEM_PROMPT, build_context, build_user_message


@dataclass
class Generator:
    config: GeneratorConfig

    def __post_init__(self):
        self.provider = create_llm_provider(self.config)

    async def generate(self, query: str, chunks: list[dict], metadata_db) -> RAGResponse:
        context = build_context(chunks, metadata_db)
        user_message = build_user_message(query, context)

        llm_response = await self.provider.chat(
            messages=[{"role": "user", "content": user_message}],
            system=SYSTEM_PROMPT,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )

        return format_response(llm_response.content, chunks, metadata_db, llm_response)
