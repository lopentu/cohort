# Build dependencies and frontend assets never enter the runtime image.
FROM node:22-bookworm-slim AS frontend
WORKDIR /build/cohort/ui/frontend
COPY cohort/ui/frontend/package*.json ./
RUN npm ci
COPY cohort/ui/frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.26 AS uv
FROM python:3.13-slim-bookworm AS runtime
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH HOME=/tmp XDG_CACHE_HOME=/state/cache
COPY pyproject.toml uv.lock README.md ./
COPY cohort/ ./cohort/
COPY scripts/ ./scripts/
# Keep the source-tree installation: the UI resolves its generated static
# assets beside cohort/ui/api.py, and the normal launcher imports that package.
RUN UV_CACHE_DIR=/tmp/uv-build-cache uv sync --frozen --no-dev --extra ui --extra evidence \
    && rm -rf /tmp/uv-build-cache \
    && mkdir -p /state
COPY --from=frontend /build/cohort/ui/static/ ./cohort/ui/static/
USER 1000:1000
CMD ["python", "scripts/container_ui.py"]
