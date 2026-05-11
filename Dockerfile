# Stage 1: Build React Frontend
FROM node:20-slim AS build-step
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install
COPY frontend ./
RUN pnpm build

# Stage 2: Build Python Backend
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    librandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY Requirements.txt .
RUN pip install --no-cache-dir -r Requirements.txt
RUN pip install google-generativeai scrapegraphai httpx

COPY . .
COPY --from=build-step /app/frontend/dist ./frontend/dist

ENV DRY_RUN=false
ENV PORT=7860

CMD ["python", "api_routes.py"]