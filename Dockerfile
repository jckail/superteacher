# syntax=docker/dockerfile:1
# --- web build ---
FROM node:26.9.0-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- runtime ---
FROM python:3.12.15-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
ARG VERSION=dev
ARG GIT_COMMIT=development
ENV VERSION=$VERSION GIT_COMMIT=$GIT_COMMIT
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
# Production must never seed fake demo students into a real database (the app default stays true for local dev).
ENV SEED_DEMO_DATA=false
WORKDIR /app
# Hash-pinned, fully resolved lock (scripts/update_lock.sh): every image build gets the exact versions CI tested,
# and pip refuses any file whose hash differs. requirements.txt stays the human-edited list of ranges.
COPY requirements.txt requirements.lock ./
RUN pip install --require-hashes --no-deps -r requirements.lock
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
# Release archives may also preserve owner-only modes on copied runtime files.
RUN chmod 0644 /app/alembic.ini /app/server.py /app/litestream.yml
COPY --from=web /web/dist ./web/dist
# Private release archives may contain root-owned directories with mode 0700.
# The runtime user must be able to traverse and read copied code and static assets.
RUN chmod -R a+rX /app/superteacher /app/alembic /app/web

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
