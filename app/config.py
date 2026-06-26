"""Application configuration loaded from env / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


MODEL_OPTIONS: dict[str, str] = {
    "claude-opus-4-8": "Claude Opus 4.8",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-haiku-4-5": "Claude Haiku 4.5",
    "gpt-5.5": "GPT-5.5",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Missing values stop application startup. There is no provider API fallback.
    lite_llm_key: str = Field(min_length=1)
    lite_llm_base_url: str = Field(min_length=1)
    secret_key: str = "dev-secret-zmien-mnie"

    admin_username: str = "admin"
    admin_password: str = "admin"

    model: str = "claude-opus-4-8"
    scraper_mode: str = "auto"  # auto | httpx | playwright

    data_dir: str = "./data"
    max_images: int = 12

    public_base_url: str = "http://localhost:8000"

    @property
    def db_path(self) -> str:
        return f"{self.data_dir.rstrip('/')}/mieszkania.sqlite3"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
