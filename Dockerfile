# ---- Stage 1: build the Vue 3 frontend ----
FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python 3 backend (serves API + SPA) ----
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=fe /fe/dist ./web

# /data is a volume: store/ wm/ onedl.db live here
ENV ONEDL_BASE=/data \
    ONEDL_HOST=0.0.0.0 \
    ONEDL_PORT=8777 \
    ONEDL_WEB=/app/web \
    ONEDL_PUBLIC_HOST=http://117.72.15.132

EXPOSE 8777
VOLUME ["/data"]
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 8777"]
