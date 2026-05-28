from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bank Reconciliation Agent"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    mysql_dsn: str = "mysql+pymysql://root:password@127.0.0.1:3306/AI_agent"
    chroma_path: str = "./chroma_data"
    upload_dir: str = "./uploads"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
