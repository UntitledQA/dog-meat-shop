# Независимое ревью: качество, безопасность, готовность к запуску

Проект: Telegram Mini App «Мясо для собак».
Дата ревью: 2026-09-08. Ревизия: рабочее дерево ветки `master` поверх коммита
`189c265 chore: establish MVP baseline and contracts`.
Проверял: QA & Security Review Agent. Правки в код не вносились — только этот документ.

> Во время ревью в дереве параллельно работали другие агенты (в частности над `frontend/**`).
> Все номера строк ниже перепроверены на состоянии дерева на момент публикации отчёта;
> если файл изменится, сверяйтесь с процитированным фрагментом кода, а не с номером строки.

---

## 1. Краткое резюме

| Приоритет  | Находок |
|------------|---------|
| `critical` | 1       |
| `high`     | 3       |
| `medium`   | 7       |
| `low`      | 8       |
| **Всего**  | **19**  |

**Общая оценка.** Backend сделан аккуратно и по контракту: слои не протекают, авторизация
Telegram реализована по официальному алгоритму и не отключается в тестах, деньги и вес — только
`Decimal`, списание остатков идёт в одной транзакции с `SELECT ... FOR UPDATE`, отмена
идемпотентна по двум независимым признакам, загрузка файлов проверяется по сигнатуре байтов,
тексты для Telegram экранируются через `html.escape`. 193 теста проходят, `ruff` чист.
Основные инварианты из `CLAUDE.md` соблюдены — по каждому ниже есть отдельная запись
в разделе «Проверено и признано корректным».

Тем не менее к продакшену проект **не готов**:

* один `critical` полностью ломает работу приложения в штатном сценарии развёртывания
  (`docker compose up`) — все запросы SPA уходят по двойному префиксу `/api/v1/api/v1/...`;
* rate limiting **фактически отсутствует**: он ключуется по заголовку, который присылает сам
  клиент. Обход подтверждён экспериментально и прямо противоречит §4 контракта, при этом
  существующий тест закрепляет неверное поведение;
* каждый авторизованный запрос (в том числе `GET /settings`) вычитывает всю историю заказов
  пользователя со всеми позициями — деградация растёт линейно с числом заказов.

После устранения `critical` и трёх `high` проект можно выпускать в пилот; `medium` желательно
закрыть до боевой нагрузки.

Отдельно: проверка **не** охватывает страницы фронтенда (`frontend/src/pages/**`,
`frontend/src/components/**`) — там параллельно работает другой агент. Единственная находка,
затрагивающая фронтенд (№1), — интеграционная и заведена по инфраструктурным файлам.

---

## 2. Таблица находок

