import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from pydantic import BaseModel, Field


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_ROOT / ".env"
load_dotenv(ENV_PATH, override=True)
ENV_FILE_VALUES = dotenv_values(ENV_PATH)


class Settings(BaseModel):
    openai_api_key: str | None = Field(default=None)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-4o"
    openai_embed_model: str = "text-embedding-3-small"
    pinecone_api_key: str | None = Field(default=None)
    pinecone_index_name: str = "recruiting-rubrics"
    pinecone_namespace: str = "rubrics"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    langsmith_tracing: str = "false"
    langsmith_api_key: str | None = Field(default=None)
    langsmith_project: str = "recruiting-pipeline"
    resend_api_key: str | None = Field(default=None)
    resend_from_email: str = "Canteeno <verify@canteeno.in>"
    api_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        return None
    stripped = value.strip()
    if stripped in {"...", "sk-...", "lsv2_...", "re_..."}:
        return None
    return stripped


def _env_file_value(name: str) -> str | None:
    value = ENV_FILE_VALUES.get(name)
    if not value:
        return None
    stripped = value.strip()
    if stripped in {"...", "sk-...", "lsv2_...", "re_..."}:
        return None
    return stripped


@lru_cache
def get_settings() -> Settings:
    default_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    return Settings(
        openai_api_key=_env_value("OPENAI_API_KEY"),
        openai_base_url=(
            _env_file_value("OPENAI_BASE_URL")
            or _env_file_value("OPENAI_API_BASE")
            or "https://api.openai.com/v1"
        ),
        openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o"),
        openai_embed_model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
        pinecone_api_key=_env_value("PINECONE_API_KEY"),
        pinecone_index_name=os.getenv("PINECONE_INDEX_NAME", "recruiting-rubrics"),
        pinecone_namespace=os.getenv("PINECONE_NAMESPACE", "rubrics"),
        pinecone_cloud=os.getenv("PINECONE_CLOUD", "aws"),
        pinecone_region=os.getenv("PINECONE_REGION", "us-east-1"),
        langsmith_tracing=os.getenv("LANGSMITH_TRACING", "false"),
        langsmith_api_key=_env_value("LANGSMITH_API_KEY"),
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "recruiting-pipeline"),
        resend_api_key=_env_value("RESEND_API_KEY"),
        resend_from_email=os.getenv(
            "RESEND_FROM_EMAIL",
            "Canteeno <verify@canteeno.in>",
        ),
        api_cors_origins=_split_csv(os.getenv("API_CORS_ORIGINS"), default_origins),
    )
