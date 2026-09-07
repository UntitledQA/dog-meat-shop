# CLAUDE.md

Памятка для Claude Code по этому репозиторию. Пользовательская документация — в `README.md`,
жёсткие контракты между слоями — в `docs/CONTRACTS.md`.

## Что это за проект

Telegram Mini App «Мясо для собак» — магазин развесного мяса для собак.
Покупатель открывает Mini App внутри Telegram, выбирает товары по весу, оформляет заказ
с доставкой или самовывозом. Администратор работает в том же Mini App: товары, остатки,
фотографии, статусы заказов. Оплата — при получении, онлайн-платежей в MVP нет.

## Стек

| Слой      | Технологии                                                       |
|-----------|------------------------------------------------------------------|
| Backend   | Python 3.11+ (Docker — 3.12), FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, structlog |
| Бот       | aiogram 3 (long polling; webhook — опция)                        |
| Frontend  | React 18, TypeScript, Vite, Zustand, react-router                |
| БД        | PostgreSQL 16 (в тестах — SQLite через aiosqlite)                |
| Инфра     | Docker Compose, nginx (статика + прокси)                         |

## Архитектура backend

Строгое разделение слоёв, зависимости идут только сверху вниз:

```
app/api/v1/       HTTP-роуты: разбор запроса, вызов сервиса, сериализация ответа
app/api/deps.py   зависимости FastAPI: DbSession, CurrentUser, AdminUser
app/services/     бизнес-логика: расчёты, транзакции, переходы статусов
app/repositories/ доступ к данным, SQLAlchemy-запросы
app/models/       ORM-модели
app/schemas/      Pydantic v2: валидация входа и форма ответа
app/storage/      абстракция файлового хранилища (LocalStorage, позже S3Storage)
app/core/         config, db, errors, logging, security, money, ratelimit
app/bot/          aiogram 3: хендлеры, клавиатуры, уведомления
```

Правила:

* Роут не ходит в БД напрямую — только через сервис.
* Сервис не знает про `Request`/`Response` и не бросает `HTTPException`; он бросает
  наследников `app.core.errors.AppError`, которые обработчик превращает в единый JSON.
* Репозиторий не содержит бизнес-правил.

## Ключевые инварианты

Их нарушение — баг, даже если тесты проходят.

1. **Только `Decimal`, никогда `float`.** Деньги — `Numeric(10, 2)`, вес — `Numeric(10, 3)`.
   Округление — `ROUND_HALF_UP` через `app/core/money.py`.
2. **Decimal сериализуется в JSON строкой** (`"890.00"`). На фронте разбирается через
   `toNumber()`, обратно уходит тоже строкой.
3. **Корзина фронта — не источник истины.** При создании заказа backend заново читает
   товары из БД: цены, остатки и `is_active` берутся оттуда, а не из тела запроса.
4. **Списание остатка — внутри одной транзакции с блокировкой.** `SELECT ... FOR UPDATE`
   по товарам, отсортированным по `id` (защита от дедлоков), проверка, списание, вставка
   заказа. На SQLite блокировка пропускается — диалект определяется в рантайме
   (`app/core/db.py: supports_row_locking`).
5. **Отмена заказа идемпотентна.** Повторная отмена возвращает заказ как есть и НЕ
   возвращает остаток второй раз; признак — `orders.stock_restored_at`.
6. **initData проверяется на бэкенде.** `user_id` берётся только из проверенного initData;
   любой `user_id` из тела или query игнорируется.
7. **Права администратора проверяются на бэкенде.** Скрытая кнопка в UI — не защита;
   каждый админ-роут требует зависимость `AdminUser`.
8. **Тип загружаемого файла определяется по сигнатуре байтов**, не по расширению
   и не по заголовку `Content-Type`. Путь собирается только внутри `UPLOAD_DIR`.
9. **Формат ошибок один на всё API**: `{"error": {"code", "message", "details"}}`,
   сообщения — на русском. Коды перечислены в `docs/CONTRACTS.md`, раздел 3.