| # | Приоритет | Область | Файл:строка | Суть | Как воспроизвести | Рекомендация |
|---|-----------|---------|-------------|------|-------------------|--------------|
| 1 | `critical` | Инфраструктура / интеграция | `docker-compose.yml:134`; `.env.example:165`; `frontend/Dockerfile:33`; `frontend/src/api/client.ts:14,19`; `frontend/src/api/endpoints.ts:24` | Двойной префикс API. `endpoints.ts` подставляет `API_PREFIX = '/api/v1'`, а `request()` дополнительно приклеивает `API_BASE_URL`, который в Docker собирается со значением `VITE_API_BASE_URL=/api/v1`. Итог — `/api/v1/api/v1/catalog`, nginx проксирует это на backend, backend отвечает 404. Тот же дефект в `resolveAssetUrl()`: фотографии запрашиваются как `/api/v1/uploads/xxx.jpg`, хотя `StaticFiles` смонтирован на `/uploads`. | `cp .env.example .env`, заполнить `BOT_TOKEN`/`ADMIN_TELEGRAM_IDS`, `docker compose up --build`, открыть `http://localhost:5173` → во вкладке Network все вызовы API 404. Статически: `API_BASE_URL('/api/v1') + p('/catalog') = '/api/v1/api/v1/catalog'`. | Выбрать один источник префикса. Минимальная правка на стороне инфраструктуры: `VITE_API_BASE_URL=` (пусто) в `.env.example` и `${VITE_API_BASE_URL:-}` в `docker-compose.yml` — тогда `API_PREFIX` из `client.ts` остаётся единственным префиксом, а `resolveAssetUrl` вернёт корректный `/uploads/...`. Согласовать с агентом фронтенда, добавить smoke-проверку в CI. |
| 2 | `high` | Безопасность / rate limiting | `backend/app/core/ratelimit.py:262-289,307-310`; тест, закрепляющий дефект: `backend/tests/test_ratelimit.py:153-163` | Ключ корзины лимитера берётся из **непроверенных** заголовков `X-Telegram-Id` / `X-Dev-Telegram-Id` (и из непроверенного `initData`). §4 контракта требует ровно обратного: «до успешной auth используется IP, после auth — только проверенный `request.state.telegram_id`». Достаточно менять значение заголовка на каждом запросе, чтобы получать свежую корзину, — лимит перестаёт существовать. | Подтверждено экспериментально (лог в §5): при `RATE_LIMIT_ORDERS=2/60` пять одинаковых `POST /api/v1/orders` дают `[201, 201, 429, 429, 429]`; те же пять запросов с валидным initData **плюс** подставным `X-Telegram-Id: 900000+i` дают `[201, 201, 201, 201, 201]`. | Убрать `X-Telegram-Id`/`X-Dev-Telegram-Id`/разбор initData из `_telegram_id_from_headers`. До auth ключевать по IP; после auth (как ASGI-middleware, выполняемое после зависимостей, либо как decorator на роуте) — по `request.state.telegram_id`. Тест `test_limit_applies_per_telegram_id` переписать так, чтобы он проверял ключевание по **проверенной** личности, и добавить негативный тест «подстановка `X-Telegram-Id` не сбрасывает лимит». |
| 3 | `high` | Безопасность / инфраструктура | `docker-compose.yml:75-79` | `uvicorn` запускается с `--proxy-headers --forwarded-allow-ips "*"`, и при этом порт backend опубликован на хост (`"${BACKEND_PORT:-8000}:8000"`). Uvicorn перезаписывает `scope["client"]` значением `X-Forwarded-For` **от любого пира**, поэтому `request.client.host` (то есть запасной ключ лимитера `ip:`) тоже подделывается. Защита, ради которой в `ratelimit.py:58` выставлено `TRUST_PROXY_HEADERS = False`, обходится на уровень ниже. Дополнительно прямой доступ к :8000 минует `client_max_body_size 10m` из nginx. | `curl -H "X-Forwarded-For: 1.2.3.4" http://localhost:8000/health` — в логах uvicorn клиентом будет 1.2.3.4. В связке с №2 лимитер не ограничивает ничего. | Не публиковать порт backend наружу (или `"127.0.0.1:8000:8000"`), а `--forwarded-allow-ips` сузить до подсети Compose/адреса прокси. В README раздел «Рекомендации для production» уже советует первое — стоит сделать это значением по умолчанию, а не советом. |
| 4 | `high` | Производительность / DoS | `backend/app/models/user.py:35` (`orders: ... lazy="selectin"`), совместно с `backend/app/models/order.py:89-95` | `User.orders` грузится жадно, поэтому **любой** авторизованный запрос вытягивает всю историю заказов пользователя, а через `Order.items` — ещё и все позиции этих заказов. Это происходит даже там, где заказы не нужны (`GET /settings`, `GET /catalog`, `GET /me`). Объём данных на запрос растёт линейно с числом заказов клиента и не ограничен ничем. | Замер (§5): у пользователя 15 заказов, `GET /api/v1/settings` → **3** SQL-запроса, из них `SELECT orders ... WHERE user_id IN (...)` и `SELECT order_items ... WHERE order_id IN (...)`; `GET /api/v1/catalog` → 5 запросов с теми же двумя; `GET /api/v1/orders/{id}` → 6. | Заменить на `lazy="raise"` (историю читает только `OrderRepository.list_for_user` с пагинацией) либо на `lazy="select"`. `Order.user` с `lazy="selectin"` оставить — он нужен для `AdminOrderOut`. Добавить тест, фиксирующий число SQL-запросов на `GET /settings`. |
| 5 | `medium` | Валидация / формат ошибок | `backend/app/schemas/product.py:55-65`; `backend/app/services/product_service.py:82,90` | `ProductUpdate` разрешает явный `null` для обязательных колонок, а `update_product` применяет `model_dump(exclude_unset=True)` дословно через `setattr`. Явный `null` доходит до БД и падает на `NOT NULL` → 500 `internal_error` вместо 422. | `PATCH /api/v1/admin/products/1` с телом `{"name": null}` (а также `price_per_kg`, `stock_kg`, `is_active`) → 500, в логе `IntegrityError: NOT NULL constraint failed: products.name`. Подтверждено для всех четырёх полей. | В `ProductUpdate` запретить явный `null` для обязательных полей (`model_validator`, отбрасывающий `None` у ключей из `exclude_unset`) либо фильтровать `values = {k: v for k, v in values.items() if v is not None or k in NULLABLE_FIELDS}`. Добавить тест на каждое поле. |
| 6 | `medium` | Валидация / DoS | `backend/app/schemas/common.py:63-71`; `backend/app/core/money.py:31,35` | `_coerce_decimal` принимает любую строку, которую разбирает `Decimal(...)`. Pydantic отсекает `NaN`/`Infinity` («Input should be a finite number»), но огромные показатели степени проходят, и `quantize()` бросает `decimal.InvalidOperation` — это `ArithmeticError`, а не `ValueError`, поэтому Pydantic его не перехватывает. Наружу уходит 500 `internal_error`, в лог — трейсбек. | `POST /api/v1/orders` с `{"items":[{"product_id":1,"weight_kg":"1e1000"}]}` → 500, в логе `unhandled_error error=InvalidOperation`. То же для `POST /api/v1/admin/products` с `{"price_per_kg":"1e1000"}`. Неавторизованный вызов не проходит (нужен валидный initData), поэтому это не анонимный DoS, а деградация от любого зарегистрированного клиента. | В `_coerce_decimal` ограничить диапазон: отбрасывать значения с `abs(exponent) > 30` и не-конечные, бросая `ValueError` (тогда Pydantic вернёт 422). Дополнительно обернуть `round_money`/`round_weight` в перехват `InvalidOperation` → `ValueError`. Добавить параметризованный тест на `NaN`, `Infinity`, `1e1000`. |
| 7 | `medium` | Бот / документация | `backend/app/bot_main.py:86-87`; `backend/app/bot/runner.py:76-115`; `backend/app/main.py` (роут отсутствует); `README.md:893-925`; `.env.example:139-147` | Режим `BOT_MODE=webhook` регистрирует webhook в Telegram, но HTTP-эндпоинта, принимающего апдейты, в приложении **нет**: `WEBHOOK_PATH` используется только для сборки URL, `WEBHOOK_SECRET` нигде не сверяется. `grep -rn "webhook" backend/app` вне `runner.py`/`bot_main.py` даёт только объявления в `config.py`. При этом README рекомендует webhook как продакшен-путь и утверждает, что «апдейты принимает backend». | Выставить `BOT_MODE=webhook`, запустить `python -m app.bot_main` — команда отрапортует об успехе, но бот перестанет отвечать: Telegram будет получать 404 на `/telegram/webhook`. | Либо реализовать роут (`POST {WEBHOOK_PATH}` со сверкой `X-Telegram-Bot-Api-Secret-Token` через `hmac.compare_digest` и `dispatcher.feed_webhook_update`), либо явно пометить режим как нереализованный в README/`.env.example` и заставить `bot_main` завершаться с ошибкой при `BOT_MODE=webhook`. |
| 8 | `medium` | Производительность / устойчивость | `backend/app/services/order_service.py:241`; `backend/app/services/notification_service.py:172-180,96-169` | Уведомления Telegram отправляются **внутри** HTTP-запроса: `create_order` дожидается `notify_new_order`, а тот последовательно шлёт сообщение покупателю и каждому админу с паузой 0.05 c. При недоступном или медленном Telegram время ответа `POST /orders` растёт на таймаут aiogram, умноженный на число получателей. §11 контракта подразумевает асинхронную обработку («polling-процесс бота параллельно обрабатывает pending outbox»). | Заблокировать исходящие к `api.telegram.org` (или подставить бота с большим таймаутом) и оформить заказ: заказ уже закоммичен, но ответ покупателю задерживается. | Вынести отправку в `asyncio.create_task` / `BackgroundTasks` (заказ уже закоммичен, откатывать нечего) или в отдельный процесс-обработчик очереди. Ошибки уже гасятся — менять надо только момент вызова. |
| 9 | `medium` | Контракт / уведомления | `backend/app/services/notification_service.py:277-304` | `retry_failed()` не вызывается **нигде**: ни в `run_polling`, ни фоновой задачей, ни админ-эндпоинтом (`grep -rn "retry_failed" backend/` даёт только определение и `__all__`). Очередь `_failed` наполняется и никогда не разбирается. Плюс она живёт в процессе API, а «polling-процесс бота» из §11 контракта — это другой процесс с собственной пустой очередью. Экспоненциального backoff, обещанного §11, тоже нет — только `MAX_DELIVERY_ATTEMPTS = 3`. README (раздел «Ограничения MVP») честно пишет, что повторов нет, то есть код соответствует README, но не `docs/CONTRACTS.md`. | Статически: `grep -rn "retry_failed" backend/app backend/tests`. | Либо запускать `retry_failed()` периодической задачей в процессе API (там же, где очередь), либо убрать неиспользуемый код и привести §11 контракта в соответствие с реальностью. Контракт правит только главный агент. |
| 10 | `medium` | Инфраструктура / секреты | `docker-compose.yml:24-34`; `.env.example:53-58` | Пароль PostgreSQL по умолчанию `meat/meat` и порт БД опубликован на хост (`"${DB_PORT:-5433}:5432"`). Кто угодно, кто дотянется до хоста по 5433, получает полный доступ к базе с общеизвестными учётными данными. README упоминает это в «Рекомендациях для production», но дефолт остаётся небезопасным. | `psql -h <хост> -p 5433 -U meat -d meat` с паролем `meat`. | Не публиковать порт БД по умолчанию (или `127.0.0.1:5433:5432`), убрать дефолт `:-meat` для `POSTGRES_PASSWORD`, чтобы Compose падал при незаполненной переменной. |
| 11 | `medium` | Тесты | `backend/tests/test_admin_products.py:307-322`; отсутствующие сценарии — см. §4 | Пробелы в покрытии на самых чувствительных местах: (а) `test_photo_replacement_updates_url` проверяет только смену URL, но не то, что старый файл удалён с диска — а это прямое требование §8 контракта; (б) нет ни одного теста на `file_too_large` (413) — весь потоковый контроль размера не покрыт; (в) до этого ревью не было теста на WebP (самая хитрая ветка `detect_image_extension` с проверкой байтов 8-11); (г) нет тестов на `LocalStorage._to_path` — функцию, которая одна отвечает за защиту от выхода за `UPLOAD_DIR`; (д) нет теста на конкурентное создание заказов. | `grep -rn "413\|file_too_large\|webp\|_to_path" backend/tests` — совпадений нет (кроме `MAX_UPLOAD_SIZE_MB` в `conftest.py`). | Добавить: проверку `storage.exists(old_url) is False` после замены фото; загрузку файла > `MAX_UPLOAD_SIZE_MB` → 413 `file_too_large`; загрузку валидного WebP → 201; юнит-тесты `_to_path` на `../`, `/`, `\`, `\x00`, чужой префикс; тест на две параллельные корутины `create_order` с общей сессией (хотя бы фиксирующий, что суммарное списание не превышает остаток). |
| 12 | `low` | Конкурентность (PostgreSQL) | `backend/app/repositories/product_repo.py:92-106` | `lock_by_ids` строит `SELECT ... FOR UPDATE` без `execution_options(populate_existing=True)`. Документация SQLAlchemy требует `populate_existing()` при блокирующем чтении через ORM: если объект уже в identity map сессии, строка в БД будет заблокирована, но ORM вернёт **старые** значения атрибутов. Сейчас это не эксплуатируется — ни один вызывающий код не загружает `Product` в ту же сессию раньше (в `create_order` и `_restore_stock` товары читаются впервые), — но защита держится на порядке вызовов, а не на коде. Сравните с `OrderRepository.lock_order:61-68`, где `populate_existing=True` проставлен. | Ревью кода. Проявится при первом же рефакторинге, добавляющем чтение товара до блокировки. | Добавить `.execution_options(populate_existing=True)` в `lock_by_ids` — по аналогии с `lock_order`. |
| 13 | `low` | Конкурентность (PostgreSQL) | `backend/app/services/order_service.py:197-225` | Заказ вставляется с `order_number=""`, номер проставляется вторым `UPDATE` в той же транзакции. Колонка под уникальным индексом `ix_orders_order_number`, поэтому вторая параллельная транзакция блокируется на индексной записи `''` до коммита первой — создание заказов сериализуется глобально, даже для разных товаров. Дубликата ключа при этом не возникает (значение всегда обновляется до коммита), так что корректность не нарушена. | Два одновременных `POST /orders` по разным товарам на PostgreSQL: второй ждёт коммита первого. | Не критично для MVP. Чище — брать `nextval` последовательности отдельным запросом до `INSERT` и вставлять готовый `order_number`. |
| 14 | `low` | Валидация / админка | `backend/app/schemas/product.py:51,64`; `backend/app/services/product_service.py:90` | `photo_url` принимается как произвольная строка до 512 символов: проходят `javascript:alert(1)`, `http://evil.tld/x.png`, `/uploads/../../etc/passwd`. Хранилище защищено (`LocalStorage._to_path` отбрасывает такие значения при удалении, `StaticFiles` — при отдаче), эксплуатация требует прав администратора, а `javascript:` в `<img src>` инертен. Остаётся утечка адресов клиентов на внешний домен и риск при любом будущем использовании `photo_url` в `<a href>`. | `POST /api/v1/admin/products` с `{"name":"X","price_per_kg":"1.00","photo_url":"javascript:alert(1)"}` → 201, значение сохраняется как есть. | Валидировать `photo_url` регуляркой `^/uploads/[0-9a-f]{32}\.(jpg|png|webp)$` — этого достаточно, потому что значение всегда генерирует сервер. |
| 15 | `low` | Инструменты / документация | `README.md:657` («`mypy app`»); ошибки в `backend/app/core/logging.py:56`, `backend/app/api/v1/catalog.py:34`, `backend/app/api/v1/orders.py:55`, `backend/app/api/v1/admin_orders.py:40`, `backend/app/api/v1/admin_products.py:43` | README документирует `mypy app` как часть проверок, но команда падает с 5 ошибками. Четыре из них однотипны: в `Page[XOut](items=orders, ...)` передаются ORM-объекты, а не Pydantic-модели (в рантайме FastAPI приводит их через `response_model`, поэтому это не баг, но и не «чисто»). | `cd backend && .venv/Scripts/python.exe -m mypy app` → `Found 5 errors in 5 files`. | Либо привести код к типам (`items=[XOut.model_validate(o) for o in orders]`), либо добавить точечные `# type: ignore` с пояснением, либо убрать `mypy` из README/CI-обещаний. Сейчас документация обещает больше, чем есть. |
| 16 | `low` | Контракт / формат ошибок | `backend/app/core/errors.py:139,152` | Код `method_not_allowed` (HTTP 405) в таблице §3 контракта отсутствует. Формат ответа при этом соблюдён. | `DELETE /api/v1/orders` с валидным initData → `405 {"error":{"code":"method_not_allowed",...}}`. | Либо свести 405 к `bad_request`, либо внести код в §3 контракта (правит главный агент). |
| 17 | `low` | Безопасность / авторизация | `backend/app/core/security.py:100` | `isinstance(user.get("id"), int)` истинно для `bool`: `{"id": true}` даст `telegram_id = 1`. Эксплуатация невозможна — такой initData нужно подписать токеном бота, — но проверка типа неточная. | Юнит-вызов `parse_and_verify_init_data` с корректно подписанным `user={"id": true}`. | Добавить `and not isinstance(user.get("id"), bool)` и проверку `> 0`. |
| 18 | `low` | Конфигурация | `backend/app/core/config.py:75-77` | `is_production` сравнивает `self.environment.lower()` без `.strip()`. Значение вида `"production "` (например, из окружения оркестратора, не проходящего через dotenv-парсер) даст `is_production == False` и **разрешит dev-авторизацию** в бою, если `DEV_AUTH_ENABLED=true`. Риск низкий: нужна и опечатка, и включённый dev-режим. | Установить `ENVIRONMENT="production "` и `DEV_AUTH_ENABLED=true` в окружении процесса → `settings.dev_auth_allowed is True`. | `self.environment.strip().lower()`. Заодно стоит логировать критическое предупреждение при старте, если `dev_auth_allowed` истинно. |
| 19 | `low` | Раскрытие информации | `backend/app/main.py:67-69` | `/docs` и `/openapi.json` открыты всегда, включая production. Секретов схема не содержит, но выдаёт полную карту админ-эндпоинтов. Сейчас усугубляется находкой №3 (порт 8000 наружу). | `curl http://localhost:8000/openapi.json`. | Отключать при `settings.is_production` (`docs_url=None, openapi_url=None`) либо закрывать на уровне прокси. |

