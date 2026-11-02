# MediCode Backend

FastAPI backend for MediCode, an educational coding and lab assessment platform.

## Requirements
- Python 3.11+
- PostgreSQL 15+
- uv or pip

## Setup
Create a virtual environment, install the project and development dependencies,
configure your local environment variables, and run the application.

## Database setup

The local database uses PostgreSQL 16 through Docker Compose. Start Docker
Desktop, then run:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d
alembic upgrade head
```

Before starting Compose, replace the `replace-with-*` values in `.env` with
strong local secrets. Use the same database password in `DATABASE_URL` and
`MEDICODE_DB_PASSWORD`.

pgAdmin is available at `http://127.0.0.1:5050`; sign in with
`PGADMIN_DEFAULT_EMAIL` and `PGADMIN_DEFAULT_PASSWORD` from `.env`. The
`MediCode PostgreSQL` server is registered automatically. Connect with host
`postgres`, port `5432`, database `medicode`, and username `medicode`; use
`MEDICODE_DB_PASSWORD` as the password. The hostname `postgres` works from
pgAdmin because both services run on the Compose network.

Alembic creates the identity and academic tables, seeds approved roles, and
adds authentication, learning content, and submission tables. Do not edit the
database schema manually; create and review an Alembic migration for every
schema change.

## Authentication

Public registration creates student accounts. Faculty accounts are created by
an administrator. Run `.venv\Scripts\python.exe .\scripts\bootstrap_admin.py`
once to create the first super administrator; the script prompts for credentials
without echoing the password.

`POST /api/auth/register` accepts `email`, `password`, and `full_name` and
returns access and refresh tokens. `POST /api/auth/login` accepts `email` and
`password`; `POST /api/auth/refresh` accepts a `refresh_token` and rotates it.
Send the access token as `Authorization: Bearer <token>` to
`POST /api/auth/logout` to revoke the session. `GET /api/auth/me` and
`GET /api/users/me` return the current account. `PATCH /api/users/me` updates
the profile's name or phone number. Administrators can list users and create
student/faculty accounts through `/api/users`.

Course authoring uses courses, offerings, labs, experiments, problems, and test
cases. Students enroll in an open course offering before viewing published
problems. `POST /api/submissions` stores source code (up to 64 KiB) and returns
a submission ID with status `RECEIVED`. The grading worker and sandbox from
Phase 3 are not connected yet, so a received submission is not executed or
graded.

Phase 4 endpoints are also available: `GET /api/courses/{id}/leaderboard`
(best scored submission per problem, summed per student),
`GET/POST /api/problems/{id}/discussions` (top-level posts and one-level
replies), and admin-only `GET /api/admin/stats`. The WebSocket endpoint is
`/ws/submissions/{id}`; send `{"access_token":"<access-token>"}` as its first
message. It sends the current submission state and listens for PostgreSQL
notifications. A grading worker must call
`medicode.services.realtime.publish_submission_update` after it commits a result
to send later updates.

## Run the server

From the `MediCode_backend` directory, activate the virtual environment and start
the development server:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn medicode.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive API documentation is
available at `http://127.0.0.1:8000/docs`, and the health check is at
`http://127.0.0.1:8000/health`.

## Architecture
- `api/`: HTTP routes and API composition
- `core/`: application configuration, logging and security
- `db/`: database sessions and shared database infrastructure
- `models/`: SQLAlchemy models
- `schemas/`: Pydantic request and response schemas
- `services/`: business logic
- `repositories/`: data access abstractions
- `workers/`: background task entry points
- `tests/`: unit and integration tests

See `docs/` for architecture and implementation decisions.
