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
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from aerumentis.core import database as db_module
from aerumentis.core.database import Base


@pytest_asyncio.fixture
async def test_engine():
    """Create a shared in-memory SQLite engine and patch the module-level engine/factory."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Patch the module-level objects so all code uses the test DB
    original_engine = db_module.engine
    original_factory = db_module.async_session_factory
    db_module.engine = engine
    db_module.async_session_factory = factory

    # Also patch in security module which imports async_session_factory at module level
    from aerumentis.core import security as sec_module
    original_sec_factory = sec_module.async_session_factory
    sec_module.async_session_factory = factory

    yield engine

    # Restore
    db_module.engine = original_engine
    db_module.async_session_factory = original_factory
    sec_module.async_session_factory = original_sec_factory
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine):
    """Get a test database session."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


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
