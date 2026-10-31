"""
core/logging_config.py
Structured, rotating application logging.

Why: the original app had no logging configuration at all -- errors
either crashed with Flask's debug traceback (dev only) or vanished
silently in production. This sets up:
  - a rotating file handler (logs/app.log), so disk usage is bounded
  - a console handler for container/stdout log aggregation (e.g.
    CloudWatch, ELK, whatever the deployment target is)
  - one consistent log format including request context where possible
Call configure_logging(app) once from create_app().
"""

import logging
import os
from logging.handlers import RotatingFileHandler


def configure_logging(app):
    log_dir = app.config.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB per file
        backupCount=10,             # keep 10 rotated files (~50 MB ceiling)
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)

    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Route Flask/Werkzeug's own logger through the same handlers so
    # request logs and application logs end up in one place.
    app.logger.handlers = logger.handlers
    app.logger.setLevel(logger.level)

    return logger
