from pathlib import Path

from pydantic import Field
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "CollabAI API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:5173"

    MONGODB_URI: str = ""
    MONGODB_DB_NAME: str = "collab_ai"
    MONGODB_MAX_POOL_SIZE: int = 50
    MONGODB_MIN_POOL_SIZE: int = 5
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 5000
    MONGODB_CONNECT_TIMEOUT_MS: int = 10000

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    SESSION_COOKIE_NAME: str = "collabai_session"
    CSRF_COOKIE_NAME: str = "collabai_csrf"
    SESSION_TTL_DAYS: int = 7
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_PROVIDER: str = "smtp"
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    SUMMARIZER_MAX_DOCUMENT_CHUNKS: int = Field(default=54, ge=1, le=120)
    SUMMARIZER_CHUNKS_PER_SECTION: int = Field(default=3, ge=1, le=6)
    SUMMARIZER_MAP_CONCURRENCY: int = Field(default=3, ge=1, le=5)
    SUMMARIZER_DEADLINE_SECONDS: int = Field(default=150, ge=30, le=300)
    SUMMARIZER_REDUCE_CONTEXT_CHARS: int = Field(default=16000, ge=4000, le=24000)

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_cookie_settings(self) -> "Settings":
        if self.COOKIE_SAMESITE not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict, or none")
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true when COOKIE_SAMESITE is none")
        if self.ENVIRONMENT.lower() in {"production", "prod"} and not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true in production")
        return self


settings = Settings()
