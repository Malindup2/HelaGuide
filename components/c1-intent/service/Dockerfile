# Build context is the repository root (see docker-compose.yml)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTRACTS_DIR=/app/contracts

WORKDIR /app
COPY shared /app/shared
RUN pip install --no-cache-dir /app/shared

COPY contracts /app/contracts
COPY components/c1-intent/service/pyproject.toml /app/service/pyproject.toml
COPY components/c1-intent/service/app /app/service/app

WORKDIR /app/service
RUN pip install --no-cache-dir .

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
