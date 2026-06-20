"""
Aerumentis — Core Configuration
Centralized, type-safe configuration using Pydantic Settings.
"""

from __future__ import annotations

import enum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(str, enum.Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, enum.Enum):
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    AZURE = "azure"


class StorageType(str, enum.Enum):
    LOCAL = "local"
    S3 = "s3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    app_name: str = "Aerumentis"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "info"

    secret_key: str = "change-me-to-a-secure-256-bit-key"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    api_key_prefix: str = "aer_"

    database_url: str = "postgresql+asyncpg://aerumentis:aerumentis@localhost:5432/aerumentis"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 3600

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection_prefix: str = "aerumentis"
    qdrant_vector_size: int = 1536
    qdrant_distance: str = "Cosine"

    llm_provider: LLMProvider = LLMProvider.OPENAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    chat_model: str = "gpt-4o"
    chat_model_fallback: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    llm_request_timeout: int = 120

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    storage_type: StorageType = StorageType.LOCAL
    storage_local_path: str = "./storage"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    cors_origins_list: list[str] = []

    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 200
    rag_top_k: int = 5
    rag_score_threshold: float = 0.70
    rag_max_context_tokens: int = 12000
    rag_enable_reranking: bool = False
    rag_enable_query_rewriting: bool = True
    rag_enable_citations: bool = True

    @field_validator("cors_origins_list", mode="before")
    @classmethod
    def _default_cors_list(cls, v):
        return v if v else []

    @model_validator(mode="after")
    def _compute_cors(self) -> Settings:
        if not self.cors_origins_list:
            self.cors_origins_list = [
                o.strip() for o in self.cors_origins.split(",") if o.strip()
            ]
        return self

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.app_env == AppEnvironment.PRODUCTION:
            if self.secret_key.startswith("change-me"):
                raise ValueError("SECRET_KEY must be set in production")
            if not self.openai_api_key and not self.openrouter_api_key:
                raise ValueError("At least one LLM API key must be set in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnvironment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == AppEnvironment.DEVELOPMENT

    @property
    def active_llm_api_key(self) -> str:
        if self.llm_provider == LLMProvider.OPENROUTER:
            return self.openrouter_api_key
        return self.openai_api_key

    @property
    def active_llm_base_url(self) -> str:
        if self.llm_provider == LLMProvider.OPENROUTER:
            return self.openrouter_base_url
        return self.openai_base_url

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_local_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def qdrant_collection(self, name: str) -> str:
        return f"{self.qdrant_collection_prefix}_{name}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
