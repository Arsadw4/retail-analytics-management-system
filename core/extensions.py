"""
Shared Flask extension instances.

Why a separate module: Flask extensions must be instantiated once at
import time and then bound to the app inside create_app() via
.init_app(app). Instantiating them here (instead of inside app.py)
avoids circular imports -- any module (routes, services, middleware)
can `from core.extensions import csrf, limiter` without importing
app.py itself.
"""

from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# CSRF protection for every POST/PUT/PATCH/DELETE form submission.
# Flask-WTF validates the `csrf_token` hidden field automatically
# once csrf.init_app(app) is called in the app factory.
csrf = CSRFProtect()

# Rate limiting -- primarily used to slow down credential-stuffing /
# brute-force attacks against /login, but available for any route
# that needs throttling (e.g. password reset, public APIs).
# storage_uri defaults to in-memory; for a multi-process production
# deployment behind Gunicorn, point this at Redis (see config.py).
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],  # no global default -- apply per-route
)
