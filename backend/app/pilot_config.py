"""Deployment configuration; the existing local research demo remains separate."""
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PilotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', case_sensitive=False)
    app_env: Literal['development', 'test', 'production'] = 'development'
    database_url: SecretStr = SecretStr('sqlite+aiosqlite:///./results/pilot.sqlite3')
    migration_database_url: SecretStr | None = None
    frontend_origin: str = 'http://localhost:5173'
    clerk_issuer: str = ''
    clerk_publishable_key: str = ''
    clerk_jwt_key: str = ''  # Optional public PEM for networkless verification.
    clerk_audience: str = ''
    worker_enabled: bool = True
    worker_count: int = Field(2, ge=1, le=4)
    worker_poll_seconds: float = Field(1, ge=.05, le=30)
    worker_lease_seconds: int = Field(120, ge=10, le=900)
    job_timeout_seconds: int = Field(600, ge=10, le=1800)
    job_max_attempts: int = Field(3, ge=1, le=5)
    daily_submission_limit: int = Field(5, ge=1, le=100)
    daily_practice_limit: int = Field(30, ge=1, le=200)
    enable_practice_gen: bool = True
    practice_items_per_set: int = Field(4, ge=1, le=5)
    gemini_max_rpm: int = Field(5, ge=1, le=1000)
    gemini_api_key: SecretStr = SecretStr('')
    gemini_max_tpm: int = Field(100000, ge=1000)
    gemini_max_rpd: int = Field(200, ge=1)
    gemini_max_concurrent: int = Field(2, ge=1, le=4)
    retention_days: int = Field(30, ge=1, le=365)
    max_queued_jobs: int = Field(200, ge=40, le=5000)
    privacy_version: str = 'pilot-2026-11-v1'
    gemini_data_policy: Literal['unconfirmed', 'paid_no_training', 'free_product_improvement'] = 'unconfirmed'

    @property
    def origins(self):
        return [self.frontend_origin.rstrip('/')]

    @model_validator(mode='after')
    def deployment_checks(self):
        origin = urlparse(self.frontend_origin)
        if origin.scheme not in ('http', 'https') or not origin.netloc or origin.path not in ('', '/'):
            raise ValueError('FRONTEND_ORIGIN must be one exact origin without a path.')
        if self.clerk_issuer:
            issuer = urlparse(self.clerk_issuer)
            if issuer.scheme != 'https' or not issuer.hostname or issuer.path not in ('', '/'):
                raise ValueError('CLERK_ISSUER must be the HTTPS issuer from your Clerk instance.')
        if self.app_env == 'production':
            if not self.database_url.get_secret_value().startswith(('postgresql://', 'postgresql+asyncpg://')):
                raise ValueError('Production requires PostgreSQL.')
            if origin.scheme != 'https' or origin.hostname in ('localhost', '127.0.0.1'):
                raise ValueError('Production requires an HTTPS frontend origin.')
            if not self.clerk_issuer or not self.clerk_publishable_key.startswith('pk_live_'):
                raise ValueError('Production requires a live Clerk instance and publishable key.')
            if self.gemini_data_policy == 'unconfirmed':
                raise ValueError('Confirm GEMINI_DATA_POLICY before opening the production pilot.')
            if not self.gemini_api_key.get_secret_value():
                raise ValueError('Production requires GEMINI_API_KEY.')
        return self
