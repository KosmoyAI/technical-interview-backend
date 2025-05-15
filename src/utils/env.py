from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # PostgreSQL
    POSTGRES_USER: str = "myuser"
    POSTGRES_PASSWORD: str = "mypassword"
    POSTGRES_DB: str = "mydb"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432

    # Redis / Valkey
    VALKEY_HOST: str = "valkey"
    VALKEY_PORT: int = 6379
    QUEUE_NAME: str = "ai_queue"

    # OpenRouter / LLM
    OPENROUTER_API_KEY: str = "changeme-openrouter-key"
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    YOUR_SITE_URL: str = "http://localhost"
    YOUR_SITE_NAME: str = "local-dev"

    class Config:
        env_prefix = ""
        case_sensitive = True

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:"
            f"{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

@lru_cache
def get_settings():
    return Settings()
