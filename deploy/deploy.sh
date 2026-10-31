#!/usr/bin/env bash
#
# deploy/deploy.sh
# Deploys/updates this app on a server that already has Docker +
# Docker Compose installed. Idempotent -- safe to re-run for updates.
#
# Usage: ./deploy/deploy.sh

set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Copy .env.example to .env and configure it once."
    exit 1
fi

echo "==> Pulling latest images / rebuilding app image"
docker compose build

echo "==> Starting/updating services"
docker compose up -d

echo "==> Waiting for MySQL to be healthy"
until docker compose exec -T mysql mysqladmin ping -h localhost --silent; do
    sleep 2
done

echo "==> Verifying database migrations are applied"
docker compose exec -T app python scripts/verify_migrations.py

echo "==> Deployment complete. Check status with: docker compose ps"
echo "==> Tail logs with: docker compose logs -f app"
