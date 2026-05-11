# Stage 1: Build React frontend
FROM node:20-slim AS frontend-builder
WORKDIR /build
RUN npm install -g pnpm
COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN pnpm install --no-frozen-lockfile
COPY frontend/ .
RUN VITE_API_URL="" pnpm build

# Stage 2: Python backend
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend-builder /build/dist ./frontend/dist
EXPOSE 7860
CMD ["python", "api_routes.py"]
