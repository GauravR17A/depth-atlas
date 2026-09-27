FROM node:22-bookworm-slim AS frontend
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-fund
COPY web/ ./
COPY api/release.json /build/api/release.json
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home ocean
COPY api/ ./api/
COPY science/ ./science/
COPY adapters/ ./adapters/
COPY casepacks/ ./casepacks/
COPY --from=frontend /build/web/dist ./web/dist
RUN python -m science.publication --candidate casepacks --manifest api/publication.json
USER ocean
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
