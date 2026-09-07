# Makefile — сокращения для частых команд.
#
# Это удобство, а не обязательный путь: на Windows make обычно не установлен,
# и рецепты ниже рассчитаны на POSIX-оболочку (sh/bash, в том числе Git Bash).
# Все команды продублированы в README.md в вариантах для PowerShell и bash —
# при отсутствии make используйте их напрямую.
#
# Установка make: Linux `apt install make`, macOS — из Xcode Command Line Tools,
# Windows — `winget install ezwinports.make` или `choco install make`.

# Каталог исполняемых файлов venv различается: Windows — Scripts/, прочие — bin/.
ifeq ($(OS),Windows_NT)
  BINDIR := Scripts
  SYS_PY := python
  EXE    := .exe
else
  BINDIR := bin
  SYS_PY := python3
  EXE    :=
endif

# Пути от корня репозитория...
VENV := backend/.venv/$(BINDIR)
# ...и те же инструменты изнутри каталога backend/ (рецепты делают cd backend).
BVENV := .venv/$(BINDIR)

COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help install dev-backend dev-frontend dev-bot migrate revision downgrade \
        seed test test-backend test-frontend lint format build up down down-v \
        logs ps clean

## help: список целей
help:
	@echo "Доступные команды:"
	@echo "  make install          venv + зависимости backend и frontend"
	@echo "  make dev-backend      API на http://localhost:8000 с автоперезагрузкой"
	@echo "  make dev-frontend     Vite dev-сервер на http://localhost:5173"
	@echo "  make dev-bot          Telegram-бот (long polling)"
	@echo "  make migrate          alembic upgrade head"
	@echo "  make revision m=text  новая миграция (autogenerate)"
	@echo "  make downgrade        откатить одну миграцию"
	@echo "  make seed             тестовые товары в базу"
	@echo "  make test             тесты backend и frontend"
	@echo "  make lint             ruff + eslint"
	@echo "  make format           автоисправление ruff"
	@echo "  make build            production-сборка frontend"
	@echo "  make up               docker compose up --build -d"
	@echo "  make down             docker compose down"
	@echo "  make down-v           docker compose down -v (УДАЛЯЕТ базу и фото)"
	@echo "  make logs             логи всех контейнеров"
	@echo "  make ps               состояние контейнеров"
	@echo "  make clean            удалить кэши, node_modules, dist"

## install: создать venv, поставить зависимости backend (+dev) и frontend
install:
	$(SYS_PY) -m venv backend/.venv
	$(VENV)/python$(EXE) -m pip install --upgrade pip
	$(VENV)/python$(EXE) -m pip install -e "backend/[dev]"
	cd frontend && npm install

## dev-backend: FastAPI с автоперезагрузкой
dev-backend:
	cd backend && $(BVENV)/uvicorn$(EXE) app.main:app --reload --host 0.0.0.0 --port 8000

## dev-frontend: Vite dev-сервер
dev-frontend:
	cd frontend && npm run dev

## dev-bot: бот в режиме long polling
dev-bot:
	cd backend && $(BVENV)/python$(EXE) -m app.bot_main

## migrate: применить все миграции
migrate:
	cd backend && $(BVENV)/alembic$(EXE) upgrade head

## revision: создать миграцию, m="описание"
revision:
	@if [ -z "$(m)" ]; then echo 'Укажите описание: make revision m="add products"'; exit 1; fi
	cd backend && $(BVENV)/alembic$(EXE) revision --autogenerate -m "$(m)"

## downgrade: откатить одну миграцию
downgrade:
	cd backend && $(BVENV)/alembic$(EXE) downgrade -1

## seed: наполнить базу тестовыми товарами
seed:
	cd backend && $(BVENV)/python$(EXE) -m scripts.seed

## test: все тесты
test: test-backend test-frontend

## test-backend: pytest
test-backend:
	cd backend && $(BVENV)/pytest$(EXE) -q

## test-frontend: vitest
test-frontend:
	cd frontend && npm run test

## lint: статические проверки
lint:
	cd backend && $(BVENV)/ruff$(EXE) check .
	cd frontend && npm run lint

## format: автоисправление и форматирование Python
format:
	cd backend && $(BVENV)/ruff$(EXE) check . --fix
	cd backend && $(BVENV)/ruff$(EXE) format .

## build: production-сборка frontend в frontend/dist
build:
	cd frontend && npm run build

## up: поднять весь стек в Docker
up:
	$(COMPOSE) up --build -d
	@echo "frontend  http://localhost:5173"
	@echo "backend   http://localhost:8000/docs"
	@echo "postgres  localhost:5433"

## down: остановить стек (данные в томах сохраняются)
down:
	$(COMPOSE) down

## down-v: остановить стек и УДАЛИТЬ тома (база и фотографии пропадут)
down-v:
	$(COMPOSE) down -v

## logs: логи всех сервисов
logs:
	$(COMPOSE) logs -f --tail=100

## ps: состояние контейнеров
ps:
	$(COMPOSE) ps

## clean: удалить кэши и артефакты сборки
clean:
	-rm -rf backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache
	-rm -rf backend/dogmeat_backend.egg-info backend/build backend/dist
	-find backend -type d -name __pycache__ -prune -exec rm -rf {} +
	-rm -rf frontend/node_modules frontend/dist frontend/.vite
