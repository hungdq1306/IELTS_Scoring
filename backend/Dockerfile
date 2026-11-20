FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm install --ignore-scripts
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && useradd --create-home fogwrite
COPY backend/ backend/
# Only the frozen, required calibration artifact ships; no lecturer exports or raw datasets.
COPY artifacts/dataset_v1/seed.jsonl artifacts/dataset_v1/seed.jsonl
COPY --from=frontend /build/dist/ frontend/dist/
USER fogwrite
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.pilot:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