---

## 3. Проверено и признано корректным

Ниже — то, что я проверял целенаправленно и где **не нашёл** проблем. Это не «всё остальное»,
а конкретный список.

### 3.1 Соответствие контракту §7

Все 18 эндпоинтов из §7 существуют, пути и коды ответов совпадают:

* Покупатель: `POST /api/v1/auth/telegram` (200), `GET /me`, `GET /settings`, `GET /catalog`,
  `GET /catalog/{id}`, `POST /orders` (**201**), `GET /orders`, `GET /orders/{id}`.
* Админ: `GET|POST /admin/products` (POST — **201**), `PATCH /admin/products/{id}`,
  `POST /admin/products/{id}/archive|restore|photo`, `POST /admin/uploads/photo` (**201**),
  `GET /admin/orders`, `GET /admin/orders/{id}`, `PATCH /admin/orders/{id}/status`.
* `Page<T>` возвращается ровно в форме `{"items", "total", "limit", "offset"}` — проверено
  живым ответом `GET /catalog`.
* Формы `User`, `AppSettings`, `Product` (с вычисляемым `in_stock`), `Order`
  (с `status_label` и `payment_method: "cash_on_delivery"`), `AdminOrder = Order + user`
  соответствуют §7.
* Формат ошибок §3 единый на всех проверенных путях: 401, 403, 404, 409 (`conflict`,
  `insufficient_stock` c `details.items[]`, `product_unavailable`, `invalid_status_transition`),
  413, 415, 422 (`details.fields[]`), 429 с заголовком `Retry-After`, 500. Единственное
  отклонение — 405, см. находку №16.
