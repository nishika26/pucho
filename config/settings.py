import os
from pathlib import Path
from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = parent of the `config/` package. Used to resolve the .env file
# regardless of the process's current working directory (uvicorn, alembic,
# streamlit, and pytest all launch from different cwds).
REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Process configuration.

    All secrets default to empty so the module imports cleanly on every
    surface (the WhatsApp webhook needs Twilio + Sarvam; the Streamlit
    dashboard needs only the DB + OpenAI). Each consumer validates the
    specific values it needs at point of use — we don't gate the whole
    process on secrets a given entrypoint will never touch.

    Database config accepts EITHER a full `DATABASE_URL` (Supabase/Vercel
    style) OR the discrete `POSTGRES_*` parts (the dashboard + Alembic style).
    `database_url` resolves the two into one DSN.
    """

    model_config = SettingsConfigDict(
        env_ignore_empty=True,
        extra="ignore",
    )

    ENVIRONMENT: Literal["development", "production"] = "development"

    # LLM / STT-TTS providers
    OPENAI_API_KEY: str = ""
    SARVAMAI_API_KEY: str = ""

    # Database — full DSN, or assembled from the discrete parts below.
    DATABASE_URL: str = ""
    POSTGRES_SERVER: str = ""
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "postgres"

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""

    # Vercel Blob — hosts the TTS audio for voice replies
    BLOB_READ_WRITE_TOKEN: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Resolved libpq DSN. Prefer DATABASE_URL; else build from POSTGRES_*.

        Returns "" if neither is configured — callers that need the DB raise
        a clear error when they try to build the engine.
        """
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.POSTGRES_SERVER and self.POSTGRES_USER:
            return (
                f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        return ""


def get_settings() -> Settings:
    """Get settings, loading the repo-root .env when present.

    The path is anchored to the repo root so the file loads no matter which
    directory the process was started from (uvicorn, alembic, streamlit).
    Real environment variables always take precedence over the file, so
    production platforms (Vercel, Streamlit Cloud) can inject secrets
    directly without a file.
    """
    return Settings(_env_file=str(REPO_ROOT / ".env"))


settings = get_settings()
