"""Aerumentis — Unit Tests: Document Processor."""
import pytest
from aerumentis.services.document_processor import (
    chunk_text, count_tokens, process_document, SUPPORTED_EXTENSIONS,
)


class TestChunking:
    def test_short_text_single_chunk(self):
        chunks = chunk_text("This is a short text.", chunk_size=1000, overlap=200)
        assert len(chunks) == 1

    def test_long_text_multiple_chunks(self):
        text = " ".join(["word"] * 5000)
        chunks = chunk_text(text, chunk_size=1000, overlap=200)
        assert len(chunks) > 1

    def test_empty_text(self):
        assert len(chunk_text("", chunk_size=1000, overlap=200)) == 0

    def test_whitespace_only(self):
        assert len(chunk_text("   \n\n  \t  ", chunk_size=1000, overlap=200)) == 0


class TestTokenCounting:
    def test_count_tokens_non_empty(self):
        assert count_tokens("This is a test sentence.") > 0

    def test_count_tokens_empty(self):
        assert count_tokens("") == 0

    def test_count_tokens_long_text(self):
        assert count_tokens("Hello world " * 100) > count_tokens("Hello world")


class TestProcessDocument:
    def test_process_txt_file(self, tmp_path):
        file_path = tmp_path / "test_manual.txt"
        file_path.write_text("Aircraft Maintenance Manual\n\nSection 1: Hydraulic System\nThe hydraulic system.\n")
        doc = process_document(str(file_path))
        assert doc.filename == "test_manual.txt"
        assert doc.file_type == ".txt"
        assert len(doc.chunks) > 0
        assert doc.checksum

    def test_process_with_extra_metadata(self, tmp_path):
        file_path = tmp_path / "amm_737.txt"
        file_path.write_text("Boeing 737 NG AMM content.")
        doc = process_document(str(file_path), extra_metadata={"aircraft_model": "737 NG", "manual_type": "AMM"})
        for chunk in doc.chunks:
            assert chunk.metadata["aircraft_model"] == "737 NG"
            assert chunk.metadata["manual_type"] == "AMM"

    def test_unsupported_file_type_raises(self, tmp_path):
        file_path = tmp_path / "doc.exe"
        file_path.write_text("fake")
        with pytest.raises(ValueError, match="Unsupported file type"):
            process_document(str(file_path))

    def test_supported_extensions(self):
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".docx" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS
