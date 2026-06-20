# AERUMENTIS

**An AI-powered operational brain for airports, maintenance teams, and airlines.**

Aerumentis unifies three critical aviation operations into a single, modern, connected platform — replacing the fragmented, outdated software that plagues the aerospace industry.

---

## Architecture

Three modules, one ecosystem:

### Phase 1 — Maintenance Documentation AI
Upload maintenance manuals, service bulletins, airworthiness directives, and SOPs. Mechanics ask questions in plain English and get instant answers with citation links back to the source material. Powered by RAG (Retrieval-Augmented Generation) with vector search.

### Phase 2 — Aerospace Knowledge Brain
Capture decades of technician experience before it walks out the door. Voice interviews, repair histories, technician notes, and incident reports are indexed and searchable. The killer feature: "Have we seen this fuel pressure issue before?" → the AI searches years of history and returns pattern matches with common causes and resolutions.

### Phase 3 — Airport Ground Operations AI
Real-time operational intelligence for the ramp. Track aircraft, orchestrate turnarounds, assign crew and equipment, and get AI-powered delay predictions before they happen. The dashboard gives operations managers a live snapshot of everything happening on the ground.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI (async, Python 3.11+) |
| **Database** | PostgreSQL (SQLAlchemy 2.0 + Alembic migrations) |
| **Vector Store** | Qdrant (semantic search & embeddings) |
| **AI/LLM** | OpenAI / OpenRouter (configurable) |
| **Embeddings** | OpenAI text-embedding-3-small (1536 dimensions) |
| **Document Processing** | PyPDF2, python-docx, custom chunking |
| **Auth** | JWT + API Key (SHA-256 hashed, scoped permissions) |
| **Testing** | pytest + pytest-asyncio (138 tests) |
| **CI/CD** | GitHub Actions |
| **Containerization** | Docker + docker-compose |

---

## Project Structure

```
AERUMENTIS/
├── src/aerumentis/
│   ├── main.py                    # FastAPI app factory
│   ├── api/v1/                    # Core API endpoints
│   │   ├── auth.py                # Authentication (register, login, me)
│   │   ├── chat.py                # RAG chat with documents
│   │   ├── documents.py           # Document upload & management
│   │   └── health.py              # Health & system info
│   ├── core/                      # Cross-cutting concerns
│   │   ├── config.py              # Pydantic settings
│   │   ├── database.py            # SQLAlchemy engine, session, Base
│   │   ├── security.py            # JWT, API keys, RBAC permissions
│   │   ├── hashing.py             # SHA-256 API key hashing
│   │   └── logging.py             # Structured logging
│   ├── models/                    # Database models
│   │   ├── database_models.py     # Phase 1: Organization, User, ApiKey, Document, ChatSession, ChatMessage
│   │   ├── phase2_models.py       # Phase 2: KnowledgeEntry, VoiceInterview, KnowledgeNode, KnowledgeEdge, RepairHistory
│   │   ├── phase3_models.py       # Phase 3: Aircraft, Turnaround, TurnaroundTask, GroundCrew, Equipment, OperationsAlert
│   │   └── schemas.py             # Pydantic request/response schemas
│   ├── modules/                   # Feature modules (modular architecture)
│   │   ├── knowledge/routers/     # Phase 2 API endpoints
│   │   ├── maintenance/routers/   # Phase 1 troubleshooting
│   │   └── operations/routers/    # Phase 3 API endpoints
│   └── services/                  # Business logic
│       ├── api_key_service.py     # API key CRUD + hashing
│       ├── chat_history_service.py# Chat session persistence
│       ├── document_processor.py  # PDF/DOCX parsing + chunking
│       ├── document_metadata_service.py
│       ├── embedding_service.py   # OpenAI embeddings
│       ├── ingestion_service.py   # Document → chunks → vectors pipeline
│       ├── knowledge_service.py   # Knowledge brain (Phase 2)
│       ├── llm_service.py         # LLM abstraction (OpenAI/OpenRouter)
│       ├── operations_service.py  # Ground ops (Phase 3)
│       ├── rag_engine.py          # Retrieval + generation
│       └── vector_store.py        # Qdrant interface
├── alembic/                       # Database migrations
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_phase2_knowledge.py
│       └── 003_phase3_operations.py
├── tests/                         # 138 tests (unit + integration)
├── docker-compose.yml             # PostgreSQL + Qdrant + API
├── Dockerfile
├── pyproject.toml
└── .github/workflows/ci.yml       # CI pipeline
```

