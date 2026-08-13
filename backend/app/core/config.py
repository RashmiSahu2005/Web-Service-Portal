import os
from dotenv import load_dotenv

# Load variables from .env file into os environment
load_dotenv()

class Settings:
    PROJECT_NAME: str = "Application Hub"
    API_V1_STR: str = ""
    BACKEND_CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000", "http://192.168.10.83:5173", "http://127.0.0.1:5174"]
    
    USE_FLEETDM: bool = os.getenv("USE_FLEETDM", "false").lower() == "true"
    FLEET_BASE_URL: str = os.getenv("FLEET_BASE_URL", "")
    FLEET_API_TOKEN: str = os.getenv("FLEET_API_TOKEN", "")
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "sqlite:///./application_hub.db")
    POLLING_INTERVAL: int = int(os.getenv("POLLING_INTERVAL", "5"))
    SMTP_ENABLED: bool = os.getenv("SMTP_ENABLED", "True").lower() == "true"
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "apmosys.icewarpcloud.in")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_SENDER_EMAIL: str = os.getenv("SMTP_SENDER_EMAIL", "noreply@applicationhub.local")
    REPOSITORY_PATH: str = os.getenv("REPOSITORY_PATH", "./repository")

    # LLM Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemma4:31b-cloud")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    
    # Tavily
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    
    # Cache
    LATEST_VERSION_CACHE_TTL_HOURS: int = int(os.getenv("LATEST_VERSION_CACHE_TTL_HOURS", "24"))
    
    # Celery
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    
    # Phase 5 Execution Flag
    REAL_FLEET_TEST: bool = os.getenv("REAL_FLEET_TEST", "false").lower() == "true"
    
    # Execution Timeouts
    INSTALL_COMMAND_TIMEOUT: int = int(os.getenv("INSTALL_COMMAND_TIMEOUT", "600"))
    VERIFICATION_COMMAND_TIMEOUT: int = int(os.getenv("VERIFICATION_COMMAND_TIMEOUT", "60"))
    SCRIPT_EXECUTION_TIMEOUT_SECONDS: int = int(os.getenv("SCRIPT_EXECUTION_TIMEOUT_SECONDS", "900"))
    SCRIPT_POLLING_INTERVAL: int = int(os.getenv("SCRIPT_POLLING_INTERVAL", "60"))

settings = Settings()
