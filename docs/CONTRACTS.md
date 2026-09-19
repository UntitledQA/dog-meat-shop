# Контракты проекта «Мясо для собак» (фиксирует главный агент)

Изменять этот документ может только главный агент. Субагенты обязаны следовать ему буквально.

## 1. Структура

```
backend/            FastAPI + aiogram + SQLAlchemy 2 + Alembic
  app/core/         config, db, errors, logging, security, ratelimit
  app/models/       SQLAlchemy ORM
  app/schemas/      Pydantic v2
  app/repositories/ доступ к данным
  app/services/     бизнес-логика
  app/api/v1/       HTTP-роуты
  app/bot/          aiogram 3
  app/storage/      абстракция хранилища файлов
  alembic/          миграции
  tests/            pytest
frontend/           React 18 + TS + Vite
```

## 2. Общие правила

* Деньги — `Numeric(10, 2)`, вес — `Numeric(10, 3)`. Только `Decimal`, никогда `float`.
* **Все Decimal сериализуются в JSON как строки** (`"890.00"`), чтобы не терять точность в JS.
  На фронте разбирать через `toNumber()`; отправлять на бэкенд тоже строкой.
* Даты/время — ISO 8601 UTC. `delivery_date` — `YYYY-MM-DD`.
* Enum в БД — `sa.Enum(..., native_enum=False)` (VARCHAR + CHECK), чтобы схема работала и в
  PostgreSQL, и в SQLite (тесты).
* Префикс API: `/api/v1`. Health-check: `GET /health` (без префикса).
* Код совместим с Python 3.10+ (в Docker — 3.12). Не использовать `StrEnum`, `typing.Self`.

## 3. Формат ошибок (единый для всего API)

```json
{ "error": { "code": "insufficient_stock", "message": "Недостаточно «Говядина»", "details": {} } }
```

| HTTP | code                        | когда                                     |
|------|-----------------------------|-------------------------------------------|
| 400  | `bad_request`               | некорректный запрос                       |
| 401  | `unauthorized`              | нет/битый initData                        |
| 403  | `forbidden`                 | не админ / чужой заказ                    |
| 404  | `not_found`                 | объект не найден                          |
| 409  | `conflict`                  | конфликт состояния                        |
| 409  | `insufficient_stock`        | не хватает остатка (`details.items[]`)    |
| 409  | `product_unavailable`       | товар скрыт/удалён                        |
| 409  | `invalid_status_transition` | недопустимый переход статуса              |
| 413  | `file_too_large`            | превышен `MAX_UPLOAD_SIZE_MB`             |
| 415  | `unsupported_media_type`    | не JPEG/PNG/WebP                          |
| 422  | `validation_error`          | ошибки Pydantic (`details.fields[]`)      |
| 429  | `rate_limited`              | превышен лимит (заголовок `Retry-After`)  |
| 500  | `internal_error`            | необработанное исключение                 |

`details.items` для `insufficient_stock`:
`[{"product_id": 1, "product_name": "...", "requested_kg": "3.000", "available_kg": "1.500"}]`

## 4. Аутентификация

* Заголовок запроса: **`X-Telegram-Init-Data: <raw initData>`**.
* Проверка по официальному алгоритму: `secret = HMAC_SHA256(key=b"WebAppData", msg=BOT_TOKEN)`,
  `hash = HMAC_SHA256(key=secret, msg=data_check_string)`, сравнение через `hmac.compare_digest`.
* `auth_date` не старше `INIT_DATA_TTL_SECONDS` (по умолчанию 86400).
* `user_id` берётся **только** из проверенного initData. Любой `user_id` из тела/квери игнорируется.
* Админ = `telegram_id in ADMIN_TELEGRAM_IDS` (плюс флаг `users.is_admin`, синхронизируется при входе).
* Dev-режим: только если `DEV_AUTH_ENABLED=true` **и** `ENVIRONMENT != production`.
  Тогда допускается заголовок `X-Dev-Telegram-Id` (или `DEV_TELEGRAM_ID`). По умолчанию выключен.
* Rate limiter не доверяет `X-Telegram-Id` или другому отдельному идентификатору клиента:
  до успешной auth используется IP, после auth — только проверенный `request.state.telegram_id`.

Точка интеграции (пишет главный агент, менять нельзя):

