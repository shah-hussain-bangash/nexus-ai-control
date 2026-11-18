FROM node:22-alpine AS ui
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 nexus
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=nexus:nexus backend/nexus ./nexus
COPY --from=ui --chown=nexus:nexus /build/dist /app/frontend/dist
RUN mkdir -p /app/backend/data && chown nexus:nexus /app/backend/data
USER nexus
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "nexus.main:app", "--host", "0.0.0.0", "--port", "8000"]
