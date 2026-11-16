from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), extra="ignore")
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://humanloop:humanloop@localhost:5432/humanloop"
    frontend_url: str = "http://localhost:3000"
    cookie_secure: bool = False
    demo_mode: bool = False
    public_bookings_enabled: bool = False
    payment_provider: str = "mock"
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_connect_enabled: bool = False
    llm_provider: str = "deterministic"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    upload_dir: str = "uploads"
    mail_dir: str = "local-mail"
    session_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.environment == "production":
        if not settings.cookie_secure or settings.demo_mode:
            raise ValueError("Production requires secure cookies and demo mode disabled")
        if not settings.frontend_url.startswith("https://"):
            raise ValueError("Production requires HTTPS")
    if settings.stripe_secret_key and not settings.stripe_secret_key.startswith("sk_test_"):
        raise ValueError("Only Stripe test keys are supported")
    if settings.stripe_connect_enabled:
        raise ValueError("Connect transfers are not available pending review")
    return settings
