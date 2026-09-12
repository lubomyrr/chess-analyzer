FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN mkdir --parents app \
    && touch app/__init__.py \
    && python -m pip install --no-cache-dir .

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

RUN useradd --create-home appuser

USER appuser

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
