# Kinney Aviation

Shop application for **Kinney Aviation** — FAA Airframe & Powerplant maintenance with Arizona fly-to-you service. It extends the public site ([kinney-aviation](https://github.com/nibrocsolutions/kinney-aviation)) with the working tools behind the practice:

- **Records** — owners, aircraft, and maintenance work orders (discrepancy, corrective action, times, and sign-off)
- **Billing** — invoices built from a work order’s labor, parts, and pilot-mechanic travel, then issued and paid
- **Calendar** — a month planner of what is scheduled each day: visits you add, work that was opened, annuals that come due, and invoices that are still unpaid
- **Presentation** — owner briefings, work sheets, and invoices rendered from those same records

Sign-in is required. An administrator manages the accounts. A shop account can work the records, the bills, and the calendar.

Built to run as a Docker container on a Raspberry Pi or any Docker host, on port **8088**. SQLite data persists in a Docker volume.

## Quick start

```bash
git clone https://github.com/nibrocsolutions/kinney-aviation-app.git
cd kinney-aviation-app
docker compose up -d --build
```

Open `http://localhost:8088` (or `http://<pi-ip>:8088`) and sign in.

With the sample fleet, the first start creates two accounts unless you set different passwords:

| Account | Username | Password | Can do |
| --- | --- | --- | --- |
| Administrator | `admin` | `Kinney-Admin-2026` | Everything, including the Admin page |
| Shop | `ron` | `Kinney-Shop-2026` | Records, billing, fleet, calendar, and owner sheets |

Change both on the Admin page before anyone else can reach the app. Set `ADMIN_PASSWORD` and `SHOP_PASSWORD` to override them. With `SEED_DEMO=0` and no `ADMIN_PASSWORD`, the first start writes a random administrator password to `data/initial-admin-password.txt` inside the data volume.

A sample Arizona fleet loads the first time the database is empty. To start with an empty shop, set `SEED_DEMO=0` before that first start.

### Useful commands

```bash
docker compose logs -f
git pull && docker compose up -d --build
docker compose down
```

`docker compose down` keeps the `kinney-data` volume. Add `-v` only when you mean to erase the shop database.

## What you can do

- Keep a fleet: N-number, times, home field, and annual due date
- Open a work order, record labor and parts, and see the billable total as you go
- **Bill this work** to snapshot that total onto a draft invoice
- Issue the invoice, record payments, and hand the owner a printed sheet
- Open an aircraft briefing that shows open squawks, the log, and the balance
- Open the calendar, see what is already on a day, and add a visit, inspection, parts run, or ferry
- On the Admin page, add a shop account, reset a password, or deactivate someone who should no longer sign in

Issued invoices stay as written. Change the money by voiding the invoice (after removing payments) and billing the work order again. The write-up on a work order can still be edited after the invoice is issued.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
mkdir -p data
DATA_DIR=./data uvicorn app.main:app --reload --host 0.0.0.0 --port 8088
```

Tests:

```bash
pytest
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check (no sign-in) |
| POST | `/api/login` | Sign in |
| POST | `/api/logout` | Sign out |
| GET | `/api/me` | Signed-in account |
| POST | `/api/account/password` | Change your password |
| GET, POST | `/api/admin/users` | Administrator: accounts |
| PATCH | `/api/admin/users/{id}` | Administrator: role, password, or active |
| GET | `/api/calendar` | Scheduled days between `start` and `end` |
| POST | `/api/schedule` | Add a day on the calendar |
| GET | `/api/dashboard` | Briefing totals |
| GET, PATCH | `/api/shop` | Shop profile and rates |
| GET, POST | `/api/customers` | Owners |
| PATCH, DELETE | `/api/customers/{id}` | Update or remove an owner |
| GET, POST | `/api/aircraft` | Fleet |
| PATCH, DELETE | `/api/aircraft/{id}` | Update or remove an aircraft |
| GET, POST | `/api/records` | Work orders |
| GET, PATCH, DELETE | `/api/records/{id}` | One work order |
| POST | `/api/records/{id}/labor` | Add labor |
| POST | `/api/records/{id}/parts` | Add a part |
| POST | `/api/records/{id}/invoice` | Build a draft invoice from the work order |
| GET | `/api/invoices` | Invoices |
| PATCH | `/api/invoices/{id}` | Notes, draft tax, due date |
| POST | `/api/invoices/{id}/refresh` | Rebuild a draft from the work order |
| POST | `/api/invoices/{id}/issue` | Issue |
| POST | `/api/invoices/{id}/void` | Void |
| POST | `/api/invoices/{id}/payments` | Record a payment |
| GET | `/api/present/aircraft/{id}` | Owner briefing |
| GET | `/api/present/records/{id}` | Work sheet |
| GET | `/api/present/invoices/{id}` | Invoice sheet |

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_DIR` | `./data` locally, `/data` in Docker | SQLite directory |
| `PORT` | `8088` | HTTP port |
| `SEED_DEMO` | `1` | Load the sample fleet when the database has no owners |
| `ADMIN_USERNAME` | `admin` | First administrator, created when there are no accounts |
| `ADMIN_PASSWORD` | sample password when `SEED_DEMO=1` | At least 10 characters. Blank with `SEED_DEMO=0` writes a random password into the data directory |
| `SHOP_USERNAME` | `ron` | Sample shop account, only when `SEED_DEMO=1` |
| `SHOP_PASSWORD` | sample password when `SEED_DEMO=1` | Shop account password |
| `SESSION_SECURE` | `0` | Set to `1` when the site is served over HTTPS |
| `DATABASE_URL` | `sqlite:///{DATA_DIR}/kinney.db` | Override the database |

## Notes

- Passwords are hashed. The session cookie is HTTP-only. Changing a password signs that person out.
- Set `SESSION_SECURE=1` when a reverse proxy terminates HTTPS.
- The sample administrator and shop passwords are for a private demo. Replace them before the app is reachable beyond the shop.
- The aircraft maintenance record required by the FARs stays in the aircraft logbook. This application is the shop’s working copy.
- The sample phone and `contact@kinneyaviation.example` are placeholders, same as the public site.
- Labor defaults to $125.00 an hour and pilot-mechanic travel to $95.00 an hour. Change both in Shop profile. Tax is entered on a draft invoice when you need it.

## Project layout

```
├── Dockerfile
├── docker-compose.yml
├── app/
│   ├── main.py
│   ├── api/routes.py
│   ├── billing.py
│   ├── models.py
│   ├── seed.py
│   └── static/
└── tests/
```
