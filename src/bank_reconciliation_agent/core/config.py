import importlib.util
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


BGE_M3_MODEL_NAME = "BAAI/bge-m3"
BGE_SMALL_MODEL_NAME = "BAAI/bge-small-zh-v1.5"


class Settings(BaseSettings):
    app_name: str = "Bank Reconciliation Agent"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    jwt_secret_key: str = "dev-insecure-secret-change-me-please-set-env"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 720
    demo_user_password: str = "demo12345"
    mysql_dsn: str = "mysql+pymysql://root:password@127.0.0.1:3306/AI_agent"
    chroma_path: str = "./chroma_data"
    upload_dir: str = "./uploads"
    trace_dir: str = "./data/traces"
    memory_sqlite_path: str = "./data/memory.sqlite"
    checkpoint_enabled: bool = False
    checkpoint_sqlite_path: str = "./data/checkpoint.sqlite"
    redis_dsn: str = "redis://127.0.0.1:6379/0"
    async_queue_enabled: bool = False
    enable_llm_cache: bool = False
    llm_cache_ttl_seconds: int = 604800
    enable_llm_rate_limit: bool = False
    llm_rate_limit_rpm: int = 60
    llm_rate_limit_max_concurrency: int = 8
    llm_rate_limit_max_wait_seconds: float = 10.0
    llm_rate_limit_window_seconds: int = 60
    job_idempotency_ttl_seconds: int = 3600
    decision_regression_runs: int = 10
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_upload_rows: int = 10_000
    llm_provider: Literal["fake", "deepseek"] = "fake"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"
    enable_rag_rewrite: bool = False
    enable_rag_hybrid: bool = False
    enable_rag_reranker: bool = False
    embedding_backend: Literal["hash", "bge_small", "bge_m3"] = "bge_m3"
    rag_dense_top_n: int = 20
    rag_bm25_top_n: int = 20
    rag_rerank_top_k: int = 5
    rag_rrf_k: int = 60
    # Hash embedding calibration; use 0.5 when a real semantic embedding is enabled.
    rag_dense_min_score: float = 0.341
    rag_reranker_min_score: float = 0.3
    rag_low_score: float = 0.5
    rag_breaker_fail_threshold: int = 5
    rag_breaker_open_seconds: int = 30
    cutoff_window: str = "22:00-24:00"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def rag_dense_min_score_for_backend(self, backend: str | None = None) -> float:
        selected_backend = backend or self.embedding_backend
        if backend is None and selected_backend != "hash" and not _real_embedding_dependency_available():
            selected_backend = "hash"
        if selected_backend == "hash":
            return self.rag_dense_min_score
        if selected_backend in {"bge_small", "bge_m3"}:
            return 0.5
        raise ValueError(f"Unsupported embedding backend: {selected_backend}")


def _real_embedding_dependency_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


settings = Settings()