---

## API Overview

### Authentication
- `POST /api/v1/auth/register` — Create org + admin user
- `POST /api/v1/auth/login` — Get JWT token
- `GET /api/v1/auth/me` — Current user info
- `POST /api/v1/auth/api-keys` — Create scoped API key
- `GET /api/v1/auth/api-keys` — List API keys
- `DELETE /api/v1/auth/api-keys/{id}` — Revoke API key

### Documents (Phase 1)
- `POST /api/v1/documents/upload` — Upload PDF/DOCX/TXT
- `GET /api/v1/documents` — List documents
- `GET /api/v1/documents/{id}` — Get document details
- `DELETE /api/v1/documents/{id}` — Delete document
- `POST /api/v1/documents/{id}/reindex` — Re-index document

### Chat (Phase 1)
- `POST /api/v1/chat` — Ask a question, get RAG-powered answer with citations
- `GET /api/v1/chat/sessions` — List chat sessions
- `GET /api/v1/chat/sessions/{id}/messages` — Get chat history

### Knowledge (Phase 2)
- `POST /api/v1/knowledge/entries` — Create knowledge entry
- `GET /api/v1/knowledge/entries` — List/filter entries
- `POST /api/v1/knowledge/search` — Semantic search
- `POST /api/v1/knowledge/patterns` — **Pattern matching** ("Have we seen this before?")
- `POST /api/v1/knowledge/repairs` — Create repair history
- `GET /api/v1/knowledge/repairs` — List repair history
- `POST /api/v1/knowledge/interviews` — Create voice interview
- `PUT /api/v1/knowledge/interviews/{id}/transcript` — Add transcript
- `POST /api/v1/knowledge/interviews/{id}/extract` — AI-extract knowledge from transcript
- `GET /api/v1/knowledge/graph` — Knowledge graph visualization data
- `GET /api/v1/knowledge/stats` — Knowledge statistics

### Operations (Phase 3)
- `POST /api/v1/operations/aircraft` — Register aircraft
- `GET /api/v1/operations/aircraft` — List active aircraft
- `PATCH /api/v1/operations/aircraft/{id}/status` — Update aircraft status
- `POST /api/v1/operations/turnarounds` — Create turnaround (auto-generates tasks)
- `GET /api/v1/operations/turnarounds` — List turnarounds
- `GET /api/v1/operations/turnarounds/flight/{flight}` — Full turnaround dashboard view
- `PATCH /api/v1/operations/tasks/{id}` — Update task status
- `POST /api/v1/operations/crew` — Create crew member
- `POST /api/v1/operations/crew/assign` — Assign crew to task
- `GET /api/v1/operations/crew/available` — Find available crew
- `POST /api/v1/operations/equipment` — Register equipment
- `POST /api/v1/operations/equipment/assign` — Assign equipment to task
- `GET /api/v1/operations/turnarounds/{id}/risk` — AI delay prediction
- `POST /api/v1/operations/alerts` — Create alert
- `POST /api/v1/operations/alerts/{id}/acknowledge` — Acknowledge alert
- `POST /api/v1/operations/alerts/{id}/resolve` — Resolve alert
- `GET /api/v1/operations/dashboard` — **Full operations dashboard**

---

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Qdrant (or Docker to run it)
- OpenAI API key (or OpenRouter)

### Quick Start with Docker
```bash
docker-compose up -d
# API available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### Manual Setup
```bash
pip install -e .
alembic upgrade head
uvicorn aerumentis.main:app --reload
```

### Environment Variables
```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/aerumentis
QDRANT_URL=http://localhost:6333
OPENAI_API_KEY=sk-...
JWT_SECRET=your-secret-key
```

---

## Testing
```bash
PYTHONPATH=src pytest tests/ -v
```
138 tests — unit + integration — all passing.

---

## Permissions (RBAC)

| Role | Permissions |
|---|---|
| **admin** | Full access to all endpoints |
| **maintainer** | Upload docs, manage knowledge, chat |
| **operator** | View operations, manage crew/tasks |
| **viewer** | Read-only access |

---

## License
Proprietary — BridgeLine Services
