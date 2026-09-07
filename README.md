# 🥩 Мясо для собак — Telegram Mini App

Магазин развесного мяса для собак, работающий целиком внутри Telegram.
Покупатель открывает Mini App из чата с ботом, набирает товары по весу (шаг 100 г),
оформляет заказ с доставкой или самовывозом и получает уведомления об изменении статуса.
Администратор ведёт каталог, остатки, фотографии и заказы в том же приложении —
отдельная веб-панель не нужна.

Оплата — **при получении**. Онлайн-платежей в MVP нет.

---

## Содержание

1. [Возможности](#возможности)
2. [Архитектура](#архитектура)
3. [Требования](#требования)
4. [Быстрый старт через Docker](#быстрый-старт-через-docker)
5. [Локальный запуск без Docker](#локальный-запуск-без-docker)
6. [Создание бота в BotFather](#создание-бота-в-botfather)
7. [Настройка Mini App URL](#настройка-mini-app-url)
8. [HTTPS-туннель для локальной разработки](#https-туннель-для-локальной-разработки)
9. [Переменные окружения](#переменные-окружения)
10. [Миграции базы данных](#миграции-базы-данных)
11. [Как назначить администратора](#как-назначить-администратора)
12. [Тестовые товары](#тестовые-товары)
13. [Тесты](#тесты)
14. [Линтеры и форматирование](#линтеры-и-форматирование)
15. [Сборка фронтенда](#сборка-фронтенда)
16. [Команды](#команды)
17. [Структура каталогов](#структура-каталогов)
18. [Диагностика проблем](#диагностика-проблем)
19. [Ограничения MVP](#ограничения-mvp)
20. [Рекомендации для production](#рекомендации-для-production)

---

## Возможности

### Покупатель

* Каталог товаров с фотографиями, ценой за килограмм и остатком на складе.
* Карточка товара с описанием и выбором веса: минимум **0.100 кг**, шаг **0.100 кг**,
  не больше доступного остатка.
* Корзина с пересчётом суммы, значок с количеством позиций в нижней навигации.
  Корзина хранится в `localStorage` и переживает закрытие Mini App.
* Оформление заказа: имя, телефон, доставка или самовывоз, адрес, дата и интервал времени,
  комментарий. Стоимость доставки добавляется автоматически, при самовывозе показывается
  адрес пункта выдачи.
* История своих заказов со статусами и составом. Чужой заказ открыть нельзя — backend
  отвечает `403`.
* Уведомления в чат от бота при смене статуса заказа.
* Тема оформления подхватывается из Telegram (`--tg-theme-*`), приложение выглядит
  одинаково уместно в светлой и тёмной теме.

### Администратор

* Всё, что доступно покупателю, плюс раздел «Админ» в нижней навигации.
* Товары: создание, редактирование, изменение цены и остатка, загрузка фотографии
  (JPEG / PNG / WebP), архивирование и восстановление. Архивный товар исчезает из каталога,
  но остаётся в истории заказов.
* Заказы: список с фильтром по статусу, карточка заказа с составом и контактами покупателя,
  смена статуса по цепочке `новый → подтверждён → готовится → доставляется → выполнен`
  и отмена из любого статуса, кроме выполненного и уже отменённого.
* Отмена заказа возвращает списанные остатки на склад ровно один раз.
* Уведомление в Telegram о каждом новом заказе.

---

## Архитектура

```
                    Telegram
        ┌───────────────┴───────────────┐
        │                               │
  Mini App (WebView)              чат с ботом
        │                               │
        ▼                               ▼
┌──────────────────┐            ┌────────────────┐
│  frontend        │            │  bot           │
│  React 18 + TS   │            │  aiogram 3     │
│  Vite, Zustand   │            │  long polling  │
│  nginx           │            │                │
└────────┬─────────┘            └───────┬────────┘
         │ /api/v1, /uploads             │
         └──────────────┬────────────────┘
                        ▼
        ┌───────────────────────────────┐
        │  backend — FastAPI            │
        │                               │
        │  api/v1/    HTTP-роуты        │
        │  api/deps   авторизация       │
        │  services/  бизнес-логика     │
        │  repositories/ доступ к данным│
        │  models/    ORM               │
        │  schemas/   Pydantic v2       │
        │  storage/   файлы             │
        │  core/      config, db, errors│
        └───────┬───────────────┬───────┘
                │               │
                ▼               ▼
        ┌───────────────┐  ┌──────────────┐
        │ PostgreSQL 16 │  │ uploads/     │
        │ (том pgdata)  │  │ (том uploads)│
        └───────────────┘  └──────────────┘
```

Как это работает:

1. Telegram открывает Mini App и передаёт в него подписанную строку `initData`.
2. Фронтенд отправляет её в каждом запросе заголовком `X-Telegram-Init-Data`.
3. Backend проверяет подпись HMAC-SHA256 по токену бота и возраст `auth_date`.
   Идентификатор пользователя берётся **только** из проверенных данных.
4. Заказ создаётся одной транзакцией: товары блокируются `SELECT ... FOR UPDATE`,
   цены и остатки читаются заново из базы, корзина клиента источником истины не является.
5. Бот работает отдельным процессом и шлёт уведомления покупателю и администраторам.

Подробные контракты (модели, эндпоинты, коды ошибок, правила расчёта) — в
[`docs/CONTRACTS.md`](docs/CONTRACTS.md).

---

## Требования

| Инструмент       | Версия              | Зачем                                        |
|------------------|---------------------|----------------------------------------------|
| Docker + Compose | Docker 24+, Compose v2 | самый простой способ поднять весь стек     |
| Python           | 3.11+ (в образе 3.12, минимум 3.10) | backend и бот без Docker     |
| Node.js          | 20+ (в образе 22)   | фронтенд без Docker                          |
| PostgreSQL       | 16                  | нужен только при запуске без Docker          |
| Git              | любой               | клонирование репозитория                     |

Для запуска через Docker из этого списка нужны только Docker и Git.
Аккаунт Telegram и бот, созданный в @BotFather, обязательны в любом случае.

---

## Быстрый старт через Docker

```bash
git clone <адрес-репозитория> meat
cd meat
```

**1. Создайте `.env` из шаблона**

```bash
# Linux / macOS
cp .env.example .env
```

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

**2. Заполните обязательные переменные в `.env`**

```dotenv
BOT_TOKEN=1234567890:AAH...            # токен от @BotFather
BOT_USERNAME=my_meat_bot               # имя бота без @
ADMIN_TELEGRAM_IDS=123456789           # ваш Telegram ID, узнать у @userinfobot
WEBAPP_URL=https://ваш-туннель.example # публичный HTTPS-адрес фронтенда
ALLOWED_ORIGINS=https://ваш-туннель.example
```

Без HTTPS-адреса Mini App не откроется внутри Telegram — см.
[HTTPS-туннель](#https-туннель-для-локальной-разработки).
Проверить API и админку в браузере можно и без него.

**3. Поднимите стек**

```bash
docker compose up --build
```

Первая сборка занимает несколько минут. Поднимется четыре контейнера:

| Сервис     | Образ / сборка         | Порт на хосте | Что делает                                              |
|------------|------------------------|---------------|---------------------------------------------------------|
| `db`       | `postgres:16-alpine`   | **5433** → 5432 | PostgreSQL, данные в томе `pgdata`, healthcheck `pg_isready` |
| `backend`  | сборка `./backend`     | **8000** → 8000 | FastAPI: ждёт БД, применяет миграции, запускает uvicorn |
| `bot`      | тот же образ           | —             | `python -m app.bot_main`, long polling                  |
| `frontend` | сборка `./frontend`    | **5173** → 80 | nginx: SPA + прокси `/api` и `/uploads` на backend      |

> Порт базы — **5433**, а не 5432, чтобы не конфликтовать с PostgreSQL,
> установленным на машине локально. Изменить можно переменной `DB_PORT` в `.env`.
> Порты backend и frontend меняются переменными `BACKEND_PORT` и `FRONTEND_PORT`.

**4. Откройте**

* Приложение — <http://localhost:5173>
* Документация API (Swagger) — <http://localhost:8000/docs>
* Проверка живости — <http://localhost:8000/health>

**Порядок запуска** соблюдается автоматически: `backend` ждёт, пока `db` станет
`healthy`, `bot` и `frontend` ждут, пока `healthy` станет `backend`.
Миграции применяет только `backend` (у `bot` выставлено `RUN_MIGRATIONS=false`).

### Полезные команды Docker

```bash
docker compose up --build -d          # поднять в фоне
docker compose ps                     # состояние и healthcheck
docker compose logs -f backend        # логи одного сервиса
docker compose logs -f                # логи всех
docker compose restart backend        # перезапустить сервис
docker compose exec backend sh        # шелл внутри контейнера
docker compose exec db psql -U meat -d meat   # psql внутри контейнера
docker compose down                   # остановить, данные сохранить
docker compose down -v                # остановить и УДАЛИТЬ тома (база и фото пропадут)
```

---

## Локальный запуск без Docker

Нужны Python 3.11+, Node.js 20+ и работающий PostgreSQL 16.
Базу удобно поднять контейнером, а backend и фронтенд запускать локально:

```bash
docker compose up -d db          # PostgreSQL на localhost:5433
```

### 1. База данных

Если PostgreSQL установлен локально, создайте базу и пользователя:

```sql
CREATE USER meat WITH PASSWORD 'meat';
CREATE DATABASE meat OWNER meat;
```

И приведите `DATABASE_URL` в `.env` в соответствие с портом:

```dotenv
# база из docker compose
DATABASE_URL=postgresql+asyncpg://meat:meat@localhost:5433/meat
# свой локальный PostgreSQL
DATABASE_URL=postgresql+asyncpg://meat:meat@localhost:5432/meat
```

> Внутри Docker хост базы — `db`, при локальном запуске — `localhost`.
> Значение для контейнеров подставляет сам `docker-compose.yml`, править `.env`
> ради Docker не нужно.

### 2. Backend

**Linux / macOS**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Windows PowerShell**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> Если PowerShell отказывается выполнять `Activate.ps1`, разрешите скрипты для текущего
> пользователя: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
> Либо работайте без активации, вызывая `.\.venv\Scripts\python.exe -m ...`.

API поднимется на <http://localhost:8000>, Swagger — на `/docs`.

### 3. Бот

Отдельный терминал, то же виртуальное окружение:

```bash
# Linux / macOS
cd backend && source .venv/bin/activate && python -m app.bot_main
```

```powershell
# Windows PowerShell
cd backend; .\.venv\Scripts\Activate.ps1; python -m app.bot_main
```

Бот и backend можно запускать независимо: API работает без бота, бот — без запущенного API.

### 4. Фронтенд

```bash
cd frontend
npm install
npm run dev
```

Vite поднимет dev-сервер на <http://localhost:5173> с горячей перезагрузкой.

Чтобы открывать приложение в обычном браузере (вне Telegram, где нет `initData`),
включите dev-авторизацию в `.env`:

```dotenv
DEV_AUTH_ENABLED=true
DEV_TELEGRAM_ID=123456789     # ваш Telegram ID — так вы получите и права админа
ENVIRONMENT=development
```

Backend примет заголовок `X-Dev-Telegram-Id` вместо подписи Telegram.
**В production `DEV_AUTH_ENABLED` обязан быть `false`** — при `ENVIRONMENT=production`
режим блокируется в любом случае.

---

## Создание бота в BotFather

1. Откройте в Telegram [@BotFather](https://t.me/BotFather) и нажмите **Start**.
2. Отправьте `/newbot`.
3. Введите **отображаемое имя** бота, например `Мясо для собак`.
4. Введите **username** — латиницей, обязательно заканчивается на `bot`,
   например `dog_meat_shop_bot`. Если занят, BotFather попросит другой.
5. BotFather пришлёт токен вида `1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw`.
   Скопируйте его в `.env`:

   ```dotenv
   BOT_TOKEN=1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   BOT_USERNAME=dog_meat_shop_bot
   ```

   > Токен — это полный доступ к боту. Не коммитьте его в git и не публикуйте.
   > Если токен утёк — `/revoke` в BotFather выдаст новый.

6. Необязательно, но полезно — оформите бота:

   ```
   /setdescription    — текст на экране до нажатия Start
   /setabouttext      — короткое описание в профиле
   /setuserpic        — аватар
   /setcommands       — список команд, например:
                        start - Открыть магазин
                        orders - Мои заказы
                        help - Помощь
   ```

---

## Настройка Mini App URL

Mini App должен открываться по **HTTPS**. `http://localhost` Telegram не примет —
сначала поднимите [туннель](#https-туннель-для-локальной-разработки) или выложите
фронтенд на домен с сертификатом.

### Вариант A — кнопка меню (быстрее)

1. В BotFather: `/setmenubutton`.
2. Выберите своего бота.
3. Отправьте URL приложения, например `https://random-words-1234.trycloudflare.com`.
4. Отправьте подпись кнопки, например `Открыть магазин`.

Теперь в чате с ботом слева от поля ввода появится кнопка, открывающая Mini App.

### Вариант B — полноценное Mini App (ссылка `t.me/бот/имя`)

1. В BotFather: `/newapp`.
2. Выберите бота.
3. Введите заголовок и описание приложения.
4. Загрузите иконку 640×360.
5. Укажите **Web App URL** — тот же HTTPS-адрес.
6. Задайте короткое имя, например `shop`.

Приложение станет доступно по прямой ссылке `https://t.me/dog_meat_shop_bot/shop` —
её удобно давать покупателям.

Изменить URL позже: `/myapps` → приложение → **Edit Web App URL**,
или `/setmenubutton` для кнопки меню.

### После смены адреса не забудьте

```dotenv
WEBAPP_URL=https://новый-адрес
ALLOWED_ORIGINS=https://новый-адрес
PUBLIC_BASE_URL=https://новый-адрес-бэкенда
```

и перезапустите backend и бота:

```bash
docker compose up -d --force-recreate backend bot
```

---

## HTTPS-туннель для локальной разработки

Telegram открывает Mini App только по HTTPS с валидным сертификатом.
Туннель отдаёт наружу локальный порт **5173** (фронтенд).

### cloudflared (бесплатно, без регистрации)

Установка:

```bash
# macOS
brew install cloudflared
# Linux (deb)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cloudflared.deb && sudo dpkg -i cloudflared.deb
```

```powershell
# Windows
winget install --id Cloudflare.cloudflared
```

Запуск:

```bash
cloudflared tunnel --url http://localhost:5173
```

В консоли появится адрес вида `https://random-words-1234.trycloudflare.com`.

### ngrok (нужна бесплатная регистрация)

```bash
# macOS / Linux
brew install ngrok            # или скачайте с https://ngrok.com/download
ngrok config add-authtoken <ваш токен из личного кабинета>
ngrok http 5173
```

```powershell
# Windows
winget install --id Ngrok.Ngrok
ngrok config add-authtoken <ваш токен>
ngrok http 5173
```

ngrok покажет строку `Forwarding  https://abcd-12-34-56-78.ngrok-free.app -> http://localhost:5173`.

### Что подставить

Пусть туннель выдал `https://abcd.trycloudflare.com`.

**1. В `.env`:**

```dotenv
WEBAPP_URL=https://abcd.trycloudflare.com
ALLOWED_ORIGINS=https://abcd.trycloudflare.com,http://localhost:5173
```

`ALLOWED_ORIGINS` — список через запятую; localhost можно оставить, чтобы параллельно
работала отладка в браузере.

**2. В BotFather:** `/setmenubutton` (или `/myapps` → Edit Web App URL) → тот же адрес.

**3. Перезапустите backend**, чтобы применился CORS:

```bash
docker compose up -d --force-recreate backend bot   # Docker
# либо просто перезапустите uvicorn при локальном запуске
```

### Важные нюансы

* Бесплатные туннели выдают **новый адрес при каждом запуске**. После перезапуска
  туннеля адрес нужно поменять и в `.env`, и в BotFather. Постоянный адрес даёт
  именованный туннель Cloudflare или платный тариф ngrok.
* Туннель направляется на **frontend (5173)**, а не на backend: nginx сам проксирует
  `/api` и `/uploads` внутрь. При запуске через Vite dev-сервер настройте прокси
  в `vite.config.ts` либо поднимите второй туннель на 8000 и укажите его в `PUBLIC_BASE_URL`.
* ngrok на бесплатном тарифе показывает страницу-предупреждение при первом заходе;
  Telegram её не пропустит. Обойти можно заголовком `ngrok-skip-browser-warning`
  или используя cloudflared.
* Не забудьте, что при работе через туннель кто угодно со ссылкой может открыть ваш
  локальный стенд. Выключайте туннель, когда он не нужен.

---

## Переменные окружения

Все переменные читаются из `.env` в корне проекта (и дополнительно из `backend/.env`).
Определения и значения по умолчанию — в `backend/app/core/config.py`,
готовый шаблон с комментариями — в `.env.example`.

| Переменная              | Назначение                                                                 | Пример                                                    | Обязательна |
|-------------------------|----------------------------------------------------------------------------|-----------------------------------------------------------|-------------|
| `BOT_TOKEN`             | Токен бота от @BotFather. Им же проверяется подпись `initData`              | `1234567890:AAH...`                                       | **да**      |
| `BOT_USERNAME`          | Username бота без `@`, используется в ссылках                              | `dog_meat_shop_bot`                                       | **да**      |
| `BOT_MODE`              | Режим бота: `polling` или `webhook`                                        | `polling`                                                 | нет (`polling`) |
| `WEBAPP_URL`            | Публичный HTTPS-адрес Mini App, он же указывается в BotFather              | `https://abcd.trycloudflare.com`                          | **да** для работы в Telegram |
| `PUBLIC_BASE_URL`       | Публичный адрес backend: абсолютные ссылки на фото, установка webhook       | `https://api.example.com`                                 | нет (`http://localhost:8000`) |
| `DATABASE_URL`          | Строка подключения SQLAlchemy. Драйвер `asyncpg` обязателен                | `postgresql+asyncpg://meat:meat@localhost:5433/meat`      | **да**      |
| `POSTGRES_USER`         | Пользователь контейнера `db` (только для Compose)                          | `meat`                                                    | для Docker  |
| `POSTGRES_PASSWORD`     | Пароль контейнера `db` (только для Compose)                                | `meat`                                                    | для Docker  |
| `POSTGRES_DB`           | Имя базы в контейнере `db` (только для Compose)                            | `meat`                                                    | для Docker  |
| `ADMIN_TELEGRAM_IDS`    | Telegram ID администраторов через запятую                                  | `123456789,987654321`                                     | **да**      |
| `DELIVERY_PRICE`        | Стоимость доставки, руб. При самовывозе не добавляется                     | `300.00`                                                  | нет (`300.00`) |
| `PICKUP_ADDRESS`        | Адрес пункта самовывоза, показывается покупателю                           | `г. Москва, ул. Примерная, 1`                             | нет         |
| `ALLOWED_ORIGINS`       | Разрешённые CORS-источники через запятую                                   | `https://abcd.trycloudflare.com,http://localhost:5173`    | **да** для работы в Telegram |
| `UPLOAD_DIR`            | Каталог фотографий. Относительный путь — от корня проекта                  | `uploads` (в Docker `/app/uploads`)                       | нет (`uploads`) |
| `MAX_UPLOAD_SIZE_MB`    | Максимальный размер загружаемого файла, МБ                                 | `5`                                                       | нет (`5`)   |
| `DEV_AUTH_ENABLED`      | Вход без Telegram по заголовку `X-Dev-Telegram-Id`. В production запрещён  | `false`                                                   | нет (`false`) |
| `DEV_TELEGRAM_ID`       | Telegram ID, под которым работает dev-авторизация                          | `123456789`                                               | нет (`0`)   |
| `ENVIRONMENT`           | `development` или `production`. В `production` dev-вход блокируется        | `development`                                             | нет (`development`) |
| `LOG_LEVEL`             | Уровень логирования: `DEBUG`/`INFO`/`WARNING`/`ERROR`                      | `INFO`                                                    | нет (`INFO`) |
| `INIT_DATA_TTL_SECONDS` | Максимальный возраст `auth_date` в `initData`, секунды                     | `86400`                                                   | нет (`86400`) |
| `RATE_LIMIT_AUTH`       | Лимит запросов аутентификации, «запросов/секунд»                           | `30/60`                                                   | нет (`30/60`) |
| `RATE_LIMIT_ORDERS`     | Лимит создания заказов, «запросов/секунд»                                  | `10/60`                                                   | нет (`10/60`) |
| `RATE_LIMIT_UPLOADS`    | Лимит загрузки файлов, «запросов/секунд»                                   | `20/60`                                                   | нет (`20/60`) |
| `WEBHOOK_PATH`          | Путь приёма апдейтов Telegram при `BOT_MODE=webhook`                       | `/telegram/webhook`                                       | при webhook |
| `WEBHOOK_SECRET`        | Секрет в заголовке `X-Telegram-Bot-Api-Secret-Token`                       | длинная случайная строка                                  | при webhook |
| `DB_PORT`               | Порт PostgreSQL на хосте (только Compose)                                  | `5433`                                                    | нет (`5433`) |
| `BACKEND_PORT`          | Порт backend на хосте (только Compose)                                     | `8000`                                                    | нет (`8000`) |
| `FRONTEND_PORT`         | Порт frontend на хосте (только Compose)                                    | `5173`                                                    | нет (`5173`) |
| `VITE_API_BASE_URL`     | Базовый путь API в сборке фронтенда                                        | `/api/v1`                                                 | нет (`/api/v1`) |
| `TZ`                    | Часовой пояс контейнеров                                                   | `Europe/Moscow`                                           | нет         |

### Минимум, чтобы всё заработало

```dotenv
BOT_TOKEN=...              # без него не проверяется initData
BOT_USERNAME=...
ADMIN_TELEGRAM_IDS=...     # без него админка недоступна никому
WEBAPP_URL=https://...     # без HTTPS Mini App не откроется в Telegram
ALLOWED_ORIGINS=https://...
```

---

## Миграции базы данных

Все команды выполняются из каталога `backend` при активированном venv.
В Docker миграции применяются автоматически при старте контейнера `backend`.

```bash
alembic upgrade head                              # применить все миграции
alembic revision --autogenerate -m "add products" # создать миграцию по моделям
alembic downgrade -1                              # откатить одну миграцию
alembic downgrade base                            # откатить все
alembic current                                   # текущая ревизия
alembic history --verbose                         # история
```

Внутри Docker:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

Правила:

* После изменения моделей всегда создавайте миграцию `--autogenerate` и **просматривайте
  сгенерированный файл** — Alembic не всегда угадывает переименования и типы.
* Уже применённые в общей ветке миграции не редактируются: ошибку исправляет новая миграция.
* Автогенерация сравнивает модели с **реальной базой**, поэтому база должна быть доступна
  и находиться на предыдущей ревизии.

---

## Как назначить администратора

1. **Узнайте свой Telegram ID.** Напишите [@userinfobot](https://t.me/userinfobot)
   (или @getmyid_bot) — он ответит числом вроде `123456789`.
   Это именно ID аккаунта, не username.

2. **Впишите его в `.env`.** Несколько администраторов — через запятую, без пробелов:

   ```dotenv
   ADMIN_TELEGRAM_IDS=123456789,987654321
   ```

3. **Перезапустите backend и бота** — переменные читаются при старте:

   ```bash
   docker compose up -d --force-recreate backend bot
   ```

   При локальном запуске просто перезапустите `uvicorn` и `python -m app.bot_main`.

4. **Переоткройте Mini App.** При входе флаг `is_admin` в таблице `users`
   синхронизируется со списком, и в нижней навигации появится раздел «Админ».

Проверить, что права выданы:

```bash
docker compose exec db psql -U meat -d meat -c "SELECT telegram_id, username, is_admin FROM users;"
```

> Права проверяются на бэкенде в зависимости `AdminUser`. Скрытая кнопка в интерфейсе —
> не защита: без записи в `ADMIN_TELEGRAM_IDS` админ-эндпоинты отвечают `403`.

---

## Тестовые товары

Скрипт наполняет каталог примерами (говядина, курица, субпродукты и т.п.), чтобы
не заводить товары руками:

```bash
# локально, из каталога backend с активированным venv
python -m scripts.seed
```

```bash
# в Docker
docker compose exec backend python -m scripts.seed
```

Скрипт идемпотентен: повторный запуск не создаёт дубликаты.
Перед запуском база должна быть на актуальной ревизии (`alembic upgrade head`).

---

## Тесты

### Backend (pytest, база SQLite в памяти)

```bash
cd backend
pytest -q                                  # все тесты
pytest -v                                  # подробный вывод
pytest tests/test_orders.py                # один файл
pytest -k "cancel and idempotent"          # по имени
pytest --lf                                # только упавшие в прошлый раз
```

В Docker:

```bash
docker compose exec backend pytest -q
```

### Frontend (vitest)

```bash
cd frontend
npm run test           # прогон
npm run test -- --watch   # в режиме наблюдения
```

---

## Линтеры и форматирование

```bash
# backend
cd backend
ruff check .            # проверка
ruff check . --fix      # автоисправление
ruff format .           # форматирование
mypy app                # проверка типов

# frontend
cd frontend
npm run lint            # eslint
npm run lint -- --fix   # автоисправление
```

Правила ruff (длина строки 100, набор проверок `E,F,W,I,N,UP,B,C4,SIM,RUF`)
описаны в `backend/pyproject.toml`.

---

## Сборка фронтенда

```bash
cd frontend
npm run build     # production-сборка в frontend/dist
npm run preview   # локальный просмотр собранной версии
```

В Docker сборка выполняется автоматически на стадии `build` образа `frontend`,
результат отдаёт nginx. Пересобрать образ:

```bash
docker compose build frontend
docker compose up -d frontend
```

---

## Команды

Основной путь — прямые команды. `make` — необязательное удобство
(на Windows его обычно нет; см. [Makefile](Makefile)).

### Установка зависимостей

| Что | Linux / macOS | Windows PowerShell |
|---|---|---|
| venv backend | `cd backend && python3 -m venv .venv && source .venv/bin/activate` | `cd backend; python -m venv .venv; .\.venv\Scripts\Activate.ps1` |
| зависимости backend | `pip install -e ".[dev]"` | `pip install -e ".[dev]"` |
| зависимости frontend | `cd frontend && npm install` | `cd frontend; npm install` |
| всё сразу | `make install` | `make install` (если make установлен) |

### Запуск

| Что | Linux / macOS | Windows PowerShell |
|---|---|---|
| backend | `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` | `cd backend; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| бот | `cd backend && python -m app.bot_main` | `cd backend; python -m app.bot_main` |
| frontend | `cd frontend && npm run dev` | `cd frontend; npm run dev` |
| весь стек | `docker compose up --build` | `docker compose up --build` |
| стек в фоне | `docker compose up --build -d` | `docker compose up --build -d` |
| остановить | `docker compose down` | `docker compose down` |
| логи | `docker compose logs -f` | `docker compose logs -f` |

> Без активации venv вызывайте инструменты по полному пути:
> Linux/macOS — `backend/.venv/bin/uvicorn`, Windows — `backend\.venv\Scripts\uvicorn.exe`.

### Миграции

| Что | Команда (из `backend`) |
|---|---|
| применить | `alembic upgrade head` |
| создать | `alembic revision --autogenerate -m "описание"` |
| откатить одну | `alembic downgrade -1` |
| текущая ревизия | `alembic current` |
| в Docker | `docker compose exec backend alembic upgrade head` |

### Тесты, линтеры, сборка

| Что | Команда |
|---|---|
| тесты backend | `cd backend && pytest -q` |
| тесты frontend | `cd frontend && npm run test` |
| линтер backend | `cd backend && ruff check .` |
| автоисправление | `cd backend && ruff check . --fix && ruff format .` |
| типы | `cd backend && mypy app` |
| линтер frontend | `cd frontend && npm run lint` |
| сборка frontend | `cd frontend && npm run build` |
| тестовые товары | `cd backend && python -m scripts.seed` |

### Через make

```
make install       make dev-backend    make dev-frontend   make dev-bot
make migrate       make revision m="описание"              make downgrade
make seed          make test           make test-backend   make test-frontend
make lint          make format         make build
make up            make down           make down-v         make logs   make ps
make clean
```

---

## Структура каталогов

```
meat/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py          зависимости FastAPI: DbSession, CurrentUser, AdminUser
│   │   │   └── v1/              HTTP-роуты: каталог, заказы, админка
│   │   ├── bot/                 aiogram 3: хендлеры, клавиатуры, уведомления
│   │   ├── core/
│   │   │   ├── config.py        все переменные окружения и значения по умолчанию
│   │   │   ├── db.py            движок, сессии, определение диалекта
│   │   │   ├── errors.py        единый формат ошибок API
│   │   │   ├── logging.py       structlog
│   │   │   ├── money.py         округление Decimal, ROUND_HALF_UP
│   │   │   ├── ratelimit.py     ограничение частоты запросов
│   │   │   └── security.py      проверка подписи Telegram initData
│   │   ├── models/              ORM: users, products, orders, order_items
│   │   ├── repositories/        запросы к БД
│   │   ├── schemas/             Pydantic v2: валидация и форма ответов
│   │   ├── services/            бизнес-логика: заказы, каталог, авторизация
│   │   ├── storage/             абстракция хранилища файлов (LocalStorage)
│   │   ├── main.py              сборка приложения FastAPI
│   │   └── bot_main.py          точка входа бота
│   ├── alembic/                 миграции
│   ├── scripts/                 seed и служебные скрипты
│   ├── tests/                   pytest
│   ├── pyproject.toml           зависимости и настройки ruff / mypy / pytest
│   ├── Dockerfile               multi-stage образ (общий для API и бота)
│   ├── entrypoint.sh            ожидание БД → миграции → запуск команды (LF!)
│   └── .dockerignore
├── frontend/
│   ├── src/
│   │   ├── api/                 client.ts (заголовки, разбор ошибок) и types.ts
│   │   ├── components/          переиспользуемые компоненты
│   │   ├── pages/               экраны по маршрутам
│   │   ├── store/               Zustand: корзина в localStorage
│   │   └── main.tsx             точка входа
│   ├── package.json
│   ├── vite.config.ts
│   ├── Dockerfile               node → nginx
│   ├── nginx.conf               SPA fallback, прокси /api и /uploads, gzip, кэш
│   └── .dockerignore
├── docs/
│   └── CONTRACTS.md             контракты между слоями — источник истины
├── uploads/                     фотографии товаров (в git не попадают)
├── docker-compose.yml           db, backend, bot, frontend
├── .env.example                 шаблон окружения с комментариями
├── .gitignore
├── Makefile                     сокращения для частых команд
├── CLAUDE.md                    памятка для Claude Code
└── README.md
```

---

## Диагностика проблем

| Симптом | Причина и решение |
|---|---|
| Mini App не открывается в Telegram, белый экран | URL не HTTPS или не совпадает с указанным в BotFather. Проверьте `WEBAPP_URL` и `/setmenubutton`. |
| `401 unauthorized` при любом запросе | Не задан `BOT_TOKEN`, либо `initData` просрочена (`INIT_DATA_TTL_SECONDS`), либо приложение открыто вне Telegram без `DEV_AUTH_ENABLED`. |
| Ошибка CORS в консоли браузера | Адрес фронтенда не добавлен в `ALLOWED_ORIGINS`. Добавьте и перезапустите backend. |
| Раздела «Админ» нет | Ваш Telegram ID не в `ADMIN_TELEGRAM_IDS`, либо backend не перезапущен, либо Mini App не переоткрыт. |
| `port is already allocated` при `docker compose up` | Порт занят. Поменяйте `DB_PORT` / `BACKEND_PORT` / `FRONTEND_PORT` в `.env`. |
| backend перезапускается по кругу | Смотрите `docker compose logs backend`: чаще всего недоступна база или падает миграция. |
| `502 Bad Gateway` от nginx | backend не поднялся, либо был пересоздан и сменил IP. `docker compose restart frontend`. |
| `/bin/sh^M: bad interpreter` | `entrypoint.sh` сохранён с CRLF. Переведите в LF (см. ниже). |
| Фотографии не отображаются | Проверьте том `uploads` и `UPLOAD_DIR=/app/uploads` в контейнере: `docker compose exec backend ls -la /app/uploads`. |
| Товары пропали после `docker compose down -v` | `-v` удаляет тома вместе с базой. Без `-v` данные сохраняются. |

**Переводы строк.** Репозиторий разрабатывается на Windows, а `backend/entrypoint.sh`
исполняется внутри Linux-контейнера, поэтому он обязан храниться с LF. Проверить и починить:

```powershell
# PowerShell
$p = "backend/entrypoint.sh"
[IO.File]::WriteAllText($p, [IO.File]::ReadAllText($p).Replace("`r`n", "`n"))
```

```bash
# Linux / macOS / Git Bash
sed -i 's/\r$//' backend/entrypoint.sh
```

Чтобы git не портил скрипты автоматически, полезно настроить `core.autocrlf`:

```bash
git config core.autocrlf input
```

---

## Ограничения MVP

Осознанные упрощения — их стоит знать до запуска в бой.

* **Нет онлайн-оплаты.** Расчёт при получении наличными или переводом курьеру.
  Telegram Payments и эквайринг не подключены, `payment_method` всегда
  `cash_on_delivery`.
* **Файлы хранятся локально**, в томе `uploads`. При нескольких репликах backend
  каждая увидит свои файлы; бэкап тома делается отдельно от базы.
* **Ограничение частоты запросов — in-memory.** Счётчики живут в процессе:
  сбрасываются при рестарте и не общие для нескольких воркеров или реплик.
  Для production нужен общий счётчик в Redis.
* **Админка живёт только внутри Mini App.** Отдельного веб-интерфейса нет;
  без Telegram управлять каталогом нельзя (кроме прямых запросов к API).
* **Уведомления без очереди и повторов.** Если Telegram недоступен в момент отправки,
  сообщение теряется — брокера и ретраев нет.
* **Бот работает через long polling.** Один экземпляр бота на всю установку:
  два процесса с одним токеном будут конфликтовать. Горизонтальное масштабирование
  требует webhook.
* **Нет полнотекстового поиска и категорий товаров** — только поиск по имени в админке.
* **Нет отчётов и аналитики**, выгрузок и печатных форм.
* **Нет мультиязычности** — интерфейс и сообщения на русском.
* **Нет разграничения ролей внутри администраторов** — все админы равны.
* **Расписание доставки не проверяется** — дата и интервал принимаются как текст,
  занятость слотов не контролируется.
* **Удаление товара реализовано как архивирование** — физического удаления нет,
  чтобы не рушить историю заказов.

---

## Рекомендации для production

### HTTPS и reverse proxy

Ставьте перед стеком nginx или Caddy с сертификатом Let's Encrypt; наружу выпускайте
только 443. Порты `8000` и `5433` из `docker-compose.yml` уберите или ограничьте
адресом `127.0.0.1`:

```yaml
    ports:
      - "127.0.0.1:8000:8000"
```

uvicorn уже запускается с `--proxy-headers --forwarded-allow-ips "*"`; убедитесь,
что внешний прокси передаёт `X-Forwarded-For` и `X-Forwarded-Proto`.

### Webhook вместо long polling

Polling удобен в разработке, но держит постоянное соединение и не масштабируется.
В production переключитесь на webhook:

```dotenv
BOT_MODE=webhook
PUBLIC_BASE_URL=https://api.example.com
WEBHOOK_PATH=/telegram/webhook
WEBHOOK_SECRET=<длинная случайная строка>
```

Сгенерировать секрет:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Регистрация вручную (обычно это делает приложение при старте):

```bash
curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
     -d "url=https://api.example.com/telegram/webhook" \
     -d "secret_token=$WEBHOOK_SECRET" \
     -d "drop_pending_updates=true"

curl "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"   # проверить
curl "https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook"    # снять
```

Приложение обязано сверять заголовок `X-Telegram-Bot-Api-Secret-Token` с `WEBHOOK_SECRET`
и отбрасывать запросы с чужим значением. При webhook отдельный сервис `bot`
в `docker-compose.yml` не нужен — апдейты принимает backend.

### Вынос файлов в объектное хранилище

Локальный том — единственная точка отказа и препятствие для масштабирования.
В `app/storage/` уже есть интерфейс `Storage`; добавьте `S3Storage` (boto3 или aioboto3)
для S3 / MinIO / Yandex Object Storage, отдавайте фотографии через CDN и переключайте
реализацию переменной окружения. Старые файлы перенесите разовым скриптом.

### Резервное копирование PostgreSQL

```bash
# дамп
docker compose exec -T db pg_dump -U meat -d meat --format=custom > backup_$(date +%F).dump

# восстановление
cat backup_2026-09-07.dump | docker compose exec -T db pg_restore -U meat -d meat --clean --if-exists
```

Ежедневный бэкап в 3:30 с хранением 14 дней (`crontab -e`):

```cron
30 3 * * * cd /srv/meat && docker compose exec -T db pg_dump -U meat -d meat --format=custom > /var/backups/meat/db_$(date +\%F).dump 2>>/var/log/meat-backup.log
40 3 * * * find /var/backups/meat -name 'db_*.dump' -mtime +14 -delete
```

Отдельно копируйте том `uploads`:

```bash
docker run --rm -v dogmeat_uploads:/data -v /var/backups/meat:/backup alpine \
    tar czf /backup/uploads_$(date +%F).tar.gz -C /data .
```

Бэкап без проверенного восстановления бэкапом не является — раз в месяц
разворачивайте дамп на тестовом стенде.

### Ротация логов

Docker по умолчанию пишет логи без ограничений. Добавьте в `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
```

Либо задайте `logging` для каждого сервиса в compose. Логи приложения (structlog)
в production удобнее писать в JSON и собирать во внешнюю систему.

### Несколько воркеров

Один процесс uvicorn упирается в одно ядро. Для нагрузки:

```bash
gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 4 \
    --bind 0.0.0.0:8000 \
    --timeout 60 \
    --graceful-timeout 30 \
    --access-logfile -
```

Ориентир: `workers = 2 × ядра + 1`. Помните: in-memory rate limiting при нескольких
воркерах перестаёт быть общим — переносите счётчики в Redis. Бот при этом остаётся
в единственном экземпляре.

### Ограничение доступа к базе

* Уберите публикацию порта 5432/5433 наружу — доступ только внутри сети Compose.
* Смените пароль по умолчанию на длинный случайный, храните его в секретах
  (Docker secrets, Vault), а не в `.env` на диске.
* Заведите отдельного пользователя приложения без прав `SUPERUSER` и `CREATEDB`;
  миграции запускайте под отдельной учётной записью.
* Включите TLS для соединений и `scram-sha-256` в `pg_hba.conf`.
* Регулярно обновляйте образ `postgres:16-alpine` и перезапускайте с сохранением тома.

### Прочее перед запуском

* `ENVIRONMENT=production`, `DEV_AUTH_ENABLED=false`, `LOG_LEVEL=INFO`.
* `ALLOWED_ORIGINS` — только реальный домен Mini App, без `localhost` и без `*`.
* Мониторинг `GET /health` внешней проверкой (UptimeRobot, Prometheus blackbox).
* Отправка ошибок в Sentry или аналог.
* Обновляйте зависимости и пересобирайте образы: `docker compose build --pull`.
