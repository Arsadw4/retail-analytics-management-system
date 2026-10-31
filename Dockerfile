# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# mysqldump/mysql client tools (Phase 9 backup/restore) +
# build essentials for any package that needs to compile.
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-mysql-client \
        gcc \
        pkg-config \
        default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY . .

# Non-root user -- never run the app as root in production.
RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/logs /app/backups /app/static/uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/login', timeout=3)" || exit 1

CMD ["gunicorn", "--config", "deploy/gunicorn.conf.py", "wsgi:app"]
