import json
from dataclasses import replace

from app.config import load_settings
from app.providers.gemini import GeminiProvider
from app.services.budget import DatabaseBudget
from app.models import ProviderUsage
from app.providers.base import ProviderError
import logging


class PilotProvider(GeminiProvider):
    def __init__(self, database, settings, semaphore, *, small=False):
        existing = load_settings()
        super().__init__(replace(existing, retries=1, requests_per_minute=settings.gemini_max_rpm,
                                 model=existing.practice_answer_model if small else existing.model,
                                 score_thinking_budget=getattr(settings, 'gemini_score_thinking_budget', existing.score_thinking_budget),
                                 practice_thinking_budget=getattr(settings, 'gemini_practice_thinking_budget', existing.practice_thinking_budget),
                                 feedback_language=getattr(settings, 'feedback_language', existing.feedback_language)))
        self.budget = DatabaseBudget(database, settings)
        self.database = database
        self.budget_wait_seconds = 70
        self.semaphore = semaphore

    async def generate_structured(self, system_prompt, user_prompt, response_schema, *, thinking_budget=None, model_name=None):
        # Conservative upper bound for textual input plus max output; includes schema overhead.
        estimate = len((system_prompt + user_prompt + json.dumps(response_schema.model_json_schema())).encode('utf-8')) + 8192
        token = self.budget.tokens.set(estimate)
        generation, outcome = None, 'failed'
        try:
            generation = await super().generate_structured(system_prompt, user_prompt, response_schema, thinking_budget=thinking_budget, model_name=model_name)
            outcome = 'completed'
            return generation
        except ProviderError as error:
            generation = error.generation
            outcome = error.code
            raise
        finally:
            self.budget.tokens.reset(token)
            try:
                async with self.database.transaction() as session:
                    session.add(ProviderUsage(model=model_name or self.settings.model,usage=generation.usage if generation else {},outcome=outcome))
            except Exception:
                logging.getLogger('fogwrite').error('provider_usage_write_failed')
