"""Real-MySQL end-to-end checks for employee and account authentication.

These checks are opt-in and refuse to run unless MYSQL_DB ends in ``_test``.
They create disposable accounts through the application routes and inspect the
resulting database rows; they do not replace the database with mocks.
"""

import os
import re
import uuid
from datetime import timedelta

import pytest


_RUN_DATABASE_TESTS = os.environ.get("RUN_DB_INTEGRATION") == "1"
_DATABASE_NAME = os.environ.get("MYSQL_DB", "")

if _RUN_DATABASE_TESTS and not _DATABASE_NAME.endswith("_test"):
    raise RuntimeError("Authentication integration tests require MYSQL_DB to end in '_test'.")

pytestmark = pytest.mark.skipif(
    not _RUN_DATABASE_TESTS,
    reason="Set RUN_DB_INTEGRATION=1 and use a disposable MYSQL_DB ending in '_test'.",
)

_ADMIN_EMAIL = "admin@example.com"
_ADMIN_PASSWORD = f"AuditAdmin!{uuid.uuid4().hex[:16]}"
_CLIENT_NUMBER = 0


@pytest.fixture(scope="module")
def app():
    from app import create_app
    from core.security import hash_password
    from database.db import get_db_cursor
    from models.user_model import User

    test_app = create_app()
    test_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SESSION_TIMEOUT_MINUTES=2,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=2),
    )

    with test_app.app_context():
        admin = User.get_user_by_email(_ADMIN_EMAIL)
        if admin is None:
            raise AssertionError("The disposable schema is missing its seeded admin account.")
        User.update_password(admin[0], hash_password(_ADMIN_PASSWORD))
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE users SET status='active', mfa_enabled=FALSE, mfa_secret=NULL "
                "WHERE user_id=%s",
                (admin[0],),
            )

    return test_app


def _new_client(app):
    global _CLIENT_NUMBER
    _CLIENT_NUMBER += 1
    client = app.test_client()
    client.environ_base["REMOTE_ADDR"] = f"192.0.2.{(_CLIENT_NUMBER % 200) + 1}"
    return client


