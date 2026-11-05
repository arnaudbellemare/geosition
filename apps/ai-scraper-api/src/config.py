from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Provider API keys
    openai_api_key: str = ""
    perplexity_api_key: str = ""
    gemini_api_key: str = ""
    grok_api_key: str = ""

    # Service config
    admin_key: str = "change-me-in-production"
    db_path: str = "data/scraper.db"
    default_monthly_limit: int = 1000
    cors_origins: List[str] = Field(default=["*"])

    # Optional: override models per provider
    openai_model: str = "gpt-4o"
    perplexity_model: str = "sonar-pro"
    gemini_model: str = "gemini-2.0-flash"
    grok_model: str = "grok-3"


settings = Settings()
