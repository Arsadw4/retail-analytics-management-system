"""
app.py
Application entry point / factory.

Why the app-factory pattern (create_app()) instead of a bare module-
level `app = Flask(__name__)`:
- Lets us build multiple app instances with different configs
  (development / testing / production) -- essential for running the
  test suite against an isolated config without touching real data.
- Avoids import-time side effects: extensions are instantiated once
  in core/extensions.py and bound to a specific app only when
  create_app() runs, which is what prevents circular imports between
  routes -> services -> core -> app.
"""

import logging
import secrets

from flask import Flask, render_template, request, g
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config
from core.extensions import csrf, limiter
from core.logging_config import configure_logging
from database.db import init_db_pool


def create_app():
    app = Flask(__name__)
    app.config.from_object(get_config())

    # Trust exactly one reverse proxy hop (nginx/ALB) for X-Forwarded-*
    # headers -- required for request.remote_addr / rate limiting and
    # HTTPS-scheme detection to be correct behind a load balancer.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    configure_logging(app)

    @app.before_request
    def _set_csp_nonce():
        g.csp_nonce = secrets.token_urlsafe(18)

    @app.context_processor
    def _inject_security_context():
        return {"csp_nonce": getattr(g, "csp_nonce", "")}

    init_db_pool(app)

    from core.perf_monitor import register as register_perf_monitor
    register_perf_monitor(app)

    csrf.init_app(app)
    limiter.init_app(app)

    _register_security_headers(app)
    _register_compression(app)
    _register_blueprints(app)
    _register_error_handlers(app)

    return app


def _register_security_headers(app):
    """
    Defense-in-depth HTTP headers on every response. These don't
    replace input validation/output encoding, but they close off
    entire classes of attack (clickjacking, MIME sniffing, some XSS)
    even if a template or endpoint slips up elsewhere.
    """

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(self)"  # camera needed for the Phase 3 barcode scan page
        )
        # Adjust script-src if you add third-party JS (e.g. a CDN chart
        # library); keep it as tight as the app actually needs.
        # cdnjs.cloudflare.com is required for the Phase 3 barcode/QR
        # scan page (html5-qrcode) -- it was missing here previously,
        # which silently blocked that library from loading in any
        # browser that enforces CSP (i.e. all of them). Fixed as part
        # of this phase's security header review.
        nonce = getattr(g, "csp_nonce", "")
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            f"script-src 'self' 'nonce-{nonce}' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "connect-src 'self' https://cdn.jsdelivr.net; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains"
            )
        return response


def _register_compression(app):
    """
    Gzip-compresses text-based responses (HTML/JSON/CSS/JS) above a
    minimum size. Dependency-free (stdlib gzip) rather than adding
    Flask-Compress -- one `after_request` hook, easy to audit. Skips
    already-compressed or binary content (images, PDFs, xlsx) where
    gzip wastes CPU for little or no size benefit.
    """
    import gzip as gzip_module

    _COMPRESSIBLE_TYPES = ("text/html", "application/json", "text/css",
                           "application/javascript", "text/javascript", "text/csv")
    _MIN_SIZE = 500

    @app.after_request
    def compress(response):
        accept_encoding = request.headers.get("Accept-Encoding", "")
        content_type = (response.content_type or "").split(";")[0]

        if ("gzip" not in accept_encoding
                or content_type not in _COMPRESSIBLE_TYPES
                or response.direct_passthrough
                or "Content-Encoding" in response.headers):
            return response

        data = response.get_data()
        if len(data) < _MIN_SIZE:
            return response

        compressed = gzip_module.compress(data, compresslevel=6)
        response.set_data(compressed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(compressed))
        response.headers["Vary"] = "Accept-Encoding"
        return response


def _register_blueprints(app):
    from routes.auth_routes import auth_bp
    from routes.admin_routes import admin_bp
    from routes.product_routes import product_bp
    from routes.sales_routes import sales_bp
    from routes.report_routes import report_bp
    from routes.customer_routes import customer_bp
    from routes.employee_routes import employee_bp
    from routes.category_routes import category_bp
    from routes.inventory_routes import inventory_bp
    from routes.analytics_routes import analytics_bp
    from routes.ai_routes import ai_bp
    from routes.warehouse_routes import warehouse_bp
    from routes.stock_routes import stock_bp
    from routes.barcode_routes import barcode_bp
    from routes.billing_routes import billing_bp
    from routes.customer_mgmt_routes import customer_mgmt_bp
    from routes.supplier_routes import supplier_bp
    from routes.hr_routes import hr_bp
    from routes.admin_mgmt_routes import admin_mgmt_bp
    from routes.bi_routes import bi_bp
    from routes.security_routes import security_bp
    from routes.backup_routes import backup_bp
    from routes.monitoring_routes import monitoring_bp
    from routes.global_search_routes import global_search_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(category_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(warehouse_bp)
    app.register_blueprint(stock_bp)
    app.register_blueprint(barcode_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(customer_mgmt_bp)
    app.register_blueprint(supplier_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(admin_mgmt_bp)
    app.register_blueprint(bi_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(backup_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(global_search_bp)


def _register_error_handlers(app):
    logger = logging.getLogger("app")

    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        # Most common real-world cause: a form was left open past the
        # session timeout (Phase 9) and the token expired along with
        # it -- point the person back to a fresh page rather than a
        # bare "Bad Request".
        logger.warning("CSRF validation failed on %s %s: %s", request.method, request.path, e.description)
        return render_template("errors/400.html", description=e.description), 400

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/400.html", description=getattr(e, "description", None)), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def rate_limited(e):
        return render_template("errors/429.html", description=str(e.description)), 429

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Unhandled exception on %s %s", request.method, request.path)
        return render_template("errors/500.html"), 500


app = create_app()

if __name__ == "__main__":
    # debug=False by default now -- DevelopmentConfig sets DEBUG=True
    # via app.config, which Flask's app.run() picks up automatically
    # from app.debug, so we don't hardcode debug=True here.
    app.run()