```python
# app/api/deps.py
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser   = Annotated[User, Depends(get_current_admin)]
DbSession   = Annotated[AsyncSession, Depends(get_db)]
```

```python
# app/core/security.py  (реализует Telegram/Security-агент)
@dataclass
class TelegramUserData:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None

def parse_and_verify_init_data(raw: str, bot_token: str, ttl_seconds: int) -> TelegramUserData
# бросает app.core.errors.UnauthorizedError с понятным русским сообщением
```

## 5. Модели БД (создаёт главный агент, менять нельзя)

`users(id, telegram_id UNIQUE, username, first_name, last_name, phone, is_admin, created_at, updated_at)`

`products(id, name NOT NULL, description, price_per_kg NUMERIC(10,2) >= 0, stock_kg NUMERIC(10,3) >= 0,
photo_url, is_active, created_at, updated_at)`

`orders(id, order_number UNIQUE, user_id FK, status, delivery_type, customer_name, phone, address,
address_city, address_street, address_house, address_postal_code, address_lat, address_lon,
delivery_date, comment, subtotal, delivery_price, total, stock_restored_at,
created_at, updated_at)`

Колонки `address_*` заполняются из сервиса адресных подсказок и все необязательны:
подсказка может не знать индекс или номер дома, и это не повод отклонять заказ.
Координаты — `Numeric(9, 6)`, только `Decimal`, в JSON строкой (см. §2).
Отдельного поля «интервал времени доставки» нет: оно удалено миграцией 0003.

`order_items(id, order_id FK CASCADE, product_id FK SET NULL, product_name, weight_kg,
price_per_kg, line_total)`

Других таблиц в MVP нет. Уведомления Telegram **не** хранятся в БД (см. ниже).

* `OrderStatus`: `confirmed | delivering | completed | cancelled`
  (подписи: «Подтверждён», «Доставляется», «Готово», «Отменён»).
  Колонка — VARCHAR(20) + CHECK; enum объявлен с `create_constraint=True`,
  без него SQLAlchemy 1.4+ ограничение не создаёт.
* `DeliveryType`: `delivery | pickup`
* `order_number` = `ORD-YYYYMMDD-NNNNN` (NNNNN — id заказа с ведущими нулями): уникально без гонок.
* `stock_restored_at` — метка возврата остатка, гарантирует однократность возврата.

### Доставка уведомлений

Недоставленные сообщения складываются в **очередь в памяти процесса**
(`deque(maxlen=500)` в `app/services/notification_service.py`), повторная отправка —
`await retry_failed()`. Осознанное ограничение MVP: очередь не переживает рестарт и не
общая для нескольких воркеров. Полноценный transactional outbox в БД — задача после MVP;
интерфейс `notify_new_order` / `notify_order_status_changed` при этом не изменится.

## 6. Правила расчёта

1. Корзина фронта — **не источник истины**. Бэкенд заново читает товары из БД.
2. `line_total = round_money(weight_kg * price_per_kg)`, ROUND_HALF_UP до 2 знаков.
3. `subtotal = Σ line_total`; `delivery_price = DELIVERY_PRICE` для `delivery`, `0` для `pickup`;
   `total = subtotal + delivery_price`.
4. Вес: минимум `0.100`, шаг `0.100`, не больше остатка. Квантование до 3 знаков.
5. Создание заказа — одна транзакция: `SELECT ... FOR UPDATE` по товарам, отсортированным по `id`
   (защита от дедлоков), проверка `is_active` и `stock_kg`, списание, вставка заказа.
   На SQLite (тесты) `FOR UPDATE` пропускается — диалект определяется в рантайме.
6. Отмена — транзакция с блокировкой заказа: если `status == cancelled` → возврат как есть
   (идемпотентно, остаток не возвращается повторно); иначе восстановить остатки,
   проставить `stock_restored_at`, статус `cancelled`.
7. Заказ создаётся сразу в статусе `confirmed` — отдельного «нового» нет.
   Переходы: самовывоз `confirmed → completed`; доставка
   `confirmed → delivering → completed` (допускается и сразу `completed`).
   `delivering` запрещён заказам с `pickup` — проверяется на бэкенде, 409
   `invalid_status_transition`. `cancelled` — из любого статуса, кроме
   `completed`/`cancelled`. Установка того же статуса — no-op 200 без уведомления.

## 7. REST API

