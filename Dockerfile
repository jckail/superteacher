# Build stage for React frontend
FROM node:18 AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --legacy-peer-deps
COPY frontend/ ./
RUN CI=false npm run build

# Final stage
FROM python:3.11-slim

# Get version from build arg
ARG VERSION
LABEL version=${VERSION}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy frontend build
COPY --from=frontend-builder /app/frontend/build /app/frontend/build

# Install backend dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code including setup.py
COPY backend/ ./backend/

# Install backend package in development mode
WORKDIR /app/backend
RUN pip install -e .
WORKDIR /app

# Copy server script
COPY server.py .

# Create directory for SQLite database and set permissions
RUN touch /app/edutrack.db && \
    chown -R nobody:nogroup /app && \
    chmod 666 /app/edutrack.db

# Set environment variables
ENV PORT=8080
ENV HOST=0.0.0.0
ENV VERSION=${VERSION}
ENV GIT_PYTHON_REFRESH=quiet

# Add healthcheck
HEALTHCHECK --interval=3s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# Expose the port
EXPOSE ${PORT}

# Switch to non-root user
USER nobody

# Command to run the application
CMD ["python", "server.py"]