@pytest.fixture
def admin_client(app):
    client = _new_client(app)
    response = client.post(
        "/login",
        data={"email": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/dashboard")
    return client


def _create_employee(app, admin_client, suffix=None):
    suffix = suffix or uuid.uuid4().hex[:12]
    email = f"auth-{suffix}@example.test"
    password = f"Employee!{suffix}9"
    name = f"Auth Test {suffix}"
    response = admin_client.post(
        "/admin/add-employee",
        data={
            "name": name,
            "email": email,
            "phone": "+1 555 010 2099",
            "designation": "Authentication QA",
            "salary": "42000.50",
            "password": password,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302, response.data.decode("utf-8", errors="replace")
    assert response.headers["Location"].endswith("/admin/hr/employees")

    from database.db import get_db_cursor
    from models.user_model import User

    with app.app_context():
        user = User.get_user_by_email(email)
        assert user is not None
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT employee_id FROM employees WHERE user_id=%s", (user[0],))
            employee = cursor.fetchone()
    assert employee is not None
    return {
        "user_id": user[0],
        "employee_id": employee[0],
        "email": email,
        "password": password,
        "name": name,
    }


def _login(app, email, password, **form_values):
    client = _new_client(app)
    data = {"email": email, "password": password, **form_values}
    response = client.post("/login", data=data, follow_redirects=False)
    return client, response


def _query_one(app, query, params=()):
    from database.db import get_db_cursor

    with app.app_context():
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()


def test_multiple_employee_accounts_hash_login_dashboard_and_logout(app, admin_client):
    from core.security import verify_password

    employees = [_create_employee(app, admin_client) for _ in range(3)]

    for index, employee in enumerate(employees):
        stored = _query_one(
            app,
            "SELECT password, status, role FROM users WHERE user_id=%s",
            (employee["user_id"],),
        )
        assert stored[0] != employee["password"]
        assert verify_password(stored[0], employee["password"])
        assert stored[1:] == ("active", "employee")

        email = employee["email"].upper() if index == 0 else employee["email"]
        client, response = _login(app, email, employee["password"])
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/employee/dashboard")
        with client.session_transaction() as login_session:
            assert login_session["user_id"] == employee["user_id"]
            assert login_session["role"] == "employee"
            assert len(login_session["session_token"]) == 64

        dashboard = client.get("/employee/dashboard")
        assert dashboard.status_code == 200
        assert employee["name"].encode() in dashboard.data
        assert _query_one(
            app,
            "SELECT COUNT(*) FROM user_sessions WHERE user_id=%s",
            (employee["user_id"],),
        )[0] == 1

        assert client.get("/logout").status_code == 405
        logout = client.post("/logout")
        assert logout.status_code == 302
        assert _query_one(
            app,
            "SELECT COUNT(*) FROM user_sessions WHERE user_id=%s",
            (employee["user_id"],),
        )[0] == 0
        assert client.get("/employee/dashboard").status_code == 302


def test_bad_missing_inactive_locked_and_sql_injection_credentials(app, admin_client):
    employee = _create_employee(app, admin_client)

    unknown, response = _login(app, "' OR 1=1 -- ", "any-password")
    assert response.status_code == 200
    assert b"Invalid Email or Password" in response.data
    with unknown.session_transaction() as login_session:
        assert "user_id" not in login_session

    missing, response = _login(app, "", "")
    assert response.status_code == 200
    assert b"Invalid Email or Password" in response.data
    with missing.session_transaction() as login_session:
        assert "user_id" not in login_session

    wrong_password_client = _new_client(app)
    for _ in range(5):
        response = wrong_password_client.post(
            "/login",
            data={"email": employee["email"], "password": "WrongPassword!"},
        )
        assert response.status_code == 200
        assert b"Invalid Email or Password" in response.data

    locked = _query_one(
        app,
        "SELECT failed_login_attempts, locked_until FROM users WHERE user_id=%s",
        (employee["user_id"],),
    )
    assert locked[0] == 5
    assert locked[1] is not None

    locked_client, response = _login(app, employee["email"], employee["password"])
    assert response.status_code == 200
    assert b"Invalid Email or Password" in response.data
    with locked_client.session_transaction() as login_session:
        assert "user_id" not in login_session

    from database.db import get_db_cursor

    with app.app_context():
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE users SET failed_login_attempts=0, locked_until=NULL, status='inactive' "
                "WHERE user_id=%s",
                (employee["user_id"],),
            )
    inactive_client, response = _login(app, employee["email"], employee["password"])
    assert response.status_code == 200
    assert b"Invalid Email or Password" in response.data
    with inactive_client.session_transaction() as login_session:
        assert "user_id" not in login_session


def test_activation_permissions_and_existing_session_revocation(app, admin_client):
    employee = _create_employee(app, admin_client)
    employee_client, login_response = _login(app, employee["email"], employee["password"])
    assert login_response.status_code == 302
    assert employee_client.get("/employee/dashboard").status_code == 200

    from models.user_model import User

    user = User.get_user_by_id(employee["user_id"])
    edit_url = f"/admin/edit-user/{employee['user_id']}"
    edit_page = admin_client.get(edit_url)
    assert edit_page.status_code == 200
    assert re.search(rb'<option value="employee" selected', edit_page.data)

    deactivated = admin_client.post(
        edit_url,
        data={"full_name": user[1], "email": user[2], "role": "employee", "status": "inactive"},
    )
    assert deactivated.status_code == 302
    assert _query_one(
        app,
        "SELECT status FROM users WHERE user_id=%s",
        (employee["user_id"],),
    )[0] == "inactive"
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM user_sessions WHERE user_id=%s",
        (employee["user_id"],),
    )[0] == 0
    assert employee_client.get("/employee/dashboard").status_code == 302

    inactive_client, response = _login(app, employee["email"], employee["password"])
    assert response.status_code == 200
    assert b"Invalid Email or Password" in response.data

    reactivated = admin_client.post(
        edit_url,
        data={"full_name": user[1], "email": user[2], "role": "employee", "status": "active"},
    )
    assert reactivated.status_code == 302
    active_client, response = _login(app, employee["email"], employee["password"])
    assert response.status_code == 302
    assert active_client.get("/employee/dashboard").status_code == 200
    assert active_client.get("/admin/users").status_code == 403


def test_password_change_admin_reset_and_expired_session_rejection(app, admin_client):
    from core.security import verify_password

    employee = _create_employee(app, admin_client)
    first_client, first_login = _login(app, employee["email"], employee["password"])
    second_client, second_login = _login(app, employee["email"], employee["password"])
    assert first_login.status_code == second_login.status_code == 302

    changed_password = f"Changed!{uuid.uuid4().hex[:12]}9"
    changed = first_client.post(
        "/employee/change-password",
        data={
            "old_password": employee["password"],
            "new_password": changed_password,
            "confirm_password": changed_password,
        },
    )
    assert changed.status_code == 302
    assert changed.headers["Location"].endswith("/login")
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM user_sessions WHERE user_id=%s",
        (employee["user_id"],),
    )[0] == 0
    stored_hash = _query_one(
        app,
        "SELECT password FROM users WHERE user_id=%s",
        (employee["user_id"],),
    )[0]
    assert verify_password(stored_hash, changed_password)
    assert not verify_password(stored_hash, employee["password"])
    assert second_client.get("/employee/dashboard").status_code == 302

    new_client, response = _login(app, employee["email"], changed_password)
    assert response.status_code == 302
    assert new_client.get("/employee/dashboard").status_code == 200

    reset_password = f"Reset!{uuid.uuid4().hex[:12]}9"
    reset = admin_client.post(
        f"/admin/users/{employee['user_id']}/reset-password",
        data={"new_password": reset_password, "confirm_password": reset_password},
    )
    assert reset.status_code == 302
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM user_sessions WHERE user_id=%s",
        (employee["user_id"],),
    )[0] == 0
    assert new_client.get("/employee/dashboard").status_code == 302
    reset_client, response = _login(app, employee["email"], reset_password)
    assert response.status_code == 302
    assert reset_client.get("/employee/dashboard").status_code == 200

    token = _query_one(
        app,
        "SELECT session_token FROM user_sessions WHERE user_id=%s",
        (employee["user_id"],),
    )[0]
    with app.app_context():
        from database.db import get_db_cursor
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE user_sessions SET last_seen_at=NOW()-INTERVAL 3 MINUTE "
                "WHERE session_token=%s",
                (token,),
            )
    assert reset_client.get("/employee/dashboard").status_code == 302
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM user_sessions WHERE session_token=%s",
        (token,),
    )[0] == 0


