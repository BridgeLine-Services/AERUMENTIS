"""
Aerumentis — Vector Store (Qdrant)
Abstraction layer over Qdrant for collection management and similarity search.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from aerumentis.core.config import get_settings
from aerumentis.core.logging import get_logger

logger = get_logger("aerumentis.vector_store")
settings = get_settings()

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http import models as qdrant_models
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    AsyncQdrantClient = None  # type: ignore
    qdrant_models = None  # type: ignore


@dataclass
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class VectorStore:
    def __init__(self) -> None:
        if not QDRANT_AVAILABLE:
            logger.warning("qdrant_not_installed", msg="Vector store in mock mode")
            self._client = None
            return
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=30
        )

    async def ensure_collection(self, collection_name: str) -> None:
        if not self._client:
            return
        full_name = settings.qdrant_collection(collection_name)
        try:
            await self._client.get_collection(full_name)
        except Exception:
            distance = qdrant_models.Distance.COSINE
            if settings.qdrant_distance.lower() == "euclid":
                distance = qdrant_models.Distance.EUCLID
            elif settings.qdrant_distance.lower() == "dot":
                distance = qdrant_models.Distance.DOT
            await self._client.create_collection(
                collection_name=full_name,
                vectors_config=qdrant_models.VectorParams(
                    size=settings.qdrant_vector_size, distance=distance
                ),
            )
            logger.info("collection_created", collection=full_name)

    async def upsert(self, collection_name: str, points: Sequence[VectorPoint]) -> int:
        if not self._client:
            return len(points)
        full_name = settings.qdrant_collection(collection_name)
        qdrant_points = [
            qdrant_models.PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points
        ]
        batch_size = 100
        for i in range(0, len(qdrant_points), batch_size):
            await self._client.upsert(
                collection_name=full_name, points=qdrant_points[i : i + batch_size], wait=True
            )
        logger.info("vectors_upserted", collection=full_name, count=len(points))
        return len(points)

    async def upsert_points(
        self, collection_name: str, points: list[tuple[str, list[float], dict]]
    ) -> int:
        """Upsert points from (id, vector, payload) tuples."""
        vector_points = [VectorPoint(id=p[0], vector=p[1], payload=p[2]) for p in points]
        return await self.upsert(collection_name, vector_points)

    async def delete_points(self, collection_name: str, point_ids: list[str]) -> None:
        """Delete points by their IDs."""
        if not self._client or not point_ids:
            return
        full_name = settings.qdrant_collection(collection_name)
        try:
            await self._client.delete(
                collection_name=full_name,
                points_selector=qdrant_models.PointIdsList(points=point_ids),
                wait=True,
            )
            logger.info("points_deleted", collection=full_name, count=len(point_ids))
        except Exception as e:
            logger.warning("delete_points_failed", collection=full_name, error=str(e))

    async def search(
        self, collection_name: str, query_vector: list[float],
        top_k: int = 5, score_threshold: float | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        if not self._client:
            return []
        full_name = settings.qdrant_collection(collection_name)
        qdrant_filter = None
        if filters:
            conditions = [
                qdrant_models.FieldCondition(key=k, match=qdrant_models.MatchValue(value=v))
                for k, v in filters.items()
            ]
            qdrant_filter = qdrant_models.Filter(must=conditions)
        results = await self._client.search(
            collection_name=full_name, query_vector=query_vector,
            limit=top_k, score_threshold=score_threshold, query_filter=qdrant_filter,
        )
        search_results = [
            SearchResult(id=str(hit.id), score=hit.score, payload=hit.payload or {})
            for hit in results
        ]
        logger.debug("search_complete", collection=full_name, count=len(search_results))
        return search_results

    async def delete_collection(self, collection_name: str) -> None:
        if not self._client:
            return
        await self._client.delete_collection(settings.qdrant_collection(collection_name))

    async def count(self, collection_name: str) -> int:
        if not self._client:
            return 0
        try:
            result = await self._client.count(settings.qdrant_collection(collection_name))
            return result.count
        except Exception:
            return 0

    async def close(self) -> None:
        if self._client:
            await self._client.close()


_vector_store: VectorStore | None = None

def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
