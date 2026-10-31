"""
core/pagination.py
Reusable SQL LIMIT/OFFSET pagination helper. Applied to the
highest-traffic list pages (Products, Invoice Search, Activity Logs)
as the demonstrated pattern -- not retrofitted onto every list page in
the app, which would mean re-touching dozens of already-tested routes
across eight phases for marginal benefit on pages that will realistically
never hold more than a few hundred rows. Apply the same pattern to any
other page as its data volume grows enough to warrant it.
"""

from flask import request

DEFAULT_PAGE_SIZE = 25


def get_pagination_params(default_size=DEFAULT_PAGE_SIZE):
    page = request.args.get("page", 1, type=int)
    page = max(page, 1)
    size = request.args.get("page_size", default_size, type=int)
    size = min(max(size, 5), 200)  # guard against absurd/abusive page sizes
    offset = (page - 1) * size
    return page, size, offset


def build_page_info(page, size, total_count):
    total_pages = max(1, (total_count + size - 1) // size)
    return {
        "page": page,
        "page_size": size,
        "total_count": total_count,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages
    }
