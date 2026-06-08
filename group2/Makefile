COMPOSE = docker compose
PYTHON = python

.PHONY: up down status logs etl demo test

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

status:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail=100

etl:
	$(PYTHON) etl/pg_to_ch.py
	$(PYTHON) etl/pg_to_manticore.py

demo:
	$(PYTHON) scripts/demo_scenario.py

test:
	$(PYTHON) scripts/run_tests.py