"""
database/db.py
Database connection layer.

Why PyMySQL with DBUtils pooling instead of the original
Flask-MySQLdb setup:
- Flask-MySQLdb (a thin wrapper over mysqlclient) opens ONE
  connection per Flask app context and has no pooling story --
  fine for a single-user dev server, not for concurrent enterprise
  traffic where many requests need a DB connection at once.
- mysqlclient also requires compiling C extensions against
  libmysqlclient, which complicates deployment (Docker images,
  Windows dev machines). PyMySQL is pure-Python and drop-in
  compatible with the DB-API 2.0 interface the rest of the code
  already uses (cursor.execute, fetchone, fetchall).
- DBUtils' PooledDB gives us a real connection pool with a
  configurable ceiling, so a traffic spike can't exhaust MySQL's
  max_connections and take the whole app down.

get_db_cursor() is a context manager: it hands out a connection from
the pool, commits on success, rolls back on any exception, and
always returns the connection to the pool -- callers never manage
connection lifecycle themselves, which is what caused inconsistent
cur.close() handling (and occasional leaks) in the original models.
"""

import logging
from contextlib import contextmanager

import pymysql
from dbutils.pooled_db import PooledDB
from flask import g

logger = logging.getLogger("app")

_pool: PooledDB | None = None


def init_db_pool(app):
    """Call once from the application factory (create_app)."""
    global _pool
    _pool = PooledDB(
        creator=pymysql,
        maxconnections=app.config.get("DB_POOL_MAX_CONNECTIONS", 20),
        mincached=app.config.get("DB_POOL_MIN_CACHED", 2),
        maxcached=app.config.get("DB_POOL_MAX_CACHED", 10),
        blocking=True,
        ping=1,  # PING before each use; transparently reconnects dead connections
        host=app.config["MYSQL_HOST"],
        port=app.config.get("MYSQL_PORT", 3306),
        user=app.config["MYSQL_USER"],
        password=app.config["MYSQL_PASSWORD"],
        database=app.config["MYSQL_DB"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,
        autocommit=False,
    )
    logger.info("Database connection pool initialized.")
    _teardown_legacy_connection(app)


@contextmanager
def get_db_cursor(commit: bool = True):
    """
    Usage:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM products WHERE product_id=%s", (pid,))
            row = cur.fetchone()

    For read-only queries pass commit=False to skip the (harmless but
    unnecessary) commit call.
    """
    if _pool is None:
        raise RuntimeError(
            "Database pool not initialized. Call init_db_pool(app) in create_app()."
        )

    conn = _pool.connection()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Database operation failed, transaction rolled back.")
        raise
    finally:
        cur.close()
        conn.close()  # returns the connection to the pool, does not actually close it


# -----------------------------------------------------------------
# Backward-compatibility shim
# -----------------------------------------------------------------
# The original models/*.py were written against Flask-MySQLdb's API:
#     from database.db import mysql
#     cur = mysql.connection.cursor()
#     ... cur.execute(...); mysql.connection.commit(); cur.close()
#
# Rewriting all nine model files to the new get_db_cursor() context
# manager in one pass (alongside the RBAC/security work) would be a
# large, easy-to-botch diff touching business logic unrelated to
# Phase 1's scope. Instead, `mysql` below reproduces the same
# `.connection.cursor()` surface, backed by the SAME connection pool,
# so every existing model file keeps working unmodified today.
#
# The connection is cached on Flask's `g` so multiple `mysql.connection`
# accesses within one request share a single connection (matching the
# original library's behavior), and is returned to the pool
# automatically when the request ends via the teardown handler
# registered in `init_db_pool`.
#
# This is intentionally temporary: as each model is migrated to
# get_db_cursor() during Phase 3 (Core modules), its `mysql` import
# should be removed. New code should use get_db_cursor() directly.
class _LegacyConnectionProxy:
    """Mimics `mysql.connection` -- returns a pooled connection cached per-request."""

    def _get(self):
        if "_legacy_db_conn" not in g:
            g._legacy_db_conn = _pool.connection()
        return g._legacy_db_conn

    def cursor(self, *args, **kwargs):
        return self._get().cursor(*args, **kwargs)

    def commit(self):
        self._get().commit()

    def rollback(self):
        self._get().rollback()


class _LegacyMySQL:
    @property
    def connection(self):
        if _pool is None:
            raise RuntimeError(
                "Database pool not initialized. Call init_db_pool(app) in create_app()."
            )
        return _LegacyConnectionProxy()


mysql = _LegacyMySQL()


def _teardown_legacy_connection(app):
    @app.teardown_appcontext
    def _close_legacy_conn(exception=None):
        conn = g.pop("_legacy_db_conn", None)
        if conn is not None:
            if exception is not None:
                try:
                    conn.rollback()
                except Exception:
                    logger.exception("Failed to roll back legacy connection on teardown.")
            conn.close()  # returns connection to the pool
