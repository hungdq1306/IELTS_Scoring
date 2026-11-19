import argparse
import asyncio
import sqlite3
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from random import uniform
from time import perf_counter, time
from zoneinfo import ZoneInfo

import httpx
from google import genai
from google.genai import errors, types

from app.config import ROOT, Settings, load_settings
from app.grading.schemas import Attempt, DetailedModelGrade
from app.providers.base import Generation, ProviderError

FREE_MODELS = {"gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite"}


def retry_after_seconds(headers) -> float | None:
    value = (headers or {}).get("retry-after")
    if value is None:
        return None
    try:
        return max(0, float(value))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def classify_error(exc: Exception) -> ProviderError:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return ProviderError("timeout", "Gemini timed out.", 504, True)
    if isinstance(exc, httpx.TransportError):
        return ProviderError("connection_error", "Cannot connect to Gemini. Check network access and DNS.", 503, True)
    code = exc.code
    response = getattr(exc, "response", None)
    after = retry_after_seconds(getattr(response, "headers", None))
    if code == 429:
        details = getattr(exc, "details", None)
        if isinstance(details, dict):
            details = details.get("error", details).get("details", [])
        details = [item for item in (details or []) if isinstance(item, dict)]
        for item in details:
            duration = str(item.get("retryDelay", ""))
            if duration.endswith("s"):
                try:
                    after = max(after or 0, float(duration[:-1]))
                except ValueError:
                    pass
        quota_items = [item for item in details if item.get("@type", "").endswith("QuotaFailure")]
        quota_signal = f"{getattr(exc, 'message', '')} {quota_items}".lower()
        if any(marker in quota_signal for marker in ("perday", "per_day", "per day", "daily", "limit: 0", "'quotavalue': '0'", "'quotavalue': 0")):
            return ProviderError("daily_quota", "Gemini daily quota is exhausted or this project has zero quota for the model. Check Google AI Studio.", 429, api_code=code)
        return ProviderError("rate_limited", "Gemini rate limit reached. Try again later and check the project limits.", 429, True, after, code)
    if code in (408, 500, 502, 503, 504):
        return ProviderError("upstream_unavailable", "Gemini is temporarily unavailable.", 503, True, after, code)
    if code == 400 and any(word in str(exc.message).lower() for word in ("schema", "constraint")):
        return ProviderError("gemini_configuration", "Gemini rejected the output schema (HTTP 400).",
                             503, api_code=code)
    if code in (400, 401, 403, 404):
        return ProviderError("gemini_configuration", "Gemini rejected the request. Check model access, key, region, and API configuration.", 503, api_code=code)
    return ProviderError("gemini_error", "Gemini returned an unexpected API error.", api_code=code)


