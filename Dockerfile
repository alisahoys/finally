# Stage 1: build the static Next.js export
FROM node:24-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: FastAPI serving the API and the export.
# Code lives at /app/backend so DB_PATH resolves to the /app/db volume.
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/app ./app
COPY backend/db ./db
RUN uv sync --frozen --no-dev
COPY --from=frontend /frontend/out ./static
RUN mkdir -p /app/db
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