* Все `Decimal` сериализуются строками: `"price_per_kg":"890.00"`, `"stock_kg":"12.500"` —
  подтверждено ответом API, а не только чтением кода.

### 3.2 Бизнес-логика заказов

* Корзина фронта не является источником истины: `create_order` перечитывает товары из БД,
  цена берётся из `product.price_per_kg`, а не из тела запроса
  (`order_service.py:173-191`); есть тест `test_price_is_taken_from_database_not_from_request`.
* `line_total = round_money(round_weight(w) * price)`, `subtotal = Σ line_total`,
  `delivery_price` = `DELIVERY_PRICE` для доставки и `0.00` для самовывоза,
  `total = subtotal + delivery_price` — совпадает с §6 контракта.
* Снимок позиции (`product_name`, `weight_kg`, `price_per_kg`, `line_total`) сохраняется
  в `order_items`; изменение каталога не переписывает старые заказы (`FK ... ON DELETE SET NULL`,
  тест `test_order_snapshot_survives_catalog_change`).
* Доставка требует адреса, самовывоз — нет (`OrderCreate._check_consistency`).
* Вес: минимум `0.100`, кратность `0.100`, квантование до 3 знаков (`_order_weight`).
* Дубли `product_id` в корзине отклоняются с внятным русским сообщением, а не молча
  схлопываются, — важно, потому что дальше в `create_order` используется словарь по `product_id`.
* `order_number` формата `ORD-YYYYMMDD-NNNNN` строится из выданного БД `id` — без отдельного
  счётчика и без гонок за номер.
* Только `Decimal`, ни одного `float` в денежных путях; `to_decimal` конвертирует `float`
  через `str`, `ROUND_HALF_UP` вынесен в `app/core/money.py`.

### 3.3 Конкурентность и остатки

* `ProductRepository.lock_by_ids` действительно генерирует для PostgreSQL
  `... WHERE products.id IN (...) ORDER BY products.id ASC FOR UPDATE` — проверено компиляцией
  запроса под диалект `postgresql` (вывод в §5). Сортировка по `id` даёт единый порядок
  блокировки и защищает от дедлоков.
* `OrderRepository.lock_order` даёт `... WHERE orders.id = %(id_1)s FOR UPDATE OF orders`.
  Важно, что `Order.items`/`Order.user` загружаются через `selectin`, а не `joinedload`:
  иначе PostgreSQL отверг бы `FOR UPDATE` на nullable-стороне внешнего соединения.
  На SQLite такая ошибка никогда бы не проявилась — здесь её удалось избежать.
* `supports_row_locking` корректно определяет диалект в рантайме: `postgresql+asyncpg` → `True`,
  `sqlite+aiosqlite` → `False` (проверено запуском, вывод в §5). То есть в бою блокировка
  действительно включается, а не «выключается тихо».
* Транзакция создания заказа целостная: блокировка → проверка `is_active` → проверка остатка →
  расчёт → списание → вставка → `flush` → `commit`, с `rollback` на любом исключении.
