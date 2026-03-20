from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./provenance.db"

    # Anthropic (required for v1)
    anthropic_api_key: str = ""
    anthropic_default_model: str = "claude-opus-4-5"
    anthropic_default_temperature: float = 0.2

    # OpenAI (stubbed in v1)
    openai_api_key: str = ""
    openai_default_model: str = "gpt-4o"

    # Gemini (stubbed in v1)
    gemini_api_key: str = ""
    gemini_default_model: str = "gemini-1.5-pro"

    # Probing defaults
    default_probe_mode: str = "isolation"  # "isolation" | "aggregate"
    probe_timeout_seconds: int = 60
    probe_max_retries: int = 3

    # pytrends
    pytrends_request_delay_seconds: float = 1.0
    pytrends_timeout: int = 30

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
