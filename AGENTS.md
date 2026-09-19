# AGENTS.md

Общие правила для всех агентов, работающих над Telegram Mini App «Мясо для собак».
Пользовательская документация находится в `README.md`. Нормативные контракты между
слоями находятся в `docs/CONTRACTS.md`; менять их может только главный агент.

## Цель MVP

Один monorepo содержит:

- `backend/`: FastAPI API, aiogram 3 бот, SQLAlchemy 2 async, Alembic;
- `frontend/`: React + TypeScript + Vite Mini App с покупательским и admin UI;
- PostgreSQL 16 и локальное хранилище фотографий через Docker Compose;
- тесты, линтеры, typecheck, production build и русскую документацию.

Оплата в MVP — при получении. Реальных секретов, внешнего деплоя и `git push` быть не должно.

## Источник истины

Перед изменениями прочитать `docs/CONTRACTS.md`. При расхождении кода с контрактом
исправляется код, а не документ. Frontend использует `frontend/src/api/types.ts` как
единственный набор API-типов и не дублирует контракты в страницах.

## Архитектура backend

Зависимости направлены сверху вниз:

```text
app/api/v1/       HTTP: запрос -> сервис -> схема ответа
app/api/deps.py   DB/auth/admin FastAPI dependencies
app/services/     бизнес-правила и транзакции
app/repositories/ SQLAlchemy-запросы без бизнес-правил
app/models/       ORM
app/schemas/      Pydantic v2
app/storage/      Storage protocol + LocalStorage; будущий S3 адаптер
app/core/         config, db, errors, logging, security, rate limit, Decimal helpers
app/bot/          aiogram handlers, клавиатуры, polling и delivery outbox
```

Роуты не выполняют SQL и не содержат транзакционной логики. Сервисы не знают про
`Request`/`Response` и бросают только наследников `AppError`, не `HTTPException`.

## Зафиксированные модели

- `User`: `id`, уникальный `telegram_id`, username/name/phone, `is_admin`, timestamps.
- `Product`: name/description, `price_per_kg Numeric(10,2)`, `stock_kg Numeric(10,3)`,
  `photo_url`, `is_active`, timestamps, DB checks `>= 0`.
- `Order`: номер, user FK, status/delivery type, контакты/адрес (плоский и разобранный)/дата/comment,
  subtotal/delivery/total, `stock_restored_at`, timestamps.
- `OrderItem`: order/product FK и неизменяемый снимок имени, веса, цены и суммы.
- `NotificationOutbox`: уникальный event key, Telegram recipient, тип/payload, attempts,
  `next_attempt_at`, `sent_at`, `last_error`, timestamps для гарантированного повтора.

Полные поля, enum и ограничения — `docs/CONTRACTS.md` §§5–6.

## API и ошибки

Префикс `/api/v1`, healthcheck `GET /health`, статика `/uploads/*`. Полный список
эндпоинтов и JSON — `docs/CONTRACTS.md` §7.

Любая API-ошибка:

```json
{"error":{"code":"insufficient_stock","message":"Недостаточно товара","details":{}}}
```

Pydantic validation также преобразуется в этот формат. Русские сообщения, корректные
HTTP status; внутренние traceback и секреты наружу не выдаются.

## Telegram auth и права

- Mini App передаёт только raw `Telegram.WebApp.initData` в `X-Telegram-Init-Data`.
- Backend проверяет официальный HMAC-SHA256, `auth_date` TTL и берёт Telegram ID только
  из подписанного `user` JSON. Отдельный ID клиента не считается доказательством личности.
- Admin определяется на backend по `ADMIN_TELEGRAM_IDS`; сохранённый `is_admin`
  синхронизируется при каждом входе.
- `DEV_AUTH_ENABLED=false` по умолчанию и полностью игнорируется при production env.
- Все admin endpoints требуют `AdminUser`; заказ покупателя проверяется по `user_id`.
- Rate-limit ключ нельзя брать из доверенного клиентского `X-Telegram-Id`.

## Деньги, вес и остатки

- Только `Decimal`; `float` запрещён для денег и веса.
- Деньги `Numeric(10,2)`, вес `Numeric(10,3)`, `ROUND_HALF_UP`.
- JSON Decimal — строки. Минимальный вес и шаг: `0.100` кг.
- Backend повторно читает цену, активность и остаток; frontend-корзина не источник истины.
- Создание заказа блокирует товары `SELECT FOR UPDATE` в порядке ID, проверяет все
  позиции и списывает остаток в той же транзакции.
