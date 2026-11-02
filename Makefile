.PHONY: test test-unit test-integration smoke host-check seed up down

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

smoke:
	python scripts/smoke.py

host-check:
	bash scripts/check_sandbox_host.sh

seed:
	python scripts/seed_problems.py

up:
	docker compose up -d --build

down:
	docker compose down
