import asyncio
import time
from contextvars import ContextVar
from datetime import datetime
from zoneinfo import ZoneInfo

from app.providers.base import ProviderError
from app.queue import locked_bucket


class DatabaseBudget:
    """Shared across workers/models/restarts. Reserve before every API attempt."""
    def __init__(self, database, settings):
        self.database, self.settings = database, settings
        self.tokens = ContextVar('gemini_reserved_tokens', default=8192)

    async def acquire(self):
        estimated_tokens = self.tokens.get()
        while True:
            now = time.time()
            pacific = datetime.fromtimestamp(now, ZoneInfo('America/Los_Angeles'))
            midnight = pacific.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            async with self.database.transaction() as session:
                bucket = await locked_bucket(session, 'gemini-project-budget')
                events = [event for event in bucket.events if event['at'] >= midnight or event['at'] > now - 60]
                if sum(event['at'] >= midnight for event in events) >= self.settings.gemini_max_rpd:
                    raise ProviderError('daily_quota', 'Gemini daily project budget exhausted.', 429, False)
                minute = [event for event in events if event['at'] > now - 60]
                if estimated_tokens > self.settings.gemini_max_tpm:
                    raise ProviderError('token_budget', 'Request exceeds configured token budget.', 422)
                if len(minute) < self.settings.gemini_max_rpm and sum(event['tokens'] for event in minute) + estimated_tokens <= self.settings.gemini_max_tpm:
                    bucket.events = [*events, {'at': now, 'tokens': estimated_tokens}]
                    return
                delay = max(.05, min(event['at'] for event in minute) + 60 - now)
            await asyncio.sleep(min(delay, 10))