class RequestBudget:
    """Atomic quota reservations shared by local HTTP and CLI processes."""

    def __init__(self, path: Path, settings: Settings):
        self.path, self.settings = path, settings

    def reserve(self) -> float:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS requests (reserved REAL NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            now = time()
            today = datetime.fromtimestamp(now, ZoneInfo("America/Los_Angeles"))
            midnight = today.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            db.execute("DELETE FROM requests WHERE reserved < ?", (min(midnight, now - 60),))
            used = db.execute("SELECT count(*) FROM requests WHERE reserved >= ?", (midnight,)).fetchone()[0]
            if used >= self.settings.daily_budget:
                raise ProviderError("local_daily_budget", "Local Gemini daily request budget reached.", 429)
            previous = db.execute("SELECT max(reserved) FROM requests").fetchone()[0]
            wait = max(0, previous + 60 / self.settings.requests_per_minute - now) if previous else 0
            if wait == 0:
                db.execute("INSERT INTO requests VALUES (?)", (now,))
            return wait

    async def acquire(self) -> None:
        while wait := await asyncio.to_thread(self.reserve):
            await asyncio.sleep(wait)


def _scores_last(schema: dict) -> dict:
    """Order JSON Schema properties so evidence and feedback precede final numeric scores."""
    for key in ("properties", "required"):
        container = schema.get(key)
        if isinstance(container, dict) and "criterion_scores" in container:
            ordered = {k: v for k, v in container.items() if k != "criterion_scores"}
            ordered["criterion_scores"] = container["criterion_scores"]
            schema[key] = ordered
        elif isinstance(container, list) and "criterion_scores" in container:
            schema[key] = [k for k in container if k != "criterion_scores"] + ["criterion_scores"]
    return schema


def gemini_schema(response_schema):
    schema = response_schema.model_json_schema()
    if response_schema.__module__.startswith("app.practice."):
        return compact_schema(schema, preserve_enums=True)
    if response_schema is DetailedModelGrade:
        return _scores_last(compact_schema(schema, preserve_enums=True))
    for definition in schema.get("$defs", {}).values():
        for field in definition.get("properties", {}).values():
            if field.get("multipleOf") == 0.5 and field.get("minimum") == 0 and field.get("maximum") == 9:
                del field["multipleOf"]
                field["enum"] = [index / 2 for index in range(19)]
    return _scores_last(schema)


def compact_schema(schema, preserve_enums=False):
    """Keep detailed output's shape on Gemini; enforce full constraints with Pydantic."""
    result = {key: schema[key] for key in ("type", "$ref") if key in schema}
    if preserve_enums and "enum" in schema:
        result["enum"] = schema["enum"]
    for key in ("$defs", "properties"):
        if key in schema:
            result[key] = {name: compact_schema(value, preserve_enums) for name, value in schema[key].items()}
    if "items" in schema:
        result["items"] = compact_schema(schema["items"], preserve_enums)
    if "anyOf" in schema:
        result["anyOf"] = [compact_schema(item, preserve_enums) for item in schema["anyOf"]]
    if "required" in schema:
        result["required"] = schema["required"]
    return result


class GeminiProvider:
    def __init__(self, settings: Settings, budget_path: Path = ROOT / "results" / "_quota.sqlite3", client=None, generation_budget: int | None = None):
        self.settings = settings
        self.client = client
        self.generation_budget = generation_budget
        self.budget = RequestBudget(budget_path, settings)
        self.semaphore = asyncio.Semaphore(settings.concurrency)

    def _client(self):
        if not self.settings.api_key:
            raise ProviderError("missing_api_key", "Set GEMINI_API_KEY in the project .env and restart the backend.", 503)
        if self.settings.model not in FREE_MODELS:
            raise ProviderError("model_not_allowed", "Configure a documented free-tier Flash-Lite model.", 503)
        if self.client is None:
            self.client = genai.Client(
                api_key=self.settings.api_key, vertexai=False,
                http_options=types.HttpOptions(
                    timeout=self.settings.timeout * 1000,
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
        return self.client

    async def available_models(self) -> list[str]:
        try:
            client = self._client()
            async with asyncio.timeout(self.settings.timeout):
                models = await client.aio.models.list(config={"page_size": 100})
                return sorted(
                    name for item in [item async for item in models]
                    if (name := (item.name or "").removeprefix("models/")) in FREE_MODELS
                    and "generateContent" in (item.supported_actions or [])
                )
        except (errors.APIError, httpx.TransportError, TimeoutError) as exc:
            raise classify_error(exc) from exc

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aio.aclose()
            self.client.close()

    async def generate_structured(self, system_prompt, user_prompt, response_schema) -> Generation:
        client = self._client()
        config = types.GenerateContentConfig(
            system_instruction=system_prompt, response_mime_type="application/json",
            response_json_schema=gemini_schema(response_schema),
            temperature=0, max_output_tokens=8192,
        )
        attempts = []
        budget_wait = max(30, 60 / self.settings.requests_per_minute + 5)
        async with self.semaphore:
            for attempt_no in range(self.settings.retries + 1):
                try:
                    if self.generation_budget is not None and self.generation_budget <= 0:
                        raise ProviderError('request_budget', 'Benchmark request budget reached.', 429)
                    await asyncio.wait_for(self.budget.acquire(), timeout=budget_wait)
                    if self.generation_budget is not None:
                        self.generation_budget -= 1
                except TimeoutError as exc:
                    error = ProviderError("local_rate_limit", "Local request pacing is busy. Try again shortly.", 429, retryable=True)
                    error.attempts = attempts
                    raise error from exc
                except ProviderError as exc:
                    exc.attempts = attempts
                    raise
                started = perf_counter()
                try:
                    async with asyncio.timeout(self.settings.timeout):
                        response = await client.aio.models.generate_content(
                            model=self.settings.model, contents=user_prompt, config=config,
                        )
                except (errors.APIError, httpx.TransportError, TimeoutError) as exc:
                    elapsed = round((perf_counter() - started) * 1000)
                    failure = classify_error(exc)
                    attempts.append(Attempt(status=failure.code, api_code=failure.api_code, latency_ms=elapsed))
                    delay = max(failure.retry_after or 0, min(30, 5 * 2**attempt_no) + uniform(0, 0.5))
                    if not failure.retryable or attempt_no == self.settings.retries or delay > 60:
                        if failure.code == "upstream_unavailable":
                            failure.message = (f"Gemini is still unavailable after {len(attempts)} attempts. "
                                               "Your essay is preserved. Please try again in a few minutes.")
                        failure.attempts = attempts
                        raise failure from exc
                    await asyncio.sleep(delay)
                    continue
                elapsed = round((perf_counter() - started) * 1000)
                usage = {key: value for key, value in (
                    response.usage_metadata.model_dump().items() if response.usage_metadata else []
                ) if type(value) is int}
                reason = str(response.candidates[0].finish_reason or "STOP") if response.candidates else "NO_CANDIDATE"
                usable = reason in ("FinishReason.STOP", "STOP") and bool(response.text)
                status = "ok" if usable else "incomplete_output"
                attempts.append(Attempt(status=status, latency_ms=elapsed, usage=usage))
                generation = Generation(response.text or "", self.settings.model, response.model_version, elapsed, usage, attempts)
                if not usable:
                    raise ProviderError(status, f"Gemini returned incomplete output ({reason}).",
                                        attempts=attempts, generation=generation)
                return generation
        raise RuntimeError("Unreachable retry state")


async def verify_model(settings: Settings) -> None:
    provider = GeminiProvider(settings)
    try:
        available = await provider.available_models()
        print(f"Configured: {settings.model}\nAvailable free-tier candidates: {', '.join(available) or 'none'}")
        if settings.model not in available:
            raise ProviderError("model_unavailable", "The configured model is unavailable to this API key.")
        print("Model access verified. Check the Free Tier billing and quota in AI Studio before grading.")
    finally:
        await provider.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Gemini model availability for the configured key")
    parser.parse_args()
    try:
        asyncio.run(verify_model(load_settings()))
    except ProviderError as exc:
        parser.exit(1, f"{exc.code}: {exc.message}\n")