### Покупатель
| Метод | Путь | Параметры | Ответ |
|---|---|---|---|
| POST | `/api/v1/auth/telegram` | — (initData в заголовке) | `User` |
| GET  | `/api/v1/me` | — | `User` |
| GET  | `/api/v1/settings` | — | `AppSettings` |
| GET  | `/api/v1/addresses/suggest` | `query` (3–200), `limit` (1–10, по умолчанию 5) | `AddressSuggestions` |
| GET  | `/api/v1/catalog` | `limit`, `offset` | `Page<Product>` |
| GET  | `/api/v1/catalog/{id}` | — | `Product` |
| POST | `/api/v1/orders` | `OrderCreate` | `Order` (201) |
| GET  | `/api/v1/orders` | `limit`, `offset` | `Page<Order>` |
| GET  | `/api/v1/orders/{id}` | — | `Order` (403 на чужой) |

### Администратор (все требуют `AdminUser`)
| Метод | Путь | Параметры | Ответ |
|---|---|---|---|
| GET   | `/api/v1/admin/products` | `include_inactive`, `search`, `limit`, `offset` | `Page<Product>` |
| POST  | `/api/v1/admin/products` | `ProductCreate` | `Product` (201) |
| PATCH | `/api/v1/admin/products/{id}` | `ProductUpdate` (partial) | `Product` |
| POST  | `/api/v1/admin/products/{id}/archive` | — | `Product` |
| POST  | `/api/v1/admin/products/{id}/restore` | — | `Product` |
| POST  | `/api/v1/admin/products/{id}/photo` | multipart `file` | `Product` |
| POST  | `/api/v1/admin/uploads/photo` | multipart `file` | `{"photo_url": "/uploads/..."}` |
| GET   | `/api/v1/admin/orders` | `status`, `limit`, `offset` | `Page<AdminOrder>` |
| GET   | `/api/v1/admin/orders/{id}` | — | `AdminOrder` |
| PATCH | `/api/v1/admin/orders/{id}/status` | `{"status": "confirmed"}` | `AdminOrder` |

### Схемы JSON

```jsonc
// Page<T>
{ "items": [], "total": 0, "limit": 20, "offset": 0 }

// User
{ "id": 1, "telegram_id": 123, "username": "ivan", "first_name": "Иван",
  "last_name": null, "phone": null, "is_admin": false, "created_at": "..." }

// AppSettings
{ "delivery_price": "300.00", "pickup_address": "...", "min_weight_kg": "0.100",
  "weight_step_kg": "0.100", "currency": "RUB", "payment_note": "Оплата при получении" }

// AddressSuggestions — ответ GET /api/v1/addresses/suggest.
// Всегда 200. enabled=false означает, что подсказки выключены настройкой либо
// не настроен ключ провайдера: поле адреса должно продолжать работать как обычный
// текстовый ввод. Пустой items при enabled=true — короткий запрос (<3 символов)
// или недоступный внешний сервис; это тоже не ошибка.
{ "enabled": true, "provider": "photon",
  "items": [ { "value": "Омск, ул. 2-я Солнечная, 31А", "city": "Омск",
               "street": "2-я Солнечная", "house": "31А", "postal_code": "644073",
               "lat": "54.989342", "lon": "73.368212" } ] }

// Product
{ "id": 1, "name": "Говядина", "description": "...", "price_per_kg": "890.00",
  "stock_kg": "12.500", "photo_url": "/uploads/ab.jpg", "is_active": true,
  "in_stock": true, "created_at": "...", "updated_at": "..." }

// OrderCreate
{ "items": [ { "product_id": 1, "weight_kg": "2.0" } ],
  "delivery_type": "delivery", "customer_name": "Иван", "phone": "+79991234567",
  "address": "Омск, ул. 2-я Солнечная, 31А", "address_city": "Омск",
  "address_street": "2-я Солнечная", "address_house": "31А",
  "address_postal_code": "644073", "address_lat": "54.989342", "address_lon": "73.368212",
  "delivery_date": "2026-09-08", "comment": "" }

// Order  (AdminOrder = Order + "user": User)
{ "id": 1, "order_number": "ORD-20260907-00001", "status": "confirmed",
  "status_label": "Подтверждён", "delivery_type": "delivery", "customer_name": "Иван",
  "phone": "+79991234567", "address": "Омск, ул. 2-я Солнечная, 31А",
  "address_city": "Омск", "address_street": "2-я Солнечная", "address_house": "31А",
  "address_postal_code": "644073", "address_lat": "54.989342", "address_lon": "73.368212",
  "delivery_date": "2026-09-08", "comment": "", "subtotal": "1780.00",
  "delivery_price": "300.00", "total": "2080.00", "payment_method": "cash_on_delivery",
  "items": [ { "id": 1, "product_id": 1, "product_name": "Говядина",
               "weight_kg": "2.000", "price_per_kg": "890.00", "line_total": "1780.00" } ],
  "created_at": "...", "updated_at": "..." }
```

