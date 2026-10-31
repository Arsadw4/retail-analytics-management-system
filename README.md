# Enterprise Retail Management System

A full-stack Flask + MySQL/MariaDB retail management platform covering
point-of-sale billing, inventory, CRM/suppliers, HR, Business
Intelligence (Power BI-ready), AI-assisted analytics, and production
security/monitoring/backup — built as one continuously-evolving
application across 10 development phases and consolidated here into a
single, unified release.

This README describes the current project structure and explains how to
configure, install, run, test, and provision accounts. The migration files
document database changes for existing installations.

## 1. Project Overview

The system runs as one Flask application (`app.py`), backed by a
single MySQL/MariaDB database (`enterprise_retail_management`), with
one authentication system, one RBAC model, and one unified navigation
structure. The modules below are present in the current codebase; see
`AUDIT_REPORT.md` for the scope of checks recorded and the remaining
verification limits.

## 2. Technology Stack

- **Backend**: Flask 3.1, Python 3.12+
- **Database**: MySQL 8.0.16+ / MariaDB 10.11,
  accessed via `PyMySQL` + `DBUtils` connection pooling (no C build
  toolchain required)
- **Frontend**: Jinja2 templates and vanilla CSS/JavaScript; the dashboard
  chart is rendered as SVG, and selected analytics pages load Chart.js from a CDN
- **Security**: Flask-WTF (CSRF), Flask-Limiter (rate limiting),
  PBKDF2 password hashing, optional per-user TOTP MFA (`pyotp`)
- **Reporting**: ReportLab (PDF), openpyxl (Excel)
- **Barcode/QR**: `python-barcode`, `qrcode`, Pillow
- **Production WSGI**: gunicorn, with nginx + systemd deployment
  configs included under `deploy/`
- **Testing**: pytest, pytest-cov

## 3. Main Modules

| Module | Highlights |
|---|---|
| **Auth & Security** | Session-based login, PBKDF2 hashing, account lockout, CSRF protection, security headers, SQLi-safe parameterized queries, audit logs, optional TOTP MFA, password expiration |
| **Admin & RBAC** | 8-role permission system (`core/rbac.py`), per-route `@role_required` protection, activity logs |
| **Products & Inventory** | Product catalog, categories, batches, warehouses, stock-in/stock-out with row-locking (`SELECT ... FOR UPDATE`), barcode/QR generation, low-stock alerts |
| **Billing & Sales (POS)** | Multi-item cart, barcode scan-to-add, CGST/SGST/IGST tax splitting, coupons/discounts, held bills, sales returns, daily/weekly/monthly/tax reports |
| **Customers & Suppliers (CRM)** | Customer profiles, loyalty points, wallet balance, credit ledger; supplier ledger, GRN (Goods Receipt Notes), purchase orders |
| **HR & Employee Administration** | Employee directory, departments/designations, attendance, leave requests, salary records, performance reviews, employee documents |
| **Business Intelligence / Power BI** | Star-schema views (`database/star_schema.sql`: `dim_date`, `dim_product`, `dim_customer`, `dim_employee`, `fact_sales`, `fact_inventory_snapshot`) plus per-user/store BI access control, ready for Power BI Desktop |
| **In-app Analytics** | Database-backed dashboard sales chart, sales reports, and profit-vs-inventory-value summary |
| **AI-Assisted Analytics** | ABC product analysis, customer churn risk, customer lifetime value (CLV), demand forecasting |
| **Security / Backup / Monitoring** | MFA, backup/restore with logs, system health dashboard, response caching, pagination |

## 4. Project Structure

