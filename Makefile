.PHONY: install test lint run up down demo

install:
	pip install -r requirements-dev.txt

lint:
	ruff check app workers tests scripts

test:
	pytest tests/unit -q

# Run offline: SQLite. Populate with `make demo` in a second terminal.
run:
	DATABASE_URL=sqlite+pysqlite:///./dev.sqlite \
	uvicorn app.main:app --reload

up:
	docker compose up --build

down:
	docker compose down -v

# Seed 14 days of realistic telemetry for the 4 portfolio agents (with a
# latency regression + override spike that trigger alerts). Server must be up.
demo:
	python scripts/simulate.py --base-url http://localhost:8000
