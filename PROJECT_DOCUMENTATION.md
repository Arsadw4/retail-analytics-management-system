# Retail Analytics System — Project Documentation

This project is a Flask + MySQL retail management and analytics platform.

## Core modules
- Authentication, RBAC, MFA and audit logging
- Dashboard and global search
- Products, categories and inventory
- Sales, POS, billing, invoices and returns
- Customers and suppliers
- Purchase orders and GRN
- Employees, HR, attendance, leave and payroll
- Analytics, AI insights, forecasting and recommendations
- Reports and Power BI/BI integration
- Administration, sessions, system health and backups

## Important guides
- `INSTALLATION_GUIDE.md` — setup and first run
- `API_DOCUMENTATION.md` — API reference
- `AUDIT_REPORT.md` — review scope, recorded verification, and limitations

## Database
The default database name is `enterprise_retail_management`; deployments can
select another database through `MYSQL_DB`. Existing databases are upgraded
with migrations `001_initial_database_migration.sql`,
`002_employee_profile_fields.sql`, and `003_user_profile_fields.sql` in that
order. The SQL files use the database selected by the MySQL client.

## Configuration
The delivered `.env` starts with placeholders; configure its values once.
The Flask application loads the root-level file through `python-dotenv`, and
Docker Compose also reads it, so the same configuration is reused on each
start. If `.env` is missing from a checkout, copy `.env.example` to `.env`.
The example file is the reference for supported variable names.