```
Retail_Analytics_System_Live/
├── app.py                  # Application entry point — registers all blueprints
├── config.py                # Environment-driven configuration
├── core/                    # Security, RBAC, DB pool, shared helpers
├── routes/                  # 24 Flask blueprints for application modules
├── models/                  # One model per entity/domain
├── ai/                       # AI/forecasting modules
├── templates/                # Jinja2 templates, mirrors routes/ structure
├── static/                   # CSS, JS, uploaded files
├── database/
│   ├── schema.sql            # Full cumulative schema — fresh installs
│   ├── star_schema.sql       # Power BI dimensional views
│   ├── sample_data.sql       # Optional seed data (empty by default)
│   ├── dev_queries.sql       # Ad-hoc/debug queries (not run automatically)
│   └── migrations/           # Ordered existing-database upgrade scripts
├── scripts/                  # verify_migrations.py and other maintenance scripts
├── deploy/                   # nginx config, systemd unit, gunicorn config, deploy.sh
├── tests/                    # unittest and pytest regression tests
├── .env                      # Local environment configuration
├── .env.example              # Environment variable template/reference
├── requirements.txt
└── README.md                 # This file
```

## 5. Database Setup

Database name: **`enterprise_retail_management`**

### Fresh install (recommended for a new environment)

```bash
mysql -u root -p -e "CREATE DATABASE enterprise_retail_management \
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p enterprise_retail_management < database/schema.sql
mysql -u root -p enterprise_retail_management < database/star_schema.sql   # optional, for Power BI
```

`schema.sql` is the complete cumulative schema. It does not create or
switch databases: the database selected by the `mysql` command is the
target, which also allows a separate test database to be initialized
without editing the SQL file.

### Upgrading an existing pre-Phase-1 database

If you have an older installation that predates this consolidated
schema, do **not** run `schema.sql` against it. Review and apply these
scripts in order:

1. `database/migrations/001_initial_database_migration.sql`
2. `database/migrations/002_employee_profile_fields.sql`
3. `database/migrations/003_user_profile_fields.sql`

Each file's comments explain the change. Select the same database configured by
`MYSQL_DB` when invoking the MySQL client; the migration does not switch
to a hardcoded database. These files document the upgrade path and are not
needed for a fresh install.

`database/sample_data.sql` is an intentionally empty stub (present in
every phase since Phase 1) — seed your own data, or use
`scripts/verify_migrations.py` to sanity-check the schema state.

## 6. Configuration / Environment Variables

The package includes `.env` initialized with placeholders and `.env.example`
as the reference template. Configure the values in `.env` once. Python loads
that file through `python-dotenv`, and Docker Compose reads the same root-level
file, so you do not need to enter the settings again for each start. If `.env`
is missing from a checkout, copy `.env.example` to `.env` first.

The template lists all supported variables, including:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing key — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`, `MYSQL_ROOT_PASSWORD` | Database connection and Docker initialization |
| `DB_POOL_MAX_CONNECTIONS`, `DB_POOL_MIN_CACHED`, `DB_POOL_MAX_CACHED` | Connection pool tuning |
| `RATELIMIT_STORAGE_URI` | Use `redis://...` in production for shared rate limiting across workers |
| `SMTP_*` | Invoice emailing (leave blank to disable) |
| `SESSION_TIMEOUT_MINUTES`, `BACKUP_DIR`, `MFA_ISSUER_NAME` | Security/backup/MFA settings |

## 7. Installation

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 8. How to Run

**Development:**
```bash
flask --app app run --debug
```

**Production** (gunicorn + nginx + systemd configs are provided under
`deploy/`):
```bash
gunicorn -c deploy/gunicorn.conf.py app:app
```
See `deploy/deploy.sh`, `deploy/systemd/retail-analytics.service`, and
`deploy/nginx/retail_analytics.conf` for a full production deployment.

## 9. Authentication and employee account provisioning

Log in at `/login` with an admin account seeded into the `users`
table. The fresh-install schema includes an administrator row with an
empty password field, so it cannot authenticate until a local password
hash is provisioned. Before first login, run this command from the
project directory, enter a new password at the hidden prompt, then use
the printed hash to update the seed row:

```bash
python -c "from getpass import getpass; from core.security import hash_password; print(hash_password(getpass('New admin password: ')))"
mysql -u root -p enterprise_retail_management -e "UPDATE users SET password='<generated-hash>', password_changed_at=NOW() WHERE email='admin@example.com';"
```

RBAC covers 8 roles, and routes declare their access rules with
`@role_required(...)`.

