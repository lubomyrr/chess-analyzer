from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    celery_broker_url: str = "amqp://guest:guest@localhost:5672//"
    stockfish_path: str = "stockfish"
    stockfish_depth: int = 12
    stockfish_threads: int = 1
    stockfish_hash_mb: int = 64
    stockfish_timeout_seconds: float = 120.0
    analysis_pv_length: int = 4

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
