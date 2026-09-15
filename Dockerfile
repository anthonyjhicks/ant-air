# Ant Air production image.
#
#   docker build -t ant-air .
#   docker run -p 8000:8000 -e DATABASE_URL=postgresql://... -e SECRET_KEY=... ant-air
#
# Runs database migrations on start (set AUTO_MIGRATE=false to skip, e.g. when
# an orchestrator runs them separately), then serves the app with Gunicorn as
# a non-root user on port 8000. The MCP server uses the same image:
#   docker run -e MCP_TRANSPORT=streamable-http ant-air python -m app.mcp_server
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AUTO_MIGRATE=true \
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh \
    && useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn"]
