# syntax=docker/dockerfile:1
# --- web build ---
FROM node:22.11-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- runtime ---
FROM python:3.12.7-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY superteacher/ ./superteacher/
COPY alembic/ ./alembic/
COPY alembic.ini server.py ./
COPY --from=web /web/dist ./web/dist

# Non-root; data lives on a volume. Secrets (AUTH_PASSWORD, SESSION_SECRET, ANTHROPIC_API_KEY) are injected at
# runtime and never baked into the image. AUTH_PASSWORD is REQUIRED: the container refuses to start without it
# (set AUTH_DISABLED=true only for throwaway local runs).
RUN useradd --system --uid 10001 --create-home app && mkdir -p /data && chown app /data
USER app
ENV PORT=8080 DATABASE_URL=sqlite:////data/superteacher.db STATIC_DIR=web/dist
# Cloud Run (and most platforms) put a proxy in front of the container. Without this uvicorn ignores X-Forwarded-For,
# so every user looks like the proxy's address and the login lockout (5 failures) would lock out everyone at once.
# "*" is right when only the platform's proxy can reach the container; self-hosting? Set your proxy's IP instead.
ENV FORWARDED_ALLOW_IPS=*
VOLUME /data
EXPOSE 8080
# /api/health is intentionally public so probes work with auth enabled.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/api/health')"
CMD ["python", "server.py"]
