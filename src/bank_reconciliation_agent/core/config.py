from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bank Reconciliation Agent"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    mysql_dsn: str = "mysql+pymysql://root:password@127.0.0.1:3306/AI_agent"
    chroma_path: str = "./chroma_data"
    upload_dir: str = "./uploads"
    trace_dir: str = "./data/traces"
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_upload_rows: int = 10_000
    llm_provider: Literal["fake", "deepseek"] = "fake"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