* Идемпотентность отмены построена на **двух** независимых признаках
  (`status == cancelled` **или** `stock_restored_at is not None`), возврат остатка — ровно один
  раз. Тест `test_repeated_cancel_does_not_restore_stock_twice` отменяет заказ четыре раза
  и проверяет остаток в БД, а не только код ответа.
* Повторная установка того же статуса — no-op 200 **без уведомления** (проверяется тестом
  через счётчик уведомлений).
* Переходы статусов соответствуют §6.7; отмена из `completed` даёт 409
  `invalid_status_transition` (проверено вживую).
* Ошибка отправки уведомления не откатывает уже закоммиченный заказ (два рубежа перехвата:
  `_notify_new_order` и сам `notification_service`).

### 3.4 Авторизация и разграничение доступа

* Проверка подписи реализована ровно по алгоритму Telegram: `secret = HMAC(b"WebAppData",
  bot_token)`, сравнение через `hmac.compare_digest`, TTL по `auth_date`, отбой данных
  «из будущего» (> 5 минут). Пустой `BOT_TOKEN` → 401, а не «пропустить всех».
* `telegram_id` берётся **только** из проверенного initData; `user_id` из query/тела
  игнорируется, а в схемах стоит `extra="forbid"`, поэтому лишние поля вообще отклоняются.
* Тесты авторизации (`tests/test_auth.py`, 26 сценариев) не подменяют зависимость, а собирают
  настоящий подписанный initData тем же HMAC — ослабить боевую проверку тестами нельзя.
  Покрыты: чужая подпись, подпись другим ботом, подмена `user.id`, подмена `auth_date`,
  добавленное поле, отсутствующий `hash`, просроченный и «будущий» `auth_date`, битый JSON,
  `id` строкой, отсутствующий `user`, пустой токен, initData > 8 КБ.
* Права администратора проверяются на бэкенде на **каждом** админ-роуте через `AdminUser`;
  `is_admin` синхронизируется из `ADMIN_TELEGRAM_IDS` при каждом входе, поэтому удаление ID
  из списка снимает права. Флаг из БД не может «пережить» удаление из настроек.
* Чужой заказ — 403 `forbidden`, несуществующий — 404 `not_found` (именно так, как требует §7).
* Dev-режим закрыт двумя условиями (`DEV_AUTH_ENABLED=true` **и** `ENVIRONMENT != production`),
  выключен по умолчанию, покрыт шестью тестами, включая псевдонимы `production`/`prod`.
  Единственная шероховатость — отсутствие `.strip()`, находка №18.

### 3.5 Безопасность

* **Загрузка файлов.** Тип определяется по сигнатуре байтов (JPEG `FF D8 FF`, PNG,
  RIFF+WEBP), а не по расширению и не по `Content-Type`; подделка отсекается (`415`,
  тест есть). Имя файла всегда `secrets.token_hex(16)` + нормализованное расширение из
  белого списка — пользовательское имя на диск не попадает. Размер проверяется в цикле
  чтения (`413` подтверждён экспериментально). `LocalStorage._to_path` отбрасывает `/`, `\`,
  `..`, NUL и чужой префикс, плюс делает `resolve()` и сверяет родительский каталог.
  SVG не входит в белый список — хранимого XSS через загрузку нет.
* **SQL-инъекции.** Все запросы — через SQLAlchemy Core/ORM с параметрами. Поиск в админке
  проверен строками `' OR 1=1 --`, `%`, `_`, `\` — инъекции нет (`%`/`_` работают как
  подстановочные символы LIKE, это косметика, а не уязвимость).
* **Экранирование в Telegram.** Всё пользовательское (`customer_name`, `phone`, `address`,
  `comment`, `product_name`, `username`, `order_number`) проходит через `html.escape`
  в `app/bot/messages.py`. При `parse_mode=HTML` это закрывает и порчу сообщения, и
  подмешивание чужой разметки в карточку администратора. Сделано аккуратно и последовательно.
* **Логи.** `structlog`-процессор `_redact` вычищает ключи `bot_token`, `token`, `hash`,
  `init_data`, `webhook_secret` и т.п., плюс регуляркой вырезает строки, похожие на токен бота,
  из любых строковых значений. Исключения логируются без содержимого запроса.
* **Раскрытие внутренних ошибок.** Обработчик `Exception` возвращает только
  `{"error":{"code":"internal_error","message":"Внутренняя ошибка сервера","details":{}}}`;
  трейсбек уходит в лог, а не клиенту. Проверено на реальных 500 из находок №5 и №6.
* **CORS.** Явный список источников из `ALLOWED_ORIGINS`, методы и заголовки перечислены,
  `Retry-After` в `expose_headers`. Порядок middleware выбран верно: CORS снаружи лимитера,
  поэтому даже 429 приходит с CORS-заголовками (есть тест).
* **Размер тела.** nginx ограничивает 10 МБ (`client_max_body_size`), что покрывает
  `MAX_UPLOAD_SIZE_MB=5` с запасом; предупреждение — только про прямой доступ к :8000
  (находка №3). Позиций в заказе не больше 50, `MAX_PAGE_LIMIT=100`, длина initData ≤ 8192,
  комментарий ≤ 2000, описание ≤ 4000.
* **Рост памяти лимитера** ограничен: `MAX_TRACKED_KEYS = 20_000` с аварийным вытеснением
  и периодической чисткой.

### 3.6 Тесты

Все обязательные сценарии из ТЗ присутствуют и проверяют состояние, а не только код ответа:

| Сценарий из ТЗ | Тест |
|---|---|
| Валидный / невалидный initData | `test_auth.py` — 26 тестов, включая `test_hash_matches_reference_algorithm` |
| Запрет админ-методов обычному пользователю | `test_permissions.py:86`, `test_admin_products.py:330,341` |
| Создание товара | `test_admin_products.py:28`, `test_permissions.py:128` |
| Отрицательная цена / остаток | `test_admin_products.py:82,93,126` |
| Создание заказа и расчёт суммы | `test_orders.py:12,35,67,87,104` |
| Запрет заказа сверх остатка | `test_stock.py:95,117,128,144` |
| Уменьшение остатка | `test_stock.py:47,60,77` |
| Возврат остатка после отмены | `test_stock.py:187,241,260` |
| Защита от повторного возврата | `test_stock.py:209` (четыре отмены подряд, сверка остатка в БД) |
| Запрет чтения чужого заказа | `test_orders.py:270`, `test_permissions.py:170` |

Отдельно отмечу удачные решения: тесты не отключают авторизацию и лимитер, `NotificationRecorder`
подменяет только отправку, сохраняя боевой путь вызова (значит, рассинхрон сигнатур
`order_service` ↔ `notification_service` тесты поймают), а проверки идут по данным в БД
(`_stock`, `_status`, `_restored_at`), а не по телу ответа. Пробелы — в находке №11.

