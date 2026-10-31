"""
database/errors.py
Friendly, catchable exceptions for common MySQL constraint violations.

Why this exists: several delete/insert operations in the original code
had no error handling at all around foreign-key and unique-constraint
violations. Example: deleting a category that still has products
pointing at it raises a raw pymysql.err.IntegrityError, which was
completely unhandled -- Flask would return a bare 500 with a stack
trace instead of the person seeing "this category still has products
assigned to it." Wrapping the raw driver exception into one of these
two types lets routes catch a specific, meaningful error and show a
helpful flash message instead.
"""

import pymysql


class DatabaseError(Exception):
    """Base class for translated database errors."""


class ReferentialIntegrityError(DatabaseError):
    """
    Raised when an INSERT/UPDATE/DELETE would violate a foreign key
    constraint -- most commonly: deleting a parent row (category,
    product, customer) that child rows still reference.
    """


class DuplicateEntryError(DatabaseError):
    """Raised when an INSERT/UPDATE would violate a UNIQUE constraint."""


# MySQL error codes we translate. Anything else is left as-is and
# propagates normally (caught by the global 500 handler + logged).
_FK_VIOLATION_CODES = {1451, 1452}  # 1451: on DELETE/UPDATE, 1452: on INSERT/UPDATE
_DUPLICATE_ENTRY_CODE = 1062


def translate_integrity_error(exc: Exception):
    """
    Call from an `except pymysql.err.IntegrityError as e:` block:

        try:
            ...
        except pymysql.err.IntegrityError as e:
            translate_integrity_error(e)   # always raises

    Always raises -- either a friendly DatabaseError subclass, or the
    original exception if we don't recognize the error code, so
    nothing is ever silently swallowed.
    """
    if isinstance(exc, pymysql.err.IntegrityError) and exc.args:
        code = exc.args[0]
        if code in _FK_VIOLATION_CODES:
            raise ReferentialIntegrityError(
                "This record is still referenced by other data (for example, "
                "existing products, sales, or inventory records) and can't be "
                "deleted or changed until those references are removed first."
            ) from exc
        if code == _DUPLICATE_ENTRY_CODE:
            raise DuplicateEntryError(
                "A record with that unique value (e.g. email, SKU, or barcode) "
                "already exists."
            ) from exc

    raise exc
