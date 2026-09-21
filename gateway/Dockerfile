# Build context is the repository root (see docker-compose.yml)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTRACTS_DIR=/app/contracts

WORKDIR /app
COPY shared /app/shared
RUN pip install --no-cache-dir /app/shared

COPY contracts /app/contracts
COPY gateway/pyproject.toml /app/gateway/pyproject.toml
COPY gateway/app /app/gateway/app

WORKDIR /app/gateway
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