### 3.7 Docker и запуск

* Порядок запуска корректен: `backend` ждёт `db: service_healthy`, `bot` и `frontend` ждут
  `backend: service_healthy`. Healthcheck БД — `pg_isready`, backend — `GET /health` штатным
  Python (в образе нет curl — учтено), frontend — `wget` на `/healthz`.
* Миграции применяются один раз: `RUN_MIGRATIONS=true` у backend, `false` у бота.
* `entrypoint.sh` ждёт БД с таймаутом, применяет `alembic upgrade head`, запускает команду
  через `exec` (корректная доставка SIGTERM). **Файл сохранён с LF** — проверено побайтно:
  0 вхождений CRLF.
* Образ backend — multi-stage, в runtime уезжает только venv; работает от непривилегированного
  пользователя `appuser` (uid 1001).
* Секретов в образе нет: `backend/.dockerignore` исключает `.env`, `.env.*`, `.venv`, `tests/`,
  кэши и `uploads/`; `.gitignore` закрывает `.env` и содержимое `uploads/`. Токены приходят
  только через `env_file`.
* Тома `pgdata` и `uploads` объявлены, `uploads` общий для backend и бота, каталог создаётся
  в образе до монтирования — владелец наследуется корректно.
* `stop_grace_period: 30s` у бота — разумно для long polling.

### 3.8 Схема БД и миграции

* `alembic/versions/0001_initial.py` побайтно соответствует моделям: типы `Numeric(10,2)` для
  денег и `Numeric(10,3)` для веса, `users.telegram_id BigInteger UNIQUE`,
  `orders.order_number UNIQUE`, FK `orders.user_id → users.id ON DELETE RESTRICT`,
  `order_items.order_id → orders.id ON DELETE CASCADE`,
  `order_items.product_id → products.id ON DELETE SET NULL`, CHECK-ограничения на
  неотрицательность и `weight_kg > 0`, индексы `ix_orders_user_created`, `ix_orders_status`
  и др. `downgrade()` симметричен.
* Оба enum объявлены как `sa.Enum(..., native_enum=False, length=20)` — VARCHAR + CHECK,
  то есть одна схема работает и в PostgreSQL, и в SQLite.
* `alembic/env.py` берёт URL из настроек и экранирует `%` в пароле — частая и неочевидная
  ловушка configparser, здесь она обработана.
* Код совместим с Python 3.10: `StrEnum` и `typing.Self` не используются, везде
  `from __future__ import annotations`.

### 3.9 README

* Инструкции рабочие и полные: BotFather (`/newbot`, `/setmenubutton`, `/newapp`),
  настройка Mini App URL, HTTPS-туннель (cloudflared и ngrok, с оговоркой про
  страницу-предупреждение ngrok), Docker и локальный запуск, отдельные варианты команд для
  bash и PowerShell.
* Таблица переменных окружения сверена с `backend/app/core/config.py` и `.env.example` —
  расхождений нет. Все 20 переменных из §9 контракта присутствуют во всех трёх местах.
* Раздел «Диагностика проблем» покрывает реальные грабли, включая `\r\n` в `entrypoint.sh`
  и `502` после пересоздания контейнера.
* Разделы «Ограничения MVP» и «Рекомендации для production» написаны честно, без приукрашивания.
* Замечания — находки №15 (`mypy` падает) и №7 (webhook описан как рабочий режим).

---

## 4. Ограничения MVP (осознанные компромиссы, не баги)

Это **не** находки: решения приняты сознательно и задокументированы в `CLAUDE.md`,
`docs/CONTRACTS.md` или README.

1. **Rate limiting в памяти процесса.** Не переживает рестарт, не общий для воркеров и реплик.
   Задокументировано в `ratelimit.py:15-17` и в README. Для продакшена нужен Redis.
   (Это ограничение отдельно от находок №2 и №3 — те про то, что лимитер обходится
   даже в рамках одного процесса.)
2. **Очередь уведомлений в памяти.** Прямо разрешено §5 контракта (`deque(maxlen=500)`),
   полноценный transactional outbox отнесён на «после MVP». Замечание №9 — про то, что
   заявленный механизм повторов фактически не подключён, а не про выбор хранилища.
3. **Локальное файловое хранилище.** Интерфейс `Storage` готов к `S3Storage`, но пока один том.
4. **Long polling, один экземпляр бота.** Горизонтальное масштабирование требует webhook.
5. **Нет онлайн-оплаты.** `payment_method` всегда `cash_on_delivery`.
6. **Расписание доставки не валидируется** — дата и интервал принимаются как текст, занятость
   слотов не проверяется.
7. **Удаление товара = архивирование.** Физического удаления нет, чтобы не рушить историю.
8. **Все администраторы равны** — ролей внутри админов нет.
9. **initData воспроизводима в пределах TTL** (по умолчанию 24 часа). Это свойство самой схемы
   Telegram; единственный рычаг — уменьшить `INIT_DATA_TTL_SECONDS`. Для магазина с оплатой
   при получении риск приемлем; для чувствительных операций стоит сократить TTL до часов.
10. **`created_at` без смещения в тестах.** На SQLite `DateTime(timezone=True)` теряет tz, и
    JSON выглядит как `"2026-09-07T20:37:34"`. В бою (PostgreSQL `timestamptz`) значение
    приходит tz-aware и сериализуется с `+00:00`, как требует §2. Отдельного бага здесь нет,
    но фронтенду стоит разбирать даты устойчиво к обоим вариантам.

---

## 5. Результаты запущенных команд

Все команды выполнялись на Windows 10, `backend\.venv\Scripts\python.exe` (Python 3.10).

### 5.1 Тесты

```
cd backend && .venv/Scripts/python.exe -m pytest tests/ -q

........................................................................ [ 37%]
........................................................................ [ 74%]
.................................................                        [100%]
193 passed in 7.19s
```

### 5.2 Линтер

```
cd backend && .venv/Scripts/python.exe -m ruff check .
All checks passed!

ruff 0.16.6
```

### 5.3 Проверка типов

```
cd backend && .venv/Scripts/python.exe -m mypy app

app\core\logging.py:56: error: List item 3 has incompatible type ...  [list-item]
app\api\v1\catalog.py:34: error: Argument "items" to "Page" has incompatible type
    "list[Product]"; expected "list[ProductOut]"  [arg-type]
app\api\v1\orders.py:55: error: ... "list[Order]"; expected "list[OrderOut]"  [arg-type]
app\api\v1\admin_orders.py:40: error: ... expected "list[AdminOrderOut]"  [arg-type]
app\api\v1\admin_products.py:43: error: ... expected "list[ProductOut]"  [arg-type]
Found 5 errors in 5 files (checked 51 source files)
```

