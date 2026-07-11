FROM python:3.11-slim-bookworm

ARG UV_VERSION=0.11.14

RUN pip install --no-cache-dir uv==${UV_VERSION}

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-extra embedding

COPY src/ ./src/
COPY scripts/ ./scripts/
COPY rules/ ./rules/
COPY data/rag/ ./data/rag/
COPY mock_data/ ./mock_data/

ENV PYTHONPATH=/app/src

EXPOSE 8000
