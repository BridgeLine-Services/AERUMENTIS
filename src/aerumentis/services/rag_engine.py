"""
Aerumentis — RAG Engine
Core Retrieval-Augmented Generation pipeline for Module 1.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from aerumentis.core.config import get_settings
from aerumentis.core.logging import get_logger
from aerumentis.services.embedding_service import get_embedding_service
from aerumentis.services.llm_service import get_llm_service
from aerumentis.services.vector_store import SearchResult, get_vector_store

logger = get_logger("aerumentis.rag")
settings = get_settings()


@dataclass
class Citation:
    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    score: float
    page: int | None = None
    section: str | None = None


@dataclass
class RAGResponse:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    query: str = ""
    model: str = ""
    tokens_used: int = 0
    retrieval_time_ms: float = 0.0
    generation_time_ms: float = 0.0
    total_time_ms: float = 0.0
    context_chunks_used: int = 0


@dataclass
class RAGStreamChunk:
    content: str
    citations: list[Citation] | None = None
    done: bool = False


MAINTENANCE_SYSTEM_PROMPT = """\
You are Aerumentis, an AI maintenance documentation assistant for aerospace and aviation professionals.
Your role is to help maintenance technicians, engineers, and ground crew find accurate information
from maintenance manuals, service bulletins, airworthiness directives, and standard operating procedures.

CRITICAL RULES:
1. Only use information from the provided context. Do not hallucinate or fabricate procedures.
2. If the context does not contain enough information to answer, say so explicitly.
3. Always cite your sources using [Source N] notation where N matches the citation number.
4. Prioritize safety warnings and cautions — always include them when present in the context.
5. When providing procedures, maintain the original step-by-step structure from the manual.
6. If multiple procedures exist, clarify which aircraft model / system the procedure applies to.
7. Use precise technical terminology — do not simplify or paraphrase critical maintenance steps.
8. If you detect a potential safety issue, flag it prominently with ⚠️ WARNING.

CONTEXT (from maintenance documentation):
{context}

When answering:
- Start with a direct answer to the question
- Include any safety warnings or cautions
- List required tools if mentioned
- Reference specific manual sections
- Cite sources as [Source 1], [Source 2], etc.
"""


class RAGEngine:
    def __init__(self) -> None:
        self._embedding_service = get_embedding_service()
        self._llm_service = get_llm_service()
        self._vector_store = get_vector_store()
        self._collection = "maintenance_docs"

    async def query(
        self, question: str, top_k: int | None = None,
        score_threshold: float | None = None, filters: dict[str, Any] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> RAGResponse:
        start_time = time.time()
        top_k = top_k or settings.rag_top_k
        score_threshold = score_threshold or settings.rag_score_threshold

        search_query = question
        if settings.rag_enable_query_rewriting and conversation_history:
            search_query = await self._rewrite_query(question, conversation_history)

        query_vector = await self._embedding_service.embed(search_query)

        retrieval_start = time.time()
        search_results = await self._vector_store.search(
            collection_name=self._collection, query_vector=query_vector,
            top_k=top_k, score_threshold=score_threshold, filters=filters,
        )
        retrieval_time_ms = (time.time() - retrieval_start) * 1000

        if not search_results:
            return RAGResponse(
                answer="I couldn't find any relevant information in the maintenance documentation for your query. Try rephrasing your question or checking if the relevant manuals have been uploaded.",
                query=question, retrieval_time_ms=retrieval_time_ms,
                total_time_ms=(time.time() - start_time) * 1000,
            )

        context_text, citations = self._build_context(search_results)

        generation_start = time.time()
        messages = self._build_messages(question, context_text, conversation_history)
        response = await self._llm_service.chat(messages)
        generation_time_ms = (time.time() - generation_start) * 1000
        total_time_ms = (time.time() - start_time) * 1000

        return RAGResponse(
            answer=response["content"], citations=citations, query=question,
            model=response.get("model", ""),
            tokens_used=response.get("usage", {}).get("total_tokens", 0),
            retrieval_time_ms=retrieval_time_ms, generation_time_ms=generation_time_ms,
            total_time_ms=total_time_ms, context_chunks_used=len(search_results),
        )

    async def query_stream(
        self, question: str, top_k: int | None = None,
        score_threshold: float | None = None, filters: dict[str, Any] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[RAGStreamChunk]:
        top_k = top_k or settings.rag_top_k
        score_threshold = score_threshold or settings.rag_score_threshold

        search_query = question
        if settings.rag_enable_query_rewriting and conversation_history:
            search_query = await self._rewrite_query(question, conversation_history)

        query_vector = await self._embedding_service.embed(search_query)
        search_results = await self._vector_store.search(
            collection_name=self._collection, query_vector=query_vector,
            top_k=top_k, score_threshold=score_threshold, filters=filters,
        )

        if not search_results:
            yield RAGStreamChunk(
                content="I couldn't find any relevant information in the maintenance documentation for your query.",
                citations=[], done=True,
            )
            return

        context_text, citations = self._build_context(search_results)
        yield RAGStreamChunk(content="", citations=citations, done=False)

        messages = self._build_messages(question, context_text, conversation_history)
        stream = await self._llm_service.chat(messages, stream=True)
        async for chunk in stream:
            yield RAGStreamChunk(content=chunk["content"], done=False)
        yield RAGStreamChunk(content="", done=True)

    async def _rewrite_query(self, question: str, history: list[dict[str, str]]) -> str:
        recent = history[-4:] if len(history) > 4 else history
        history_text = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:200]}" for m in recent
        )
        messages = [
            {"role": "system", "content": "Rewrite the user's question into a standalone search query for a maintenance documentation database. Remove conversational references. Output ONLY the rewritten query, nothing else."},
            {"role": "user", "content": f"Conversation history:\n{history_text}\n\nQuestion to rewrite: {question}"},
        ]
        response = await self._llm_service.chat(messages, max_tokens=150, temperature=0.0)
        return response["content"].strip()

    def _build_context(self, results: list[SearchResult]) -> tuple[str, list[Citation]]:
        context_parts: list[str] = []
        citations: list[Citation] = []
        for i, result in enumerate(results):
            source_num = i + 1
            text = result.payload.get("text", "")
            context_parts.append(f"[Source {source_num}]\n{text}")
            citations.append(Citation(
                chunk_id=result.id, document_id=result.payload.get("document_id", ""),
                filename=result.payload.get("filename", "Unknown"),
                chunk_index=result.payload.get("chunk_index", 0),
                text=text[:500], score=result.score,
                page=result.payload.get("page"), section=result.payload.get("section"),
            ))
        return "\n\n---\n\n".join(context_parts), citations

    def _build_messages(
        self, question: str, context: str, history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        system_prompt = MAINTENANCE_SYSTEM_PROMPT.format(context=context)
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history[-6:] if len(history) > 6 else history)
        messages.append({"role": "user", "content": question})
        return messages


_rag_engine: RAGEngine | None = None

def get_rag_engine() -> RAGEngine:
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine
