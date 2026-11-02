from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MediCode"
    app_env: str = "development"
    debug: bool = Field(default=False, validation_alias="APP_DEBUG")
    database_url: str = "postgresql+asyncpg://medicode:medicode@localhost:5432/medicode"
    auth_secret_key: str = "change-this-development-secret-before-deployment"
    auth_token_expire_minutes: int = 15
    auth_refresh_token_expire_days: int = 14

    # Redis & Asynchronous Worker Queue
    redis_url: str = "redis://localhost:6379/0"
    arq_queue_name: str = "medicode:submissions"
    arq_max_jobs: int = 10
    worker_concurrency: int = 4

    # Code Execution Provider Settings
    execution_provider: Literal["judge0_self", "judge0_rapidapi"] = "judge0_self"
    judge0_url: str = "http://localhost:2358"
    judge0_auth_header: str = "X-Auth-Token"
    judge0_auth_token: str = "medicode-judge0-secret-token"
    judge0_rapidapi_key: str = ""
    judge0_rapidapi_host: str = "judge0-ce.p.rapidapi.com"
    judge0_poll_interval_sec: float = 0.1
    judge0_poll_timeout_sec: float = 15.0
    python_language_id: int = 71  # Python 3 in standard Judge0 CE

    # Default Resource Limits for Python Execution
    default_cpu_time_limit_sec: float = 1.0
    default_wall_time_limit_sec: float = 3.0
    default_memory_limit_kb: int = 128_000   # 128 MB
    default_stack_limit_kb: int = 64_000     # 64 MB
    default_max_processes: int = 30
    default_max_file_size_kb: int = 1024     # 1 MB
    default_enable_network: bool = False
    max_source_code_bytes: int = 65_536      # 64 KiB
    max_output_length_chars: int = 2048      # 2 KB sanitization truncate cap

    # Rate Limiting
    rate_limit_submission_requests: int = 20
    rate_limit_submission_window_sec: int = 60
    rate_limit_burst_window_sec: int = 3
    rate_limit_run_requests: int = 10
    rate_limit_run_window_sec: int = 60

    # Caching & Cost Optimization
    cache_results_enabled: bool = True
    cache_results_ttl_sec: int = 3600
    early_exit_on_failure: bool = False

    # Production Server
    web_concurrency: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("postgresql+asyncpg://"):
            return self.database_url
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        raise ValueError("DATABASE_URL must use the postgresql:// scheme")

    @property
    def sync_database_url(self) -> str:
        if self.database_url.startswith("postgresql+asyncpg://"):
            return self.database_url.replace("+asyncpg", "+psycopg2", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        raise ValueError("DATABASE_URL must use the postgresql:// scheme")


@lru_cache
def get_settings() -> Settings:
    return Settings()
