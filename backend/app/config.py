from dataclasses import dataclass
from os import environ
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    model: str = "gemini-3.5-flash-lite"
    practice_answer_model: str = "gemini-3.1-flash-lite"
    concurrency: int = 1
    requests_per_minute: int = 5
    daily_budget: int = 20
    timeout: int = 45
    retries: int = 2
    web_retries: int = 4


def load_settings() -> Settings:
    values = dotenv_values(ROOT / ".env")

    def get(key, default):
        key = "GEMINI_" + key
        return environ.get(key, values.get(key)) or default

    def limit(key, default, minimum, maximum):
        value = int(get(key, default))
        if not minimum <= value <= maximum:
            raise ValueError(f"GEMINI_{key} must be between {minimum} and {maximum}")
        return value

    return Settings(
        api_key=get("API_KEY", "").strip(),
        model=get("MODEL", Settings.model).removeprefix("models/"),
        practice_answer_model=get("PRACTICE_ANSWER_MODEL", Settings.practice_answer_model).removeprefix("models/"),
        concurrency=limit("MAX_CONCURRENT_REQUESTS", 1, 1, 8),
        requests_per_minute=limit("REQUESTS_PER_MINUTE", 5, 1, 120),
        daily_budget=limit("DAILY_REQUEST_BUDGET", 20, 1, 10000),
        timeout=limit("TIMEOUT_SECONDS", 45, 1, 300),
        retries=limit("MAX_RETRIES", 2, 0, 4),
        web_retries=limit("WEB_MAX_RETRIES", 4, 0, 4),
    )