→ находка №15.

### 5.4 Определение диалекта и SQL блокировок

Скрипт вызывал `supports_row_locking()` на реальных сессиях и компилировал запросы
репозиториев под диалект PostgreSQL:

```
'postgresql+asyncpg://meat:meat@localhost:5432/meat'   supports_row_locking=True
'sqlite+aiosqlite:///:memory:'                         supports_row_locking=False

--- products lock SQL ---
SELECT products.id, ... FROM products
WHERE products.id IN (__[POSTCOMPILE_id_1]) ORDER BY products.id ASC FOR UPDATE

--- order lock SQL ---
SELECT orders.id, ... FROM orders WHERE orders.id = %(id_1)s FOR UPDATE OF orders
```

→ раздел 3.3: блокировки в бою действительно включаются, порядок по `id` соблюдён,
на nullable-сторону внешнего соединения `FOR UPDATE` не попадает.

### 5.5 Функциональные пробы через HTTP (httpx + ASGI, фикстуры из `tests/conftest.py`)

Пробы запускались как отдельный файл вне репозитория (`-p tests.conftest`), файлы проекта
не изменялись.

```
PROBE weight='NaN'        -> 422 validation_error  "Input should be a finite number"
PROBE weight='Infinity'   -> 422 validation_error
PROBE weight='-Infinity'  -> 422 validation_error
PROBE weight='snan'       -> 422 validation_error
PROBE weight='1e1000'     -> 500  [error] unhandled_error error=InvalidOperation
                                  method=POST path=/api/v1/orders
PROBE price='NaN'         -> 422 validation_error
PROBE price='Infinity'    -> 422 validation_error
PROBE price='1e1000'      -> 500  [error] unhandled_error error=InvalidOperation
                                  method=POST path=/api/v1/admin/products
```
→ находка №6.

```
PROBE patch name=null         -> 500  IntegrityError: NOT NULL constraint failed: products.name
PROBE patch price_per_kg=null -> 500  IntegrityError: NOT NULL ... products.price_per_kg
PROBE patch stock_kg=null     -> 500  IntegrityError: NOT NULL ... products.stock_kg
PROBE patch is_active=null    -> 500  IntegrityError: NOT NULL ... products.is_active
```
→ находка №5.

```
RATE_LIMIT_ORDERS = 2/60

PROBE ratelimit, одинаковые заголовки       -> [201, 201, 429, 429, 429]
PROBE ratelimit, подставной X-Telegram-Id   -> [201, 201, 201, 201, 201]
```
→ находка №2: лимит обходится добавлением одного заголовка, initData при этом валидный.

```
PROBE big upload (2 МБ при лимите 1 МБ) -> 413 {"error":{"code":"file_too_large",...}}
PROBE webp по сигнатуре RIFF....WEBP    -> 201 {"photo_url":"/uploads/072dff...b.webp"}
PROBE upload без авторизации            -> 401 unauthorized
PROBE 60 позиций в заказе               -> 422 "List should have at most 50 items"
PROBE product_id=0 / -1                 -> 422 validation_error
PROBE product_id=10^18                  -> 404 not_found  details.product_ids=[10^18]
PROBE отмена выполненного заказа        -> 409 invalid_status_transition
PROBE search="' OR 1=1 --"              -> 200 total=0   (инъекции нет)
PROBE search="%" / "_"                  -> 200 total=1   (подстановочные символы LIKE)
PROBE неизвестный путь                  -> 404 {"error":{"code":"not_found",...}}
PROBE неверный метод (DELETE /orders)   -> 405 {"error":{"code":"method_not_allowed",...}}
PROBE GET /catalog                      -> 200 {"items":[{... "price_per_kg":"890.00",
                                              "stock_kg":"12.500", "in_stock":true}],
                                              "total":1,"limit":20,"offset":0}
PROBE photo_url='javascript:alert(1)'   -> 201 (значение сохранено как есть)
PROBE photo_url='/uploads/../../etc/passwd' -> 201 (значение сохранено как есть)
```
→ подтверждают раздел 3.5 и находки №14, №16.

### 5.6 Замер числа SQL-запросов (перехват `before_cursor_execute`)

Пользователь с 15 заказами по одной позиции:

```
PROBE /api/v1/me       -> 200; SQL=3
     SELECT users.id, users.telegram_id, ...
     SELECT orders.user_id AS orders_user_id, ...      <- вся история заказов
     SELECT order_items.order_id AS order_items_order_id, ...  <- все позиции всех заказов
PROBE /api/v1/catalog  -> 200; SQL=5   (те же три + count + products)
PROBE /api/v1/settings -> 200; SQL=3   (эндпоинт вообще не работает с заказами)
PROBE /api/v1/orders/<id> -> 200; SQL=6
```
→ находка №4.

### 5.7 Прочие проверки

```
file backend/entrypoint.sh
  backend/entrypoint.sh: POSIX shell script, Unicode text, UTF-8 text executable
CRLF count: 0   LF count: 78
```

```
grep -rn "retry_failed" backend/app backend/tests
  app/services/notification_service.py:13   (docstring)
  app/services/notification_service.py:40   (комментарий)
  app/services/notification_service.py:277  (определение)
  app/services/notification_service.py:324  (__all__)
```
→ находка №9: вызовов нет.

```
grep -rn "webhook" backend/app --include=*.py | grep -v bot/runner.py
  — только app/bot_main.py, app/core/config.py, app/core/logging.py
```
→ находка №7: HTTP-эндпоинта приёма апдейтов нет.

```
grep -rn "413|file_too_large|webp|_to_path|traversal|gather|concurr" backend/tests
  — совпадений нет
```
→ находка №11: пробелы в покрытии.

---

## 6. Рекомендуемый порядок исправления

1. №1 — двойной префикс API (без него приложение не работает вовсе).
2. №2 и №3 — восстановить работоспособность rate limiting (ключевание по проверенной личности
   и по неподделываемому IP).
3. №4 — убрать жадную загрузку `User.orders`.
4. №5, №6 — два пути, отдающих 500 вместо 422.
5. №10 — убрать публикацию порта БД и дефолтный пароль.
6. №7, №8, №9 — привести webhook и уведомления в соответствие с контрактом и README.
7. №11 — закрыть пробелы в тестах (особенно 413, `_to_path` и удаление старого фото).
8. Остальные `low` — по мере готовности.

