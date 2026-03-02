import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - fallback if dotenv is unavailable
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = _env("APP_ENV", "dev")
    app_host: str = _env("APP_HOST", "127.0.0.1")
    app_port: int = int(_env("APP_PORT", "8000"))
    secret_key: str = _env("SECRET_KEY", "hackathon-secret-change-this")

    llm_provider: str = _env("LLM_PROVIDER", "mock").lower()

    azure_openai_endpoint: str = _env("AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = _env("AZURE_OPENAI_API_KEY")
    azure_openai_deployment: str = _env("AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = _env("AZURE_OPENAI_API_VERSION", "2024-10-21")

    openai_api_key: str = _env("OPENAI_API_KEY")
    openai_model: str = _env("OPENAI_MODEL", "gpt-4o-mini")

    huggingface_api_key: str = _env("HUGGINGFACE_API_KEY")
    huggingface_model: str = _env("HUGGINGFACE_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")

    enable_online_context: bool = _env_bool("ENABLE_ONLINE_CONTEXT", True)
    online_context_max_topics: int = int(_env("ONLINE_CONTEXT_MAX_TOPICS", "4"))
    online_context_chars_per_topic: int = int(_env("ONLINE_CONTEXT_CHARS_PER_TOPIC", "550"))


settings = Settings()
