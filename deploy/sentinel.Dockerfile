FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy source
COPY src/ src/
COPY pyproject.toml .

# Install package (stdlib-only, no deps beyond setuptools)
RUN pip install --no-cache-dir -e . --no-build-isolation

# Default env
ENV SENTINEL_PORT=8090
ENV SENTINEL_DB_PATH=/data/sentinel.db
ENV SENTINEL_OTEL_ENDPOINT=http://signoz-ingester:4317
ENV PYTHONUNBUFFERED=1

EXPOSE 8090

VOLUME ["/data"]

ENTRYPOINT ["python3", "-m", "sentinel.app"]
CMD []
