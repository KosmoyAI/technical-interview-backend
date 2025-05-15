FROM python:3.12-slim

ENV POETRY_VERSION=1.8.2 \
	PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1

# Install Poetry + build deps for asyncpg
RUN apt-get update && \
	apt-get install -y --no-install-recommends build-essential libpq-dev && \
	pip install --no-cache-dir "poetry==$POETRY_VERSION" && \
	apt-get purge -y build-essential && \
	rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency metadata first
COPY pyproject.toml poetry.lock* /app/

# Install dependencies (no virtualenv inside the container)
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --only main

# Copy the rest of the source
COPY . /app

EXPOSE 8000

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
