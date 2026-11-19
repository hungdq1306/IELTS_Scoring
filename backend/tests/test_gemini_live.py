import asyncio
import os

import pytest

from app.config import load_settings
from app.grading.schemas import GradeRequest
from app.grading.task2 import grade_essay
from app.providers.gemini import GeminiProvider


@pytest.mark.live
@pytest.mark.skipif(os.getenv("GEMINI_LIVE_TEST") != "1", reason="Set GEMINI_LIVE_TEST=1 to spend Gemini quota.")
def test_real_gemini():
    async def run():
        settings = load_settings()
        provider = GeminiProvider(settings)
        try:
            assert settings.model in await provider.available_models()
            result, _ = await grade_essay(
                GradeRequest(prompt="Should cities invest more in public transport? Explain your position.",
                             essay="Cities should invest in buses because many workers cannot afford cars. Frequent bus services can connect those workers to workplaces across the city."),
                provider,
            )
            assert result.model == settings.model
            assert 0 <= result.estimated_overall_band <= 9
        finally:
            await provider.close()
    asyncio.run(run())
