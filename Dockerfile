# Aerumentis — Dockerfile (Multi-stage)
FROM python:3.11-slim as builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --target=/install -e .

FROM python:3.11-slim as runtime
LABEL org.opencontainers.image.title="Aerumentis"
LABEL org.opencontainers.image.version="0.1.0"
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local/lib/python3.11/site-packages
WORKDIR /app
COPY src/ ./src/
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e .
RUN mkdir -p /app/storage
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1
CMD ["uvicorn", "aerumentis.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
