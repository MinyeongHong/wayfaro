from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://jobmatcher:jobmatcher@localhost:5432/jobmatcher"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = ""
    cv_match_retention_hours: int = Field(24, ge=1, le=168)
    cv_match_cookie_secure: bool = True
    cv_match_allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:8000"]
    cv_match_session_limit: int = Field(10, ge=1, le=100)
    cv_match_global_pending_limit: int = Field(100, ge=1, le=10000)
    cv_match_global_daily_limit: int = Field(200, ge=1, le=100000)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