- Отмена блокирует заказ/товары, возвращает остатки один раз по `stock_restored_at`.
- Повторная установка текущего статуса и повторная отмена — успешный no-op.
- SQLite разрешён для быстрых тестов, но конкурентный тест должен выполняться на
  PostgreSQL и пропускаться с явной причиной только когда test DSN недоступен.

## Фотографии

Принимаются JPEG/PNG/WebP. Тип определяется по фактической сигнатуре, размер проверяется
потоково до записи, имя генерируется сервером, путь остаётся внутри `UPLOAD_DIR`. При
безопасной замене неиспользуемое старое фото удаляется. API работает через `Storage`, а
не напрямую с произвольным путём.

## Уведомления

Создание/смена статуса сначала фиксирует бизнес-транзакцию и outbox event. Отправка в
Telegram выполняется после commit/воркером. Ошибка Telegram никогда не откатывает заказ:
событие остаётся pending, `attempts/last_error/next_attempt_at` обновляются без токенов и
полных чувствительных данных в логах. Повтор использует уникальный event key.

## Команды

Windows (Git Bash вызывает native executables через пути `C:/...`):

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e '.[dev]'
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy app tests

# frontend
cd frontend
npm ci
npm run test
npm run lint
npm run typecheck
npm run build

# full stack
docker compose up --build -d
docker compose ps
```

Linux/container equivalents use `.venv/bin/python`. Перед коммитом агент запускает
проверки своей области и сообщает точные команды и результаты.

## TDD и качество

Для нового поведения: написать сфокусированный тест, увидеть ожидаемое падение, реализовать
минимальный код, увидеть прохождение, затем рефакторить. Не заменять обязательные функции
TODO, mocks или фиктивными API. Тесты должны проверять наблюдаемое поведение, а не только
наличие функций.

## Владение файлами при параллельной работе

Агенты работают в отдельных worktree/ветках от общего baseline и не трогают чужую зону.

### Backend Agent — `agent/backend`

Разрешено: `backend/app/models/**`, `schemas/**`, `repositories/**`, доменные
`services/{catalog,product,order}_service.py`, `api/v1/{catalog,orders,admin_*}.py`,
`backend/alembic/**`, `backend/tests/conftest.py`, backend domain/integration tests,
`backend/pyproject.toml`. Не менять auth/security/bot/frontend/root infra/docs.

### Telegram & Security Agent — `agent/telegram-security`

Разрешено: `backend/app/core/{security,ratelimit,logging}.py`, `backend/app/api/deps.py`,
`backend/app/services/{auth,notification}_service.py`, `backend/app/bot/**`,
`backend/app/bot_main.py`, security/bot/outbox tests. Если нужна ORM outbox-модель,
создать только `backend/app/models/notification.py` и отдельную новую миграцию с номером
`0002_security_outbox.py`; не менять существующие доменные модели/миграцию.

### Frontend Agent — `agent/frontend`

Разрешено: только `frontend/**`. Следовать существующему `src/api/types.ts` и REST
контракту. Реализовать все route pages, buyer/admin flows, tests и mobile Telegram theme.

### DevOps & Documentation Agent — `agent/devops-docs`

Разрешено: `docker-compose.yml`, `.env.example`, `.gitignore`, `Makefile`, `README.md`,
`backend/Dockerfile`, `backend/entrypoint.sh`, `backend/.dockerignore`,
`frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/.dockerignore`. Не менять код,
контракты, package manifests или `AGENTS.md`.

### QA Agent — после интеграции

Только независимый аудит и `docs/QA_REPORT.md`: конкретный файл/строка, severity,
воспроизведение и ожидаемое исправление. QA не исправляет код. Главный агент исправляет
все Critical/High и повторяет полный набор проверок.

## Git

- Не выполнять `git push`, deploy, publish и не создавать внешние ресурсы.
- Не переписывать/удалять чужие изменения ради конфликта без анализа.
- Каждый агент делает локальный commit и в финале перечисляет изменённые файлы.
- Главный агент проверяет `git diff` и фактические тесты перед merge/cherry-pick.
