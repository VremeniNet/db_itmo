COMPOSE = docker compose

.PHONY: up down status test logs restart

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

status:
	$(COMPOSE) ps

test:
	python scripts/run_tests.py

logs:
	$(COMPOSE) logs --tail=100

restart:
	$(COMPOSE) restart