To create an employee account, sign in as an administrator or manager,
open **Human Resources → All Employees → Add Employee**, and submit the
required name, email, salary, and initial password. Department, contact,
and profile fields are optional where the form marks them optional. The
employee code is derived from the database-assigned employee ID. The same transaction creates
the employee profile and an active `employee` login linked by `user_id`;
the password is hashed before storage. The employee signs in at `/login`
with the submitted email and password and is sent to `/employee/dashboard`.
Duplicate email addresses are rejected. There is no shared employee
default password.

## 10. Testing and verification

Install the declared development and runtime packages before running the
checks:

```bash
python -m compileall -q .
python -m unittest discover -s tests -v
python -m pytest -q
```

Database integration checks are opt-in and have a hard guard: `MYSQL_DB`
must end in `_test`. Point the normal `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`,
and `MYSQL_PASSWORD` settings at a disposable local instance, create a separate
database, and load the schemas into that database. For example, use
`enterprise_retail_management_test` when loading `database/schema.sql`.
Then run this in PowerShell:

```powershell
$env:RUN_DB_INTEGRATION = "1"
python -m pytest -q tests/test_project_integration.py
Remove-Item Env:RUN_DB_INTEGRATION
```

The integration test inserts employee, product, stock, and sale records. Use
only a disposable database whose name ends in `_test`; never point it at a
production database. The browser console is not available through the current
in-app tab-control API, so browser checks report rendered visible state and
server request results instead.

## 11. Fixes Applied During Final Integration

A small number of genuine, longstanding bugs were found and fixed
while verifying this consolidated release (present in the codebase
since early phases, not introduced by merging):

- **`year_month` reserved-keyword conflict**: `YEAR_MONTH` is a
  reserved SQL keyword (a valid `INTERVAL` unit) and was used
  unquoted as a column alias in three views (`v_monthly_sales`,
  `dim_date` in both `star_schema.sql` and migration 007, and the
  historical copy in migration 004). This caused `schema.sql` and
  `star_schema.sql` to fail to load entirely on both MySQL and
  MariaDB. Fixed by backtick-quoting the identifier everywhere it is
  defined; no application code or template referenced the column by
  name (billing routes use `SELECT *` with positional access), so the
  fix required no other changes.
- **`templates/admin/analytics/line_chart.html`** referenced an
  undefined `{{ inventory }}` variable — the route actually passes
  `inventory_value`. Fixed to reference the correct variable.
- **Three analytics templates were completely empty** (0 bytes) in
  every phase since Phase 1: `bar_chart.html`, `pie_chart.html`, and
  `profit_loss.html`. Implemented using only the exact variables
  their existing routes already provide (`total_products`,
  `total_customers`, `total_inventory` for the bar/pie charts;
  `revenue` and `inventory_value` for profit/loss) — no new fields or
  backend changes were needed.
- Corrected a stale comment at the top of `schema.sql` that
  described the file as only the "Phase 2 shape"; it has documented
  every phase's tables for some time and the comment now says so.

## 12. Troubleshooting

- **`Can't connect to MySQL server`**: confirm `MYSQL_HOST`/`MYSQL_PORT`
  in `.env` match a running MySQL/MariaDB instance and that the
  `MYSQL_USER` has privileges on `MYSQL_DB`.
- **`Table doesn't exist` errors on a fresh install**: make sure you
  ran `database/schema.sql` (not an individual migration file) against
  a brand-new database.
- **CSRF token errors on form submission**: confirm cookies are
  enabled and `SECRET_KEY` is set and stable across restarts (a
  changing secret invalidates existing sessions/tokens).
- **Analytics pages show all zeros**: this is expected on a database
  with no sales/product data yet — seed data via the app's own CRUD
  screens or `database/sample_data.sql`.

## 13. Production Notes

- Keep production credentials private and out of public source control.
- Use `RATELIMIT_STORAGE_URI=redis://...` (not the default in-memory
  store) when running multiple gunicorn workers, so rate limits are
  shared correctly.
- Use a unique `SECRET_KEY` and database credentials for every deployment.
- See `INSTALLATION_GUIDE.md` for setup, `API_DOCUMENTATION.md` for the
  endpoint reference, `PROJECT_DOCUMENTATION.md` for the module map, and
  `AUDIT_REPORT.md` for the recorded audit scope and limitations.
