from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from app.grading.schemas import Attempt


@dataclass(frozen=True)
class Generation:
    raw: str
    model: str
    version: str | None
    latency_ms: int
    usage: dict[str, int]
    attempts: list[Attempt]


@dataclass(eq=False)
class ProviderError(Exception):
    code: str
    message: str
    status: int = 502
    retryable: bool = False
    retry_after: float | None = None
    api_code: int | None = None
    attempts: list[Attempt] = field(default_factory=list)
    generation: Generation | None = None

    def __str__(self) -> str:
        return self.message


class LLMProvider(Protocol):
    async def generate_structured(
        self, system_prompt: str, user_prompt: str, response_schema: type[BaseModel]
    ) -> Generation: ...
