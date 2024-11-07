# Build stage for React frontend
FROM node:18 AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install -g npm@latest && npm install && npm audit fix --force
COPY frontend/ ./
RUN npm run build

# Final stage
FROM python:3.13-slim
WORKDIR /app

# Copy frontend build
COPY --from=frontend-builder /app/frontend/build /app/frontend/build

# Install backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy server script
COPY server.py .

# Create directory for SQLite database and set permissions
RUN touch /app/edutrack.db && \
    chown -R nobody:nogroup /app && \
    chmod 666 /app/edutrack.db

# Set environment variables
ENV PORT=8080
ENV HOST=0.0.0.0

# Switch to non-root user
USER nobody

# Expose the port
EXPOSE 8080

# Command to run the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
