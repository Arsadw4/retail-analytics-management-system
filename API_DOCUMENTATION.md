# API Documentation — Retail Analytics System

This application is primarily a server-rendered web app (Flask +
Jinja2), not a REST API — most pages return HTML. The endpoints below
are the exceptions: JSON APIs used by JavaScript on specific pages
(the dashboard chart, POS screen, and barcode scanning). All of them require an
authenticated session (the same login cookie as the web UI) and,
for state-changing requests, a valid CSRF token.

## Authentication

There is no separate API token/key system — these endpoints are called
by JavaScript running in an already-logged-in browser session and rely
on the session cookie set at `/login` (Phase 1). They are not intended
to be called from outside the browser session that's using the app.

## CSRF

`POST` requests must include a valid CSRF token, either as a form
field (`csrf_token`) or, for JSON requests, in the `X-CSRFToken`
header (see `static/js/pos.js` for the reference implementation).

---

## `GET /admin/dashboard/chart-data`

Returns completed-sale totals for the selected dashboard period. The
dashboard uses this endpoint to distinguish loading, genuine empty, and
request-error states.

**Roles**: admin, manager, super_admin

**Query parameters**:

- `period`: `this_year`, `last_year`, `this_month`, `last_month`, or
  `custom` (default: `this_year`).
- `start` and `end`: required for `custom`, in `YYYY-MM-DD` format; both
  dates are included in the selected range.

**Response** (200):

```json
{"labels": ["Jan", "Feb"], "values": [1250.0, 0.0], "transactions": 1}
```

Missing date buckets are returned as zeroes. A 400 response indicates an
invalid custom range. A 503 response indicates the sales query failed; the
dashboard shows a retryable error instead of an empty-state message.

---

## `POST /admin/billing/checkout`

Creates a completed sale (Phase 4 POS). The single most important API
in the app — see `models/billing_model.py:Billing.create_bill` for the
full GST/discount/stock-locking logic behind it.

**Roles**: admin, manager, employee, cashier

**Request body** (`application/json`):
```json
{
  "items": [{"product_id": 12, "quantity": 2}],
  "customer_id": 5,
  "customer_state": "Karnataka",
  "coupon_code": "SAVE10",
  "payment_methods": [{"method": "cash", "amount": 460.00, "reference_no": null}],
  "hold_id": null
}
```
- `items`: required, non-empty.
- `customer_id`: optional (null = walk-in customer). Required if any
  `payment_methods` entry uses `"method": "wallet"`.
- `payment_methods`: `method` is one of `cash`, `upi`, `card`, `wallet`.
  The sum of all `amount` values must exactly equal the server-computed
  grand total (including GST and discount) — the server is the sole
  source of truth for that total; see Phase 4's README for why the
  client only shows an estimate.
- `hold_id`: if completing a previously-held bill (Phase 4), pass its
  ID so the hold record is cleaned up on success.

**Response** (200, success):
```json
{"ok": true, "message": "Bill created successfully.", "sale_id": 1042, "invoice_number": "INV-2026-001042"}
```

**Response** (200, rejected — note: still HTTP 200, check `ok`):
```json
{"ok": false, "message": "Insufficient stock for Widget (available: 3).", "sale_id": null, "invoice_number": null}
```

---

## `POST /admin/billing/hold`

Saves the current cart for later (Phase 4 Hold & Resume).

**Roles**: admin, manager, employee, cashier

**Request body**:
```json
{"items": [{"product_id": 12, "name": "Widget", "price": 100.0, "quantity": 2}], "customer_id": 5}
```

**Response**: `{"ok": true, "hold_id": 7}`

---

## `GET /api/products/for-pos`

All active products, shaped for the POS screen's product picker.

**Roles**: admin, manager, employee, cashier

**Response**:
```json
[{"product_id": 12, "category": "Electronics", "name": "Widget",
  "purchase_price": 60.0, "selling_price": 100.0, "stock": 25}]
```

---

## `GET /api/products/lookup-barcode/<code>`

Looks up a product by its `barcode` or `sku` (Phase 3 barcode/QR
system) — used by the camera-based scan page and the POS barcode
input.

**Roles**: admin, manager, employee, cashier, inventory_manager

**Response** (200, found):
```json
{"found": true, "product_id": 12, "product_name": "Widget", "sku": "SKU00000012",
 "barcode": "890000000012", "purchase_price": 60.0, "selling_price": 100.0, "stock_quantity": 25}
```

**Response** (404, not found): `{"found": false}`

---

## Export endpoints (file downloads, not JSON)

Several reporting pages expose `/export/{csv,excel,pdf}` variants
(Customers, Suppliers, Employees, Attendance, Salary, Departments, AI
forecast, Inventory intelligence — see each phase's README for the
full list). These return a file attachment (`Content-Disposition:
attachment`) rather than JSON — call them by navigating the browser to
the URL (or `<a href>`), not via `fetch()`.

## Error conventions

- Authentication/authorization failures follow the normal web-app
  pattern: unauthenticated → redirect to `/login`; authenticated but
  wrong role → HTTP 403 (HTML page, not JSON — these endpoints don't
  currently negotiate `Accept: application/json` for error responses).
- Business-rule failures (insufficient stock, invalid coupon, payment
  mismatch) on `/admin/billing/checkout` and `/admin/billing/hold`
  return HTTP 200 with `"ok": false` and a human-readable `message` —
  check `ok`, not the HTTP status code, for these two endpoints
  specifically.
