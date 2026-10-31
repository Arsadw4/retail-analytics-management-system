"""
core/
Cross-cutting application concerns that every layer depends on:
security, RBAC, audit logging, structured logging, and shared
Flask extension instances.

This package intentionally has NO dependency on routes/ or
services/, so it can be imported anywhere without circular imports.
"""
