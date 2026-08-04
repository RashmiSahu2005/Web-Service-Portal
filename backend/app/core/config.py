class Settings:
    PROJECT_NAME: str = "Application Hub"
    API_V1_STR: str = ""
    BACKEND_CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000", "http://127.0.0.1:5173", "http://127.0.0.1:5174"]

settings = Settings()
