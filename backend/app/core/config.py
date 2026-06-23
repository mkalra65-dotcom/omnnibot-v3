from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OmniBot V3 API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    supabase_url: str = Field(default="")
    supabase_anon_key: str = Field(default="")
    supabase_service_role_key: str = Field(default="")

    whatsapp_verify_token: str = Field(default="")
    whatsapp_app_secret: str = Field(default="")
    whatsapp_graph_api_version: str = Field(default="v20.0")

    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4.1-mini")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
