# API and worker share this image; ROLE=worker starts the run executor instead of the API.
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.11.*
WORKDIR /srv/services/api

COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/api/ ./
COPY content/ /srv/content/
COPY config/ /srv/config/
ENV PATH="/srv/services/api/.venv/bin:$PATH" \
    CONTENT_DIR=/srv/content \
    MODELS_CONFIG=/srv/config/models.yaml

RUN useradd --uid 10001 --no-create-home app && chown -R app /srv
USER app
EXPOSE 8000
CMD ["sh", "-c", "if [ \"$ROLE\" = worker ]; then exec arq app.worker.WorkerSettings; else python -m app.bootstrap && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers; fi"]
