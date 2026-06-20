# 🛫 Aerumentis

**AI-powered operational brain for airports, maintenance teams, and airlines.**

| Module | Name | Status | Description |
|--------|------|--------|-------------|
| 1 | **Maintenance Documentation AI** | ✅ Phase 1 (Active) | RAG-powered chat with maintenance manuals, service bulletins, and ADs |
| 2 | **Aerospace Knowledge Brain** | 🔜 Phase 2 | Captures institutional knowledge from senior mechanics, repair histories, voice interviews |
| 3 | **Airport Ground Operations** | 🔜 Phase 3 | Real-time aircraft tracking, crew assignments, turnaround monitoring, predictive delay alerts |

---

## 🏗️ Architecture

```
Aerumentis/
├── src/aerumentis/
│   ├── core/               # Config, security (JWT/RBAC), database (async SQLAlchemy), logging
│   ├── api/v1/             # FastAPI routers (auth, documents, chat, health)
│   ├── models/             # Pydantic request/response schemas
│   ├── services/           # LLM, embeddings, vector store, RAG engine, document processing
│   ├── modules/
│   │   ├── maintenance/    # Module 1 — Documentation AI
│   │   ├── knowledge/      # Module 2 — Knowledge Brain (stub)
│   │   └── operations/     # Module 3 — Ground Ops (stub)
│   ├── main.py             # FastAPI app entry point
│   └── worker.py           # Celery worker for async tasks
├── tests/                  # Unit + integration tests
├── .github/workflows/      # CI/CD pipeline
├── Dockerfile              # Multi-stage production build
├── docker-compose.yml      # Full stack: API + Qdrant + Postgres + Redis + Celery
└── pyproject.toml          # Python project config
```

### Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| API Framework | FastAPI | Async, auto-docs, type-safe |
| Database | PostgreSQL + SQLAlchemy 2.0 (async) | ACID, mature ecosystem |
| Vector Database | Qdrant | Purpose-built for similarity search |
| LLM | OpenAI / OpenRouter (OpenAI-compatible) | Flexible model selection, fallback |
| Embeddings | OpenAI text-embedding-3-small | Cost-effective, 1536-dim |
| RAG | Custom pipeline (retrieval + reranking + citations) | Full control, aerospace-optimized |
| Task Queue | Celery + Redis | Async document ingestion |
| Auth | JWT + RBAC + API Keys | Enterprise-grade, multi-tenant |
| Containerization | Docker + Docker Compose | Reproducible, scalable |
| CI/CD | GitHub Actions | Automated lint, test, build |
| Logging | structlog (JSON in prod) | Observable, structured |

---

## 🚀 Quick Start

### Docker Compose (Recommended)

```bash
git clone https://github.com/aerumentis/AERUMENTIS.git
cd AERUMENTIS
cp .env.example .env
# Edit .env: set OPENAI_API_KEY=sk-your-key-here
docker-compose up --build
# API at http://localhost:8000, docs at http://localhost:8000/docs
```

### Local Development

```bash
git clone https://github.com/aerumentis/AERUMENTIS.git
cd AERUMENTIS
chmod +x scripts/setup.sh && ./scripts/setup.sh
docker-compose up -d postgres qdrant redis
source venv/bin/activate
uvicorn aerumentis.main:app --reload
pytest tests/unit/ -v
```

---

## 📖 API Overview

### Upload a Maintenance Document

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@737_ng_amm.pdf" \
  -F "aircraft_model=737 NG" \
  -F "manual_type=AMM"
```

### Query the Maintenance AI

```bash
curl -X POST http://localhost:8000/api/v1/chat/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I replace the hydraulic pump on a Boeing 737 NG?", "aircraft_model": "737 NG"}'
```

**Response:**
```json
{
  "answer": "To replace the hydraulic pump on a Boeing 737 NG...",
  "citations": [{"filename": "737_ng_amm.pdf", "chunk_index": 42, "score": 0.92, "page": 1042}],
  "model": "gpt-4o",
  "tokens_used": 1523,
  "total_time_ms": 1840.5
}
```

---

## 🔐 Security

- JWT authentication (access 30min + refresh 7 days)
- RBAC with 6 roles (superadmin → viewer) and granular permissions
- API key support for programmatic access
- Multi-tenant organization scoping
- CORS, GZip middleware, input validation

---

## 🐳 Docker Services

| Service | Port | Purpose |
|---------|------|---------|
| API | 8000 | FastAPI application |
| PostgreSQL | 5432 | Relational database |
| Qdrant | 6333/6334 | Vector database |
| Redis | 6379 | Caching + Celery broker |
| Celery Worker | — | Async document ingestion |

---

## 🛣️ Roadmap

### Phase 1 ✅ — Maintenance Documentation AI
- [x] RAG pipeline (embed → retrieve → generate → cite)
- [x] PDF, DOCX, TXT, MD, HTML ingestion
- [x] Intelligent text chunking with overlap
- [x] Vector similarity search with metadata filtering
- [x] Streaming responses (SSE)
- [x] JWT auth + RBAC + API keys
- [x] Async ingestion via Celery
- [x] Query rewriting for conversational context

### Phase 2 🔜 — Aerospace Knowledge Brain
- [ ] Technician note capture (text + voice)
- [ ] Repair history storage and search
- [ ] Voice interview transcription
- [ ] Searchable knowledge graph
- [ ] AI-generated recommendations

### Phase 3 🔜 — Airport Ground Operations
- [ ] Real-time aircraft tracking
- [ ] Gate management dashboard
- [ ] Ground crew assignment system
- [ ] Turnaround monitoring
- [ ] Predictive delay alerts (ML)
- [ ] Mobile-optimized control tower dashboard

---

## 📄 License

Proprietary. All rights reserved.

**Aerumentis** — Making aerospace software fast, modern, mobile, searchable, and connected.
