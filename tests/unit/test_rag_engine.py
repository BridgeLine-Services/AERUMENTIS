"""Aerumentis — Unit Tests: RAG Engine."""
import pytest
from aerumentis.services.rag_engine import RAGResponse, Citation, RAGStreamChunk


class TestRAGDataModels:
    def test_citation_creation(self):
        c = Citation(chunk_id="c1", document_id="d1", filename="amm.pdf",
                     chunk_index=5, text="Replace pump", score=0.95, page=42)
        assert c.chunk_id == "c1"
        assert c.score == 0.95
        assert c.page == 42

    def test_citation_defaults(self):
        c = Citation(chunk_id="c1", document_id="d1", filename="amm.pdf",
                     chunk_index=0, text="test", score=0.5)
        assert c.page is None
        assert c.section is None

    def test_rag_response_defaults(self):
        r = RAGResponse(answer="test answer")
        assert r.citations == []
        assert r.tokens_used == 0
        assert r.context_chunks_used == 0

    def test_rag_stream_chunk(self):
        chunk = RAGStreamChunk(content="hello", done=False)
        assert chunk.content == "hello"
        assert chunk.done is False
        assert chunk.citations is None

    def test_rag_stream_chunk_done(self):
        chunk = RAGStreamChunk(content="", done=True)
        assert chunk.done is True
        assert chunk.content == ""
