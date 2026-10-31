"""
middleware/employee_required.py
Backward-compatible wrapper -- grants access to employee, manager,
and admin roles (i.e. anyone with a valid staff account), mirroring
the original intent of "employee_required" as "any logged-in staff
member," not "employee role only."
"""

from core.rbac import role_required

employee_required = role_required("employee", "manager", "admin")
