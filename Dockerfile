# --- Stage 1: Build Frontend ---
FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN npm install -g pnpm && pnpm install
COPY frontend ./
RUN pnpm build

# --- Stage 2: Final Image ---
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libnss3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Copy the built assets from the first stage
COPY --from=frontend-builder /build/dist ./frontend/dist

EXPOSE 7860
CMD ["python", "api_routes.py"]
