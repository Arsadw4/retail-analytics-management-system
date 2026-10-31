# Installation Guide — Retail Analytics System

Two supported paths: Docker (recommended, fastest to a working
system) or a manual install onto a server you control directly. Both
end up in the same place.

## Option A — Docker (recommended)

**Requirements**: Docker Engine + Docker Compose plugin.

1. Edit the included `.env` once; it contains placeholders initialized from
   `.env.example`. If `.env` is missing from your checkout, copy
   `.env.example` to `.env` first. The app's `python-dotenv` integration and
   Docker Compose both read this root-level file, so subsequent starts reuse
   the same configuration. Set `SECRET_KEY` to a generated random value and
   choose unique database passwords; do not reuse example text.

2. Build and start everything (app + MySQL + nginx):
   ```bash
   ./deploy/deploy.sh
   ```
   This builds the app image, starts all three containers, waits for
   MySQL to be healthy, and runs `scripts/verify_migrations.py` to
   confirm the schema loaded correctly (`docker-compose.yml` mounts
   `database/schema.sql` and `database/star_schema.sql` as MySQL's
   init scripts, so a fresh container auto-applies them on first
   start).

3. Edit `deploy/nginx/retail_analytics.conf`: replace
   `your-domain.example.com` and the certificate paths (see
   *TLS certificates* below), then restart the `nginx` service:
   ```bash
   docker compose restart nginx
   ```

4. Create your first admin login (the seeded `admin@example.com` row
   has no password credential and cannot log in until provisioned — see
   *First login* below).

**Updating**: re-run `./deploy/deploy.sh` — it's idempotent, and
running new migrations after a code update is a manual step (see
*Applying new migrations* below) since auto-applying schema changes on
every deploy is not something you want happening unattended.

## Option B — Manual install (no Docker)

**Requirements**: Python 3.11+, MySQL 8.0.16+ (8.0.29+ recommended —
see the note in `database/schema.sql`), the MySQL client tools
(`mysqldump`/`mysql`, for Phase 9 backup/restore), nginx, and (for
production) a process manager — this guide uses systemd.

Edit the included `.env` once and configure its values. If it is missing from
your checkout, copy `.env.example` to `.env`. The application loads the
root-level `.env` automatically through `python-dotenv`.

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
# edit .env -- SECRET_KEY, MySQL credentials, etc.

# Fresh database:
mysql -u root -p < database/schema.sql
mysql -u root -p enterprise_retail_management < database/star_schema.sql   # optional, Power BI only

python scripts/verify_migrations.py    # confirms the schema loaded correctly
```

**First login**: the seeded admin account has no password credential and
cannot log in until you set a locally generated password hash:
```bash
python -c "from getpass import getpass; from core.security import hash_password; print(hash_password(getpass('New admin password: ')))"
```
Then in MySQL:
```sql
UPDATE users SET password='<hash printed above>' WHERE email='admin@example.com';
```

**Development server** (not for production):
```bash
FLASK_ENV=development python app.py
```

**Production**: run under Gunicorn behind nginx, as a systemd service:
```bash
sudo cp deploy/systemd/retail-analytics.service /etc/systemd/system/
# edit the paths and User/Group in that file to match your server
sudo systemctl daemon-reload
sudo systemctl enable --now retail-analytics

sudo cp deploy/nginx/retail_analytics.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/retail_analytics.conf /etc/nginx/sites-enabled/
# edit the domain/certificate paths in that file first
sudo nginx -t && sudo systemctl reload nginx
```

## Applying new migrations (either path)

The database migrations (`001_initial_database_migration.sql`,
`002_employee_profile_fields.sql`, then `003_user_profile_fields.sql`)
are numbered and intended to run in order against an existing database.
Select the database configured
by `MYSQL_DB` when invoking the MySQL client; the SQL files do not switch
to a hardcoded database. Review each file before applying it and keep a
verified backup. After running any migration:
```bash
python scripts/verify_migrations.py
```

## TLS certificates

Get a free certificate via Let's Encrypt/certbot:
```bash
sudo certbot certonly --nginx -d your-domain.example.com
```
Then point `deploy/nginx/retail_analytics.conf`'s `ssl_certificate`/
`ssl_certificate_key` at the paths certbot prints.

## Post-install checklist

- [ ] `SECRET_KEY` is a unique random value
- [ ] MySQL credentials in `.env` are unique values stored locally
- [ ] Default admin password has been changed (see *First login*)
- [ ] `SESSION_COOKIE_SECURE` is effectively True (automatic once
      `FLASK_ENV=production` — see `config.py`'s `ProductionConfig`)
- [ ] `python scripts/verify_migrations.py` passes
- [ ] SMTP settings configured in `.env` if you want invoice emailing
      (Phase 4) to work — otherwise it fails gracefully with a message,
      not a crash
- [ ] A backup has been taken and verified at least once through
      `/admin/system/backups`
