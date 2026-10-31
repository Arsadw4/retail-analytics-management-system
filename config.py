"""
config.py
Environment-driven configuration.

Why this changed from the original:
The old config.py hardcoded the MySQL password and Flask SECRET_KEY
directly in source control. This file now reads their names from the
environment. Copy `.env.example` to `.env` and configure the values
there once for local development.

Three config classes (Development / Testing / Production) let
create_app() pick sensible defaults per environment via FLASK_ENV,
instead of one config used everywhere with debug=True baked in
(which is itself a production security risk -- Flask's debug mode
exposes an interactive Python console on unhandled exceptions).
"""

import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()  # reads a local .env file in dev; in production, real
                # env vars are injected by the host/orchestrator instead


def _require_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or not value.strip():
        raise RuntimeError(
            f"Required environment variable '{name}' is not set. "
            f"Set it in the process environment or a local .env file; see .env.example."
        )
    if name == "SECRET_KEY":
        normalized = value.strip().lower()
        if len(normalized) < 32 or any(
            marker in normalized for marker in ("placeholder", "replace", "change-me", "your-secret")
        ):
            raise RuntimeError(
                "SECRET_KEY must be a private random value of at least 32 characters; "
                "replace the placeholder in .env before starting the application."
            )
    return value


class BaseConfig:
    # --- Secrets (never hardcode; always from environment) ---
    SECRET_KEY = _require_env("SECRET_KEY")

    MYSQL_HOST = _require_env("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))
    MYSQL_USER = _require_env("MYSQL_USER")
    MYSQL_PASSWORD = _require_env("MYSQL_PASSWORD")
    MYSQL_DB = _require_env("MYSQL_DB", "enterprise_retail_management")

    # --- Connection pool ---
    DB_POOL_MAX_CONNECTIONS = int(os.environ.get("DB_POOL_MAX_CONNECTIONS", 20))
    DB_POOL_MIN_CACHED = int(os.environ.get("DB_POOL_MIN_CACHED", 2))
    DB_POOL_MAX_CACHED = int(os.environ.get("DB_POOL_MAX_CACHED", 10))

    # --- Session / cookie security ---
    SESSION_COOKIE_HTTPONLY = True       # JS (and therefore XSS) can't read the cookie
    SESSION_COOKIE_SAMESITE = "Lax"      # baseline CSRF mitigation for cross-site requests
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=int(os.environ.get("SESSION_TIMEOUT_MINUTES", 60)))
    # Refresh the permanent cookie on activity; UserSession also enforces
    # the same idle timeout server-side so browser cookie persistence cannot
    # keep a revoked or expired session authenticated.
    SESSION_REFRESH_EACH_REQUEST = True

    # --- Rate limiting storage. In production, point this at Redis
    # so limits are shared across multiple Gunicorn worker processes
    # instead of each worker tracking its own in-memory counters. ---
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    LOG_DIR = os.environ.get("LOG_DIR", "logs")

    # --- Email (Phase 4: invoice emailing) ---
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
    SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "billing@example.com")

    # --- Phase 9: security / backup / performance ---
    SESSION_TIMEOUT_MINUTES = int(os.environ.get("SESSION_TIMEOUT_MINUTES", 60))
    BACKUP_DIR = os.environ.get("BACKUP_DIR", "backups")
    MYSQL_CLIENT_BIN_DIR = os.environ.get("MYSQL_CLIENT_BIN_DIR", "")  # optional, if mysqldump/mysql aren't on PATH
    MFA_ISSUER_NAME = os.environ.get("MFA_ISSUER_NAME", "Retail Analytics System")

    # --- File upload limits (defense against unbounded upload DoS) ---
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB
    UPLOAD_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # allow plain HTTP on localhost


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False  # simplifies posting test requests without a token


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # cookie only sent over HTTPS


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config():
    env = os.environ.get("FLASK_ENV", "development")
    return CONFIG_MAP.get(env, DevelopmentConfig)
