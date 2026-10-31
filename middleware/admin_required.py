"""
middleware/admin_required.py
Backward-compatible wrapper. Prefer importing role_required directly
from core.rbac in new code
this module exists so routes written
against the original middleware/admin_required.py path don't break.
"""

from core.rbac import role_required

admin_required = role_required("admin")