10. **Enum в БД — `sa.Enum(..., native_enum=False)`** (VARCHAR + CHECK), чтобы схема
    работала и в PostgreSQL, и в SQLite.
11. **Код совместим с Python 3.10+**: без `StrEnum` и `typing.Self`.

## Структура каталогов

```
backend/
  app/            код приложения (см. «Архитектура backend»)
  alembic/        миграции; versions/ исключён из проверок ruff
  tests/          pytest, SQLite в памяти
  scripts/        seed и служебные скрипты
  pyproject.toml  зависимости, ruff, mypy, pytest
  Dockerfile      multi-stage образ (общий для API и бота)
  entrypoint.sh   ожидание БД -> alembic upgrade head -> exec команды (LF!)
frontend/
  src/            React-приложение
  Dockerfile      сборка node -> раздача nginx
  nginx.conf      SPA fallback, прокси /api и /uploads, gzip, кэш
docs/CONTRACTS.md контракты между агентами — менять может только главный агент
uploads/          локальное хранилище фотографий (в git не попадает)
docker-compose.yml, .env.example, Makefile, README.md
```

## Команды разработки

```bash
# зависимости
python -m venv backend/.venv && backend/.venv/bin/pip install -e "backend/[dev]"
cd frontend && npm install

# запуск
cd backend && .venv/bin/uvicorn app.main:app --reload   # API на :8000
cd backend && .venv/bin/python -m app.bot_main          # бот
cd frontend && npm run dev                              # SPA на :5173

# база
cd backend && .venv/bin/alembic upgrade head
cd backend && .venv/bin/alembic revision --autogenerate -m "описание"

# проверки
cd backend && .venv/bin/pytest -q
cd backend && .venv/bin/ruff check .
cd frontend && npm run lint && npm run test

# всё в Docker
docker compose up --build
```

На Windows путь к venv — `backend\.venv\Scripts\` вместо `backend/.venv/bin/`.
Полный список с вариантами для PowerShell — в разделе «Команды» файла `README.md`.

## Где что искать

| Вопрос                                   | Файл                                   |
|------------------------------------------|----------------------------------------|
| Переменные окружения, значения по умолчанию | `backend/app/core/config.py`, `.env.example` |
| Проверка initData Telegram               | `backend/app/core/security.py`         |
| Кто такой текущий пользователь / админ    | `backend/app/api/deps.py`              |
| Коды и формат ошибок                     | `backend/app/core/errors.py`           |
| Округление денег и веса                  | `backend/app/core/money.py`            |
| Сессии и определение диалекта БД         | `backend/app/core/db.py`               |
| Схема таблиц                             | `backend/app/models/`, `docs/CONTRACTS.md` §5 |
| Список эндпоинтов и форма ответов        | `docs/CONTRACTS.md` §7                 |
| Прокси, кэш, SPA fallback                | `frontend/nginx.conf`                  |
| Порты, тома, healthcheck                 | `docker-compose.yml`                   |

## Правила внесения изменений

* `docs/CONTRACTS.md` — источник истины. Расходится код с контрактом — правится код,
  а не контракт. Контракт меняет только главный агент.
* Новая переменная окружения добавляется одновременно в `app/core/config.py`,
  `.env.example` и в таблицу переменных в `README.md`.
* Изменение модели = новая миграция Alembic. Существующие миграции не редактируются.
* Новый эндпоинт: схема в `app/schemas/` -> логика в `app/services/` -> роут в `app/api/v1/`
  -> тип в `frontend/src/api/types.ts`. Ошибки — только через `AppError`.
* Тесты обязательны для расчётов, переходов статусов, авторизации и загрузки файлов.
* Пользовательские тексты — на русском. Комментарии и docstring — тоже на русском.
* Никаких секретов в коде и в git: только через переменные окружения.
* `entrypoint.sh` и другие shell-скрипты сохраняются с переводами строк LF.
* Перед коммитом: `ruff check .`, `pytest -q`, `npm run lint`, `npm run build`.