def test_remember_me_and_safe_redirect(app):
    employee_email = f"remember-{uuid.uuid4().hex[:10]}@example.test"
    employee_password = f"Remember!{uuid.uuid4().hex[:12]}9"

    from core.security import hash_password
    from models.user_model import User

    with app.app_context():
        user_id = User.create_user(
            "Remember QA", employee_email, hash_password(employee_password), "employee"
        )

    remembered, response = _login(app, employee_email, employee_password, remember="on")
    assert response.status_code == 302
    set_cookie = response.headers.get("Set-Cookie", "")
    assert "Expires=" in set_cookie
    with remembered.session_transaction() as login_session:
        assert login_session.permanent is True

    from routes.auth_routes import _safe_next_url

    assert _safe_next_url("/employee/dashboard") == "/employee/dashboard"
    assert _safe_next_url("//attacker.example") is None
    assert _safe_next_url("/\\attacker.example") is None
    assert _safe_next_url("https://attacker.example") is None


def test_csrf_protects_logout_and_login_required_checks_server_session(app, admin_client):
    employee = _create_employee(app, admin_client)
    client, response = _login(app, employee["email"], employee["password"])
    assert response.status_code == 302

    previous_csrf_setting = app.config["WTF_CSRF_ENABLED"]
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        anonymous_client = _new_client(app)
        missing_login_token = anonymous_client.post(
            "/login",
            data={"email": employee["email"], "password": employee["password"]},
        )
        assert missing_login_token.status_code == 400

        dashboard = client.get("/employee/dashboard")
        assert dashboard.status_code == 200
        csrf_match = re.search(rb'name="csrf_token" value="([^"]+)"', dashboard.data)
        assert csrf_match is not None
        csrf_token = csrf_match.group(1).decode()
        bad_logout = client.post("/logout")
        assert bad_logout.status_code == 400
        logout = client.post("/logout", data={"csrf_token": csrf_token})
        assert logout.status_code == 302
    finally:
        app.config["WTF_CSRF_ENABLED"] = previous_csrf_setting


