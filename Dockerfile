# --- web build ---
FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- runtime ---
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY superteacher/ ./superteacher/
COPY server.py .
COPY --from=web /web/dist ./web/dist

# Data lives on a volume; secrets (ANTHROPIC_API_KEY) are injected at runtime, never baked into the image.
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
ENV PORT=8080 DATABASE_URL=sqlite:////data/superteacher.db STATIC_DIR=web/dist
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/api/health')"
CMD ["python", "server.py"]
