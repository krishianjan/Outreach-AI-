# Dockerfile
# Stage 1: Build React frontend
# Stage 2: Python FastAPI backend serving the built frontend
#
# Result: ONE container, ONE URL, full-stack demo.

# ── Stage 1: Build React ───────────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Install pnpm (project uses pnpm)
RUN npm install -g pnpm@latest --quiet

# Install JS dependencies
COPY frontend/package.json ./
COPY frontend/pnpm-lock.yaml* ./
RUN pnpm install --no-frozen-lockfile

# Copy source and build
# VITE_API_URL="" → relative URL → same origin → no CORS needed in production
COPY frontend/ .
RUN VITE_API_URL="" pnpm build

# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System dependencies for lxml, httpx, dns
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev libxml2-dev libxslt-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt

# Copy backend source (the .dockerignore excludes .env, node_modules, __pycache__)
COPY . .

# Copy the built React app from stage 1
# This overwrites the empty frontend/dist/ directory with the real build
COPY --from=frontend-builder /build/dist ./frontend/dist

# HF Spaces requires port 7860
EXPOSE 7860

# Start FastAPI (which serves both /api/* and the React frontend)
CMD ["python", "api_routes.py"]