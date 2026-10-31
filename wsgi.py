"""
wsgi.py
Production WSGI entry point. Points Gunicorn (or any other WSGI
server) at the same `app` object app.py already builds via
create_app() -- this file exists as the conventional, explicit
production entrypoint name so deployment tooling (Dockerfile,
gunicorn.conf.py, systemd unit) doesn't need to know app.py's
internals, and so `python app.py`'s `if __name__ == "__main__"` dev-
server block is never accidentally what production points at.

Usage:
    gunicorn --config deploy/gunicorn.conf.py wsgi:app
"""

from app import app

if __name__ == "__main__":
    app.run()
