"""
Aerumentis — Embedding Service
Generates vector embeddings for documents and queries.
"""
from __future__ import annotations

from typing import Sequence

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from aerumentis.core.config import get_settings
from aerumentis.core.logging import get_logger

logger = get_logger("aerumentis.embeddings")
settings = get_settings()


class EmbeddingError(Exception):
    pass


class EmbeddingService:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._api_key = settings.active_llm_api_key
        self._base_url = settings.active_llm_base_url
        self._model = settings.embedding_model
        self._dimensions = settings.embedding_dimensions
        self._max_batch_size = 100

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._client

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.NetworkError)),
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True,
    )
    async def embed(self, text: str) -> list[float]:
        embeddings = await self.embed_batch([text])
        return embeddings[0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        results: list[list[float]] = []
        for i in range(0, len(texts), self._max_batch_size):
            batch = list(texts[i : i + self._max_batch_size])
            results.extend(await self._embed_batch_request(batch))
        return results

    async def _embed_batch_request(self, texts: list[str]) -> list[list[float]]:
        payload: dict = {"model": self._model, "input": texts}
        if self._dimensions and "text-embedding-3" in self._model:
            payload["dimensions"] = self._dimensions
        try:
            response = await self.client.post("/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
            embeddings_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in embeddings_data]
        except httpx.HTTPStatusError as e:
            logger.error("embedding_api_error", status_code=e.response.status_code)
            raise EmbeddingError(f"Embedding API error: {e.response.status_code}") from e
        except Exception as e:
            logger.error("embedding_error", error=str(e))
            raise EmbeddingError(f"Embedding failed: {e}") from e

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


_embedding_service: EmbeddingService | None = None

def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