def test_employee_duplicate_edit_email_sync_and_delete(app, admin_client):
    employee = _create_employee(app, admin_client)
    duplicate_response = admin_client.post(
        "/admin/add-employee",
        data={
            "name": "Duplicate QA",
            "email": employee["email"],
            "phone": "+1 555 010 2011",
            "designation": "Duplicate",
            "salary": "1000.00",
            "password": f"Duplicate!{uuid.uuid4().hex[:10]}9",
        },
    )
    assert duplicate_response.status_code == 200
    assert b"already exists" in duplicate_response.data.lower()
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM users WHERE email=%s",
        (employee["email"],),
    )[0] == 1
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM employees WHERE user_id=%s",
        (employee["user_id"],),
    )[0] == 1

    changed_email = f"edited-{uuid.uuid4().hex[:10]}@example.test"
    update = admin_client.post(
        f"/admin/edit-employee/{employee['employee_id']}",
        data={
            "name": "Edited Auth Employee",
            "email": changed_email,
            "phone": "+1 555 010 2012",
            "designation": "Updated QA",
            "salary": "43000.00",
        },
    )
    assert update.status_code == 302
    assert _query_one(
        app,
        "SELECT email, full_name FROM users WHERE user_id=%s",
        (employee["user_id"],),
    ) == (changed_email, "Edited Auth Employee")
    assert _query_one(
        app,
        "SELECT email, employee_name FROM employees WHERE employee_id=%s",
        (employee["employee_id"],),
    ) == (changed_email, "Edited Auth Employee")

    edited_client, login_response = _login(app, changed_email, employee["password"])
    assert login_response.status_code == 302
    assert edited_client.get("/employee/dashboard").status_code == 200

    deleted = admin_client.post(f"/admin/delete-employee/{employee['employee_id']}")
    assert deleted.status_code == 302
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM users WHERE user_id=%s",
        (employee["user_id"],),
    )[0] == 0
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM employees WHERE employee_id=%s",
        (employee["employee_id"],),
    )[0] == 0
    assert edited_client.get("/employee/dashboard").status_code == 302


def test_role_authorization_and_expired_password_change(app, admin_client):
    from core.security import hash_password, verify_password
    from database.db import get_db_cursor
    from models.user_model import User

    manager_email = f"manager-{uuid.uuid4().hex[:10]}@example.test"
    manager_password = f"Manager!{uuid.uuid4().hex[:12]}9"
    created = admin_client.post(
        "/admin/add-user",
        data={
            "full_name": "Auth Audit Manager",
            "email": manager_email,
            "password": manager_password,
            "role": "manager",
        },
    )
    assert created.status_code == 302

    manager_client, response = _login(app, manager_email, manager_password)
    assert response.status_code == 302
    assert manager_client.get("/admin/add-employee").status_code == 200
    assert manager_client.get("/admin/users").status_code == 403

    employee = _create_employee(app, admin_client)
    with app.app_context():
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE users SET password_changed_at=NOW()-INTERVAL 91 DAY WHERE user_id=%s",
                (employee["user_id"],),
            )
    client, response = _login(app, employee["email"], employee["password"])
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account/change-password-required")
    assert client.get("/employee/dashboard").headers["Location"].endswith(
        "/account/change-password-required"
    )

    replacement_password = f"Expired!{uuid.uuid4().hex[:12]}9"
    changed = client.post(
        "/account/change-password-required",
        data={"new_password": replacement_password, "confirm_password": replacement_password},
    )
    assert changed.status_code == 302
    assert changed.headers["Location"].endswith("/login")
    stored = _query_one(
        app,
        "SELECT password FROM users WHERE user_id=%s",
        (employee["user_id"],),
    )[0]
    assert verify_password(stored, replacement_password)
    assert _query_one(
        app,
        "SELECT COUNT(*) FROM user_sessions WHERE user_id=%s",
        (employee["user_id"],),
    )[0] == 0


def test_mfa_requires_recent_valid_second_factor(app):
    import pyotp

    from core.security import hash_password
    from models.mfa_model import MFA
    from models.user_model import User

    email = f"mfa-{uuid.uuid4().hex[:10]}@example.test"
    password = f"Mfa!{uuid.uuid4().hex[:12]}9"
    with app.app_context():
        user_id = User.create_user("MFA Auth Audit", email, hash_password(password), "employee")
        secret = MFA.generate_secret()
        MFA.save_pending_secret(user_id, secret)
        MFA.enable(user_id)

    client, response = _login(app, email, password)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login/mfa")
    with client.session_transaction() as pending_session:
        assert "user_id" not in pending_session
        assert pending_session["mfa_pending_user_id"] == user_id

    invalid = client.post("/login/mfa", data={"code": "000000"})
    assert invalid.status_code == 200
    with client.session_transaction() as pending_session:
        assert "user_id" not in pending_session

    valid = client.post("/login/mfa", data={"code": pyotp.TOTP(secret).now()})
    assert valid.status_code == 302
    assert valid.headers["Location"].endswith("/employee/dashboard")
    assert client.get("/employee/dashboard").status_code == 200

    expired, response = _login(app, email, password)
    assert response.headers["Location"].endswith("/login/mfa")
    with expired.session_transaction() as pending_session:
        pending_session["mfa_pending_at"] -= 301
    timed_out = expired.post("/login/mfa", data={"code": pyotp.TOTP(secret).now()})
    assert timed_out.status_code == 302
    assert timed_out.headers["Location"].endswith("/login")
    with expired.session_transaction() as pending_session:
        assert "user_id" not in pending_session
        assert "mfa_pending_user_id" not in pending_session
