# syntax=docker/dockerfile:1
# --- web build ---
FROM node:24.20.0-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- runtime ---
FROM python:3.12.7-slim-bookworm
ARG VERSION=dev
ENV VERSION=$VERSION
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# Litestream: pinned release, checksum-verified (scripts/install_litestream.py). Upgrading = change both values.
ARG LITESTREAM_VERSION=0.5.17
ARG LITESTREAM_SHA256=cfb371176d164437ae869f8351cfde49bd1804ae71c61923f75c9cba9c9c006d
COPY scripts/install_litestream.py /tmp/install_litestream.py
RUN python /tmp/install_litestream.py "$LITESTREAM_VERSION" "$LITESTREAM_SHA256" && rm /tmp/install_litestream.py
COPY superteacher/ ./superteacher/
COPY alembic/ ./alembic/
COPY alembic.ini server.py litestream.yml docker-entrypoint.sh ./
# Do not rely on git preserving the executable bit (repos on Windows/WSL mounts often do not).
RUN chmod 0755 /app/docker-entrypoint.sh
COPY --from=web /web/dist ./web/dist

# Non-root; data lives on a volume. Secrets (AUTH_PASSWORD, SESSION_SECRET, ANTHROPIC_API_KEY) are injected at
# runtime and never baked into the image. AUTH_PASSWORD is REQUIRED: the container refuses to start without it
# (set AUTH_DISABLED=true only for throwaway local runs).
RUN useradd --system --uid 10001 --create-home app && mkdir -p /data && chown app /data
USER app
ENV PORT=8080 DATABASE_URL=sqlite:////data/superteacher.db STATIC_DIR=web/dist
# The Cloud Run release sets FORWARDED_ALLOW_IPS=* for its platform proxy.
# Directly reachable local containers retain Uvicorn's restricted default.
VOLUME /data
EXPOSE 8080
# /api/health is intentionally public so probes work with auth enabled.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/api/health')"
# With LITESTREAM_REPLICA_URL set the entrypoint restores the DB and replicates it (see docker-entrypoint.sh).
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "server.py"]
