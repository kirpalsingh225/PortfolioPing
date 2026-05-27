from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    api_secret: str = "dummy-api-secret-change-me"
    token_encryption_key: str = "dummy-fernet-key-change-me"

    redis_url: str = "redis://localhost:6379/0"

    supabase_url: str = "https://dummy-project.supabase.co"
    supabase_service_role_key: str = "dummy-service-role-key"

    whatsapp_verify_token: str = "dummy-whatsapp-verify-token"
    whatsapp_app_secret: str = "dummy-whatsapp-app-secret"
    whatsapp_access_token: str = "dummy-whatsapp-access-token"
    whatsapp_phone_number_id: str = "dummy-phone-number-id"
    whatsapp_api_version: str = "v21.0"

    broker_provider: str = "zerodha"
    zerodha_api_key: str = "dummy-zerodha-api-key"
    zerodha_api_secret: str = "dummy-zerodha-api-secret"
    zerodha_redirect_url: str = "http://localhost:8000/auth/zerodha/callback"

    llm_provider: str = "openrouter"
    openrouter_api_key: str = "dummy-openrouter-api-key"
    openrouter_model: str = "openai/gpt-oss-120b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gpt-oss:120b-cloud"
    ollama_temperature: float = 0.2

    max_raw_messages: int = Field(default=10, ge=4)
    summary_trigger_messages: int = Field(default=18, ge=8)


@lru_cache
def get_settings() -> Settings:
    return Settings()
