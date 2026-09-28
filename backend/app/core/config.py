import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

# Load variables from .env file into os environment
load_dotenv()

def _parse_cors_origins(raw: str) -> list:
    """Parse a comma-separated CORS origins string into a list."""
    return [origin.strip() for origin in raw.split(",") if origin.strip()]

class Settings:
    PROJECT_NAME: str = "DeployIQ MVP"
    API_V1_STR: str = ""

    # CORS origins — comma-separated in BACKEND_CORS_ORIGINS env var.
    # Default covers common local dev ports only (no organisation-specific IPs).
    BACKEND_CORS_ORIGINS: list = _parse_cors_origins(
        os.getenv(
            "BACKEND_CORS_ORIGINS",
            "http://localhost:5173,http://localhost:5174,http://localhost:3000,http://127.0.0.1:5174"
        )
    )

    USE_FLEETDM: bool = os.getenv("USE_FLEETDM", "false").lower() == "true"
    FLEET_BASE_URL: str = os.getenv("FLEET_BASE_URL", "")
    FLEET_API_TOKEN: str = os.getenv("FLEET_API_TOKEN", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    POLLING_INTERVAL: int = int(os.getenv("POLLING_INTERVAL", "5"))

    SMTP_ENABLED: bool = os.getenv("SMTP_ENABLED", "True").lower() == "true"
    # No organisation-specific server as default — must be set explicitly in .env
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_SENDER_EMAIL: str = os.getenv("SMTP_SENDER_EMAIL", "noreply@applicationhub.local")
    REPOSITORY_PATH: str = os.getenv("REPOSITORY_PATH", "./repository")

    # LLM Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
    # No stale model name as default — must be set in .env (e.g. LLM_MODEL=qwen2.5vl:7b)
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", os.getenv("OLLAMA_URL", "http://localhost:11434"))

    UPDATE_APPROVAL_ADMIN_EMAIL: str = os.getenv("UPDATE_APPROVAL_ADMIN_EMAIL", "rashmi.sahu@ap2l.ai")


    # Tavily (used only by tavily_service.py for version discovery — not for installation research)
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # SearXNG — installation research web search (self-hosted, no API key required)
    SEARXNG_BASE_URL: str = os.getenv("SEARXNG_BASE_URL", "http://localhost:8080")

    # Installation Research Agent
    INSTALLATION_RESEARCH_ENABLED: bool = os.getenv("INSTALLATION_RESEARCH_ENABLED", "true").lower() == "true"
    INSTALLATION_RESEARCH_CACHE_TTL_HOURS: int = int(os.getenv("INSTALLATION_RESEARCH_CACHE_TTL_HOURS", "6"))

    # Cache
    LATEST_VERSION_CACHE_TTL_HOURS: int = int(os.getenv("LATEST_VERSION_CACHE_TTL_HOURS", "24"))

    # Celery / Redis
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    # Shared Redis URL used for pub/sub (WebSocket, email dedup, approval state).
    # Defaults to DB 0 on the same Redis instance used by Celery.
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Phase 5 Execution Flag
    REAL_FLEET_TEST: bool = os.getenv("REAL_FLEET_TEST", "false").lower() == "true"

    # Execution Timeouts
    INSTALL_COMMAND_TIMEOUT: int = int(os.getenv("INSTALL_COMMAND_TIMEOUT", "600"))
    VERIFICATION_COMMAND_TIMEOUT: int = int(os.getenv("VERIFICATION_COMMAND_TIMEOUT", "60"))
    SCRIPT_EXECUTION_TIMEOUT_SECONDS: int = int(os.getenv("SCRIPT_EXECUTION_TIMEOUT_SECONDS", "900"))
    SCRIPT_POLLING_INTERVAL: int = int(os.getenv("SCRIPT_POLLING_INTERVAL", "60"))

    # IMAP Configuration
    ENABLE_IMAP_LISTENER: bool = os.getenv("ENABLE_IMAP_LISTENER", "false").lower() == "true"
    IMAP_HOST: str = os.getenv("IMAP_HOST", "")
    IMAP_PORT: int = int(os.getenv("IMAP_PORT", "993"))
    IMAP_USERNAME: str = os.getenv("IMAP_USERNAME", "")
    IMAP_PASSWORD: str = os.getenv("IMAP_PASSWORD", "")
    IMAP_MAX_EMAILS: int = int(os.getenv("IMAP_MAX_EMAILS", "4"))
    IMAP_USE_SSL: bool = os.getenv("IMAP_USE_SSL", "true").lower() == "true"
    IMAP_POLL_INTERVAL: int = int(os.getenv("IMAP_POLL_INTERVAL", "60"))

    # Mock / dry-run settings (only used when USE_FLEETDM=false)
    MOCK_HOST_ID: int = int(os.getenv("MOCK_HOST_ID", "1"))

settings = Settings()