## 8. Загрузка изображений

* Разрешено: `image/jpeg`, `image/png`, `image/webp` — тип определяется по **сигнатуре байтов**,
  не по расширению и не по заголовку `Content-Type`.
* Лимит: `MAX_UPLOAD_SIZE_MB` (по умолчанию 5), проверка потоково, до записи на диск.
* Имя файла: `secrets.token_hex(16) + ext`, путь собирается только внутри `UPLOAD_DIR`.
* Отдача: `GET /uploads/{filename}` (StaticFiles), `photo_url` — относительный путь.
* Интерфейс `app/storage/base.py: Storage` с методами `save(data, ext) -> str`, `delete(url)`.
  Реализация `LocalStorage`; позже — `S3Storage`.
* При замене фото старый файл удаляется, если больше не используется ни одним товаром.

## 9. Переменные окружения

`BOT_TOKEN`, `BOT_USERNAME`, `BOT_MODE`(polling|webhook), `WEBAPP_URL`, `PUBLIC_BASE_URL`,
`DATABASE_URL`, `ADMIN_TELEGRAM_IDS`, `DELIVERY_PRICE`, `PICKUP_ADDRESS`, `ALLOWED_ORIGINS`,
`UPLOAD_DIR`, `MAX_UPLOAD_SIZE_MB`, `DEV_AUTH_ENABLED`, `DEV_TELEGRAM_ID`, `ENVIRONMENT`,
`LOG_LEVEL`, `INIT_DATA_TTL_SECONDS`, `RATE_LIMIT_AUTH`, `RATE_LIMIT_ORDERS`, `RATE_LIMIT_UPLOADS`,
`RATE_LIMIT_ADDRESSES`, `ADDRESS_SUGGEST_PROVIDER`(photon|dadata|none), `DADATA_API_KEY`,
`ADDRESS_SUGGEST_TIMEOUT_SECONDS`, `ADDRESS_SUGGEST_USER_AGENT`.

Ключ провайдера подсказок живёт только в окружении сервера и в браузер не уходит —
именно поэтому подсказки идут через backend-прокси, а не прямым запросом из Mini App.

## 10. Фронтенд

* Роуты: `/`, `/product/:id`, `/cart`, `/checkout`, `/orders`, `/orders/:id`,
  `/admin`, `/admin/products`, `/admin/products/new`, `/admin/products/:id`,
  `/admin/orders`, `/admin/orders/:id`.
* Нижняя навигация: Каталог / Корзина (бейдж) / Заказы (+ Админ для админов).
* API-клиент один: `src/api/client.ts` — добавляет `X-Telegram-Init-Data`, разбирает формат ошибок.
* Типы API — один файл `src/api/types.ts`, строго по разделу 7.
* Состояние корзины — Zustand + `localStorage`, хранит `product_id`, снимок имени/цены/фото и вес.
* Тема — CSS-переменные Telegram (`--tg-theme-*`) с фолбэками.

## 11. Telegram-уведомления и повторная доставка

* `/start`, `/catalog`, `/orders`, `/help` возвращают кнопку `web_app` на `WEBAPP_URL`;
  `/orders` открывает Mini App по пути `/orders`.
* Для нового заказа создаются outbox-события покупателю и каждому администратору. Сообщение
  покупателю содержит номер, состав, вес, доставку и итог; сообщение администратору дополнительно
  содержит имя, телефон, адрес и комментарий.
* При фактическом изменении статуса создаётся событие покупателю. Повторная установка того же
  статуса не создаёт новое событие.
* Polling-процесс бота параллельно обрабатывает pending outbox. Ошибка Telegram API не влияет
  на уже committed заказ и оставляет событие для retry с ограниченным exponential backoff.
* BOT_TOKEN, raw initData и полные чувствительные данные не пишутся в structured logs.
