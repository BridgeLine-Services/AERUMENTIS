"""Aerumentis — Pytest configuration and shared fixtures."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("APP_DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

import pytest


@pytest.fixture
def sample_maintenance_text():
    return """
    BOEING 737 NG AIRCRAFT MAINTENANCE MANUAL
    SECTION 1: HYDRAULIC SYSTEM
    1.1 GENERAL
    The hydraulic system provides power for flight controls, landing gear, brakes.
    1.2 SAFETY WARNINGS
    WARNING: Always depressurize the hydraulic system before maintenance.
    1.3 HYDRAULIC PUMP REPLACEMENT
    Tools: Removal tool, torque wrench, O-ring seal kit.
    Procedure: 1. Depressurize. 2. Disconnect electrical. 3. Remove lines. 4. Extract pump.
    5. Install new pump. 6. Torque to 150 ft-lbs. 7. Reconnect. 8. Check for leaks.
    """


@pytest.fixture
def sample_chunk():
    from aerumentis.services.document_processor import DocumentChunk
    return DocumentChunk(id="test-chunk-id", text="Test maintenance documentation chunk.",
        metadata={"document_id": "test-doc-id", "filename": "test.pdf", "chunk_index": 0, "total_chunks": 5})