Правки в `docs/CONTRACTS.md` (по находкам №9 и №16) вносит только главный агент.

---

# 7. Статус исправлений (главный агент, после ревью)

Ниже — что реально исправлено и чем это подтверждено. Проверки запускались заново
после каждого изменения.

## 7.1 Исправлено

| Приоритет | Проблема | Что сделано | Подтверждение |
|---|---|---|---|
| critical | Двойной префикс `/api/v1/api/v1/...` в Docker-сборке | `VITE_API_BASE_URL` очищен в `.env.example`, `frontend/Dockerfile`, `docker-compose.yml`; в `client.ts` добавлена `normalizeBaseUrl()`, которая срезает ошибочно указанный `/api/v1` | `frontend/src/api/client.test.ts` — 5 тестов, в т. ч. «префикс встречается ровно один раз» |
| high | Обход rate limiting подделкой `X-Telegram-Id` | Ключ лимитера считается только по **проверенной** подписи initData; заголовок `X-Dev-Telegram-Id` принимается лишь при `dev_auth_allowed` | `tests/test_ratelimit.py::test_forged_telegram_id_header_does_not_reset_limit`, `::test_unsigned_init_data_falls_back_to_ip` |
| high | `--forwarded-allow-ips "*"` + порт 8000 наружу | `forwarded-allow-ips` сужен до внутренних сетей (`TRUSTED_PROXY_IPS`); порт backend публикуется на `127.0.0.1`; nginx **перезаписывает** `X-Forwarded-For` (`$remote_addr` вместо `$proxy_add_x_forwarded_for`) | `docker-compose.yml`, `frontend/nginx.conf` (2 location-блока) |
| high | `User.orders` с `lazy="selectin"` — N+1 на каждом запросе | Связь переведена в `lazy="raise"`: заказы читаются только через `OrderRepository`, случайное обращение падает громко | Замер перехватом курсора: `GET /settings` 3 → **1** SQL, `GET /catalog` 5 → **3** SQL |
| medium | `PATCH /admin/products/{id}` с явным `null` → 500 | В `ProductUpdate` добавлен `model_validator`, отклоняющий `null` для NOT NULL-полей; `description` и `photo_url` по-прежнему обнуляются | `test_explicit_null_on_required_field_returns_422` (4 поля), `test_explicit_null_clears_optional_field` (2 поля) |
| medium | `"1e1000"`, `NaN`, `Infinity` → 500 | `to_decimal` отвергает неконечные значения, `round_money`/`round_weight` переводят `InvalidOperation` в `ValueError`; добавлены границы `Numeric(10,2)`/`(10,3)` | `test_non_finite_price_returns_422` (5 значений), `test_price_beyond_column_range_returns_422`, `test_stock_beyond_column_range_returns_422` |
| medium | `BOT_MODE=webhook` документирован, но принимающего эндпоинта нет | Реализован `POST {WEBHOOK_PATH}` в `app/main.py`: сверка `X-Telegram-Bot-Api-Secret-Token` через `compare_digest`, 404 в режиме polling, обязательный секрет в production | `tests/test_webhook.py` — 6 тестов |
| medium | `retry_failed()` не вызывался нигде | Фоновая задача в lifespan (`_notification_retry_loop`), интервал 60 с, корректная отмена при остановке | `app/main.py`; полный прогон тестов зелёный |
| medium | Пароль БД по умолчанию при опубликованном порте 5433 | Порт PostgreSQL публикуется на `127.0.0.1` (`DB_BIND`), в `.env.example` описан SSH-туннель для удалённого доступа | `docker-compose.yml`, `.env.example` |
| medium | Незакрытая aiohttp-сессия бота в API-процессе | В lifespan добавлен вызов `shutdown_bot()` | `app/main.py` |
| low | `mypy app` — 5 ошибок при документированной команде | Явное преобразование ORM → схема в четырёх `Page[...]`, уточнён тип процессора structlog | `mypy app` → **Success: no issues found in 51 source files** |
| — | Интеграционный дефект: `order_service` вызывал уведомления с неверной сигнатурой — они молча не отправлялись | Заменён перебор имён на явные вызовы `notify_new_order(order.id)` / `notify_order_status_changed(order.id, status)` | `NotificationRecorder` в `tests/conftest.py` проверяет связку; `test_order_creation_notifies_telegram`, `test_status_change_notifies_customer` |
| — | Расхождение документации и кода: в контракте была описана несуществующая таблица `notification_outbox` | §5 контракта приведён к реальности: очередь в памяти, ограничение MVP зафиксировано явно | `docs/CONTRACTS.md` |

## 7.2 Закрытые пробелы в тестах

Все перечисленные ревью пробелы закрыты, кроме одного (см. 7.3):

* **413 при превышении размера** — `test_oversized_upload_returns_413`, дополнительно проверяет,
  что огромный файл не попал на диск;
* **удаление старого файла при замене фото (§8 контракта)** — `test_replacing_photo_deletes_the_old_file`
  сверяет реальное состояние диска, а `test_shared_photo_is_not_deleted_while_still_used`
  проверяет обратный случай: файл, на который ссылается другой товар, не удаляется;
* **path traversal в имени файла** — `test_filename_cannot_escape_upload_dir`, 4 варианта имени,
  проверяется, что итоговый путь лежит внутри `UPLOAD_DIR`;
* **файл действительно оказывается на диске** — `test_uploaded_file_really_lands_on_disk`.

## 7.3 Осознанно не исправлено

* **Тест конкурентного создания заказов.** На SQLite он не доказывает ничего: `FOR UPDATE`
  там отсутствует, а запись сериализуется самой БД. Осмысленная проверка требует
  PostgreSQL в CI. Корректность блокировок подтверждена иначе — компиляцией SQL под
  asyncpg (`... ORDER BY products.id ASC FOR UPDATE`) и проверкой `supports_row_locking`.
  Зафиксировано как ограничение MVP.
* **Уведомления отправляются внутри HTTP-запроса.** Заказ при этом не откатывается
  (ошибки гасятся и логируются), а недоставленное уходит в очередь повтора. Полноценный
  transactional outbox — задача после MVP, интерфейс уведомлений менять не потребуется.

## 7.4 Итоговые проверки после исправлений

```
backend:  pytest -q      222 passed
          ruff check .   All checks passed!
          mypy app       Success: no issues found in 51 source files
          alembic        upgrade head -> downgrade base -> upgrade head (обратима)
          scripts.seed   7 товаров, повторный запуск идемпотентен
frontend: npm run build  ✓ 122 modules
          npm run test   64 passed
          npm run lint   0 errors, 0 warnings
```
