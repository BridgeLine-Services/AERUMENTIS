"""Aerumentis — Unit Tests: Configuration."""
import pytest
from aerumentis.core.config import Settings, AppEnvironment, LLMProvider


class TestSettings:
    def test_default_settings(self):
        s = Settings()
        assert s.app_name == "Aerumentis"
        assert s.app_env == AppEnvironment.DEVELOPMENT
        assert s.app_port == 8000
        assert s.rag_chunk_size == 1000
        assert s.rag_top_k == 5

    def test_cors_origins_parsed(self):
        s = Settings(cors_origins="http://localhost:3000,http://localhost:8080")
        assert "http://localhost:3000" in s.cors_origins_list
        assert len(s.cors_origins_list) == 2

    def test_qdrant_collection_namespacing(self):
        s = Settings(qdrant_collection_prefix="aer")
        assert s.qdrant_collection("maintenance_docs") == "aer_maintenance_docs"

    def test_production_validation_fails_without_secret(self):
        with pytest.raises(ValueError, match="SECRET_KEY"):
            Settings(app_env=AppEnvironment.PRODUCTION, secret_key="change-me-to-a-secure-256-bit-key", openai_api_key="sk-test")

    def test_production_validation_fails_without_llm_key(self):
        with pytest.raises(ValueError, match="LLM API key"):
            Settings(app_env=AppEnvironment.PRODUCTION, secret_key="a-very-secure-key-not-default",
                     openai_api_key="", openrouter_api_key="")

    def test_llm_provider_helpers(self):
        s = Settings(llm_provider=LLMProvider.OPENROUTER, openrouter_api_key="or-test", openai_api_key="sk-test")
        assert s.active_llm_api_key == "or-test"
        assert s.active_llm_base_url == "https://openrouter.ai/api/v1"

    def test_storage_path_creates_directory(self, tmp_path):
        path = str(tmp_path / "storage")
        s = Settings(storage_local_path=path)
        assert s.storage_path.exists()
