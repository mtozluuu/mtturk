# project1 – Flight Management API

## Quick start (PostgreSQL on localhost)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up PostgreSQL (macOS via Homebrew)

```bash
brew install postgresql@18   # or whichever version you have
brew services start postgresql@18

# Create the database and user (run once)
psql -U postgres -d postgres -c "CREATE USER project1 WITH PASSWORD 'your_secure_password';"
psql -U postgres -d postgres -c "CREATE DATABASE project1 OWNER project1;"
```

### 3. Initialise the schema

```bash
psql -U project1 -d project1 -f scripts/init_db.sql
```

### 4. Configure environment variables

Copy the example file and edit it:

```bash
cp .env.example .env
```

Minimum `.env` for local development:

```
DATABASE_URL=postgresql://project1:your_secure_password@localhost:5432/project1
SESSION_SECRET_KEY=any-long-random-string

SEED_ADMIN_USERNAME=admin
SEED_ADMIN_PASSWORD=Test1234!
SEED_ADMIN_ROLE=admin
```

> **Note:** `DATABASE_URL` uses the `postgresql://` scheme which routes to
> `psycopg2` (the driver in `requirements.txt`).  If you have psycopg v3
> installed instead, use `postgresql+psycopg://`.

### 5. Start the application

```bash
uvicorn app.main:app --reload
```

On startup the app will automatically create the seed admin user if it does
not already exist.  You will see a log line like:

```
INFO  app.seed  Seed: created user 'admin' with role 'admin' (id=1).
```

### 6. Log in

Use the `POST /auth/login` endpoint (or the `/login` page):

```bash
curl -s -c cookies.txt \
  -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username": "admin", "password": "Test1234!"}'
```

---

## Seeding admin – details

The seeding mechanism is controlled by three environment variables:

| Variable              | Required | Default  | Description                               |
|-----------------------|----------|----------|-------------------------------------------|
| `SEED_ADMIN_USERNAME` | yes      | –        | Username for the seed admin account       |
| `SEED_ADMIN_PASSWORD` | yes      | –        | Password (stored hashed, never logged)    |
| `SEED_ADMIN_ROLE`     | no       | `admin`  | Role: `admin`, `pilot`, `copilot`, `technician` |

**Production safety:** seeding is completely disabled unless both
`SEED_ADMIN_USERNAME` and `SEED_ADMIN_PASSWORD` are set.  Do **not** set them
in production environments.

### Manual seeding script

You can also seed without starting the full app:

```bash
SEED_ADMIN_USERNAME=admin \
SEED_ADMIN_PASSWORD=Test1234! \
SEED_ADMIN_ROLE=admin \
python scripts/seed_admin.py
```

The script is idempotent – running it again with the same username does
nothing.

---

## API overview

| Method | Path              | Auth required | Description              |
|--------|-------------------|---------------|--------------------------|
| POST   | /auth/login       | No            | Log in (username + password) |
| POST   | /auth/logout      | Yes           | Log out                  |
| GET    | /auth/me          | Yes           | Current user info        |
| POST   | /auth/change-password | Yes       | Change own password      |
| POST   | /admin/users      | admin         | Create a user            |
| GET    | /admin/users      | admin         | List users               |
| GET    | /flights-ui       | –             | HTML flight browser      |
| GET    | /health           | No            | Health check             |
| GET    | /docs             | No            | Interactive API docs      |

---

## Running tests

```bash
pytest tests/
```

