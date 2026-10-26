# MediCode Backend

FastAPI backend for MediCode, an educational coding and lab assessment platform.

## Requirements
- Python 3.11+
- PostgreSQL 15+
- uv or pip

## Setup
Create a virtual environment, install the project and development dependencies,
configure your local environment variables, and run the application.

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
