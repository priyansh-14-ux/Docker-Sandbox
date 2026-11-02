from functools import lru_cache

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
