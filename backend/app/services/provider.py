import json
from dataclasses import replace

from app.config import load_settings
from app.providers.gemini import GeminiProvider
from app.services.budget import DatabaseBudget


class PilotProvider(GeminiProvider):
    def __init__(self, database, settings, semaphore, *, small=False):
        existing = load_settings()
        super().__init__(replace(existing, retries=1, requests_per_minute=settings.gemini_max_rpm,
                                 model=existing.practice_answer_model if small else existing.model))
        self.budget = DatabaseBudget(database, settings)
        self.budget_wait_seconds = 70
        self.semaphore = semaphore

    async def generate_structured(self, system_prompt, user_prompt, response_schema):
        # Conservative upper bound for textual input plus max output; includes schema overhead.
        estimate = len((system_prompt + user_prompt + json.dumps(response_schema.model_json_schema())).encode('utf-8')) + 8192
        token = self.budget.tokens.set(estimate)
        try:
            return await super().generate_structured(system_prompt, user_prompt, response_schema)
        finally:
            self.budget.tokens.reset(token)
