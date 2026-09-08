# Развёртывание на сервере: чтобы работало с выключенным ПК

Пока магазин крутится на вашем компьютере, он живёт ровно до того момента, как вы
закроете ноутбук. Чтобы он работал всегда, его нужно перенести на сервер, который
не выключается. Ниже — рабочий путь целиком.

## Что понадобится

| Что | Зачем | Примерная цена |
|---|---|---|
| VPS, 2 ГБ RAM, 20 ГБ диска, Ubuntu 22.04/24.04 | там будут крутиться контейнеры | 200–500 ₽/мес |
| Домен (например `shop-myaso.ru`) | Telegram открывает Mini App только по HTTPS с доменом | 200–800 ₽/год |

Провайдера выбирайте на свой вкус (Timeweb, Selectel, Beget, Aeza, Hetzner, Contabo).
Важно одно: **сервер должен быть доступен из интернета по портам 80 и 443**, иначе
Let's Encrypt не выдаст сертификат.

> Про «просто оставить включённым ПК»: так тоже можно, но нужен статический публичный
> адрес или постоянный туннель, а домашний интернет обычно даёт серый IP. Плюс любое
> отключение света роняет магазин. Для боевой работы это плохой вариант.

---

## Шаг 1. Домен

Купите домен и в его DNS создайте одну запись:

```
Тип: A     Имя: @     Значение: <IP вашего сервера>     TTL: 300
```

Если хотите поддомен (`shop.example.com`) — то же самое, но `Имя: shop`.

Проверьте, что запись разошлась (с любой машины):

```bash
nslookup shop-myaso.ru
```

Пока в ответе не появится IP сервера, дальше идти бессмысленно — сертификат не выпустится.

## Шаг 2. Подготовка сервера

Подключитесь по SSH и поставьте Docker:

```bash
ssh root@<IP сервера>
```

```bash
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
```

`systemctl enable` здесь ключевой: он включает автозапуск Docker после перезагрузки
сервера. Вместе с `restart: always` в compose это значит, что магазин сам поднимется
после любого ребута или сбоя питания.

Откройте порты (если включён файрвол):

```bash
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```

## Шаг 3. Код на сервер

```bash
apt update && apt install -y git
git clone <адрес вашего репозитория> /opt/dogmeat
cd /opt/dogmeat
```

Если репозитория нет — скопируйте папку проекта с ПК:

```powershell
# выполнять на Windows, из каталога выше проекта
scp -r C:\Users\Alex\Desktop\meat root@<IP>:/opt/dogmeat
```

**Файл `.env` не копируйте** — он локальный, с SQLite и временным туннелем.
На сервере создадим свой.

## Шаг 4. Настройки

```bash
cd /opt/dogmeat
cp .env.example .env
nano .env
```

Заполните обязательное:

```dotenv
ENVIRONMENT=production
LOG_LEVEL=INFO

BOT_TOKEN=<токен от @BotFather>
BOT_USERNAME=myasoomsbot
BOT_MODE=polling

ADMIN_TELEGRAM_IDS=<ваш telegram id, узнать у @userinfobot>

# Ваш домен, обязательно https
DOMAIN=shop-myaso.ru
LETSENCRYPT_EMAIL=you@example.com
WEBAPP_URL=https://shop-myaso.ru
PUBLIC_BASE_URL=https://shop-myaso.ru
ALLOWED_ORIGINS=https://shop-myaso.ru

# Придумайте длинный пароль, не оставляйте meat/meat
POSTGRES_USER=meat
POSTGRES_PASSWORD=<длинный случайный пароль>
POSTGRES_DB=meat

# Обязательно выключено на публичном адресе
DEV_AUTH_ENABLED=false
DEV_TELEGRAM_ID=0

DELIVERY_PRICE=300.00
PICKUP_ADDRESS=<ваш адрес самовывоза>
```

Пароль удобно сгенерировать прямо на сервере:

```bash
openssl rand -base64 32
```

Закройте файл от чужих глаз:

```bash
chmod 600 .env
```

## Шаг 5. Запуск

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Первый запуск занимает 3–5 минут: собираются образы, поднимается PostgreSQL,
применяются миграции, Caddy получает сертификат.

Посмотреть, что всё поднялось:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f --tail=50
```

Ожидаемо: `db`, `backend`, `frontend` — `healthy`; `bot` и `caddy` — `running`.

Наполнить каталог примерами (по желанию):

```bash
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed
```

Проверить снаружи:

```bash
curl -I https://shop-myaso.ru
```

Должен вернуться `200` и валидный сертификат.

## Шаг 6. Привязать Mini App к боту

Адрес поменялся с временного туннеля на постоянный домен, поэтому кнопку надо
переставить. Прямо на сервере:

```bash
docker compose -f docker-compose.prod.yml exec backend python - <<'PY'
import asyncio
from aiogram.types import MenuButtonWebApp, WebAppInfo
from app.bot.bot import get_bot, shutdown
from app.core.config import settings

async def main():
    bot = get_bot()
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Магазин", web_app=WebAppInfo(url=settings.webapp_url))
    )
    print("кнопка меню ->", settings.webapp_url)
    await shutdown()

asyncio.run(main())
PY
```

И то же самое в @BotFather, чтобы приложение открывалось и по прямой ссылке:

1. `/mybots` → выберите бота → **Bot Settings** → **Menu Button** → **Configure menu button**
2. Пришлите `https://shop-myaso.ru` и название кнопки `Магазин`

## Шаг 7. Выключайте ПК

Всё. Магазин живёт на сервере, бот опрашивает Telegram оттуда же, база — в
контейнере PostgreSQL с постоянным томом. Ваш компьютер больше ни при чём.

---

## Обслуживание

### Обновление после правок кода

```bash
cd /opt/dogmeat
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Миграции применятся автоматически при старте backend.

### Логи

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f bot
```

### Резервные копии

Данные заказов — самое ценное. Настройте ежедневный дамп:

```bash
mkdir -p /opt/backups
crontab -e
```

Добавьте строку (дамп в 4 утра, хранение 14 дней):

```cron
0 4 * * * cd /opt/dogmeat && docker compose -f docker-compose.prod.yml exec -T db pg_dump -U meat meat | gzip > /opt/backups/meat-$(date +\%F).sql.gz && find /opt/backups -name 'meat-*.sql.gz' -mtime +14 -delete
```

Фотографии лежат в томе `uploads`:

```bash
docker run --rm -v dogmeat_uploads:/data -v /opt/backups:/backup alpine \
  tar czf /backup/uploads-$(date +%F).tar.gz -C /data .
```

Восстановление базы из дампа:

```bash
gunzip -c /opt/backups/meat-2026-09-08.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U meat -d meat
```

**Проверьте восстановление хотя бы раз.** Бэкап, который никогда не разворачивали,
бэкапом не считается.

### Перезагрузка сервера

Ничего делать не нужно: `restart: always` плюс включённый `systemctl enable docker`
поднимут всё автоматически. Проверить после ребута:

```bash
docker compose -f docker-compose.prod.yml ps
```

---

## Вариант без открытых портов: Cloudflare Named Tunnel

Если провайдер не даёт открыть 80/443 или не хочется светить IP, можно оставить
сервер полностью закрытым, а наружу выпустить постоянный туннель Cloudflare.
В отличие от временного `trycloudflare`, адрес здесь стабильный.

Понадобится домен, делегированный на Cloudflare (бесплатный план подойдёт).

```bash
cloudflared tunnel login
cloudflared tunnel create dogmeat
cloudflared tunnel route dns dogmeat shop-myaso.ru
```

Затем `~/.cloudflared/config.yml`:

```yaml
tunnel: dogmeat
credentials-file: /root/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: shop-myaso.ru
    service: http://localhost:8080
  - service: http_status:404
```

В `docker-compose.prod.yml` уберите сервис `caddy` и опубликуйте frontend на
`127.0.0.1:8080:80`. Туннель поставьте службой, чтобы пережил перезагрузку:

```bash
cloudflared service install
systemctl enable --now cloudflared
```

TLS в этом случае обеспечивает Cloudflare, Let's Encrypt не нужен.

---

## Промежуточный вариант: оставить на своём ПК

Если сервера пока нет, а перезагрузки переживать хочется, можно завести автозапуск
на Windows. Магазин будет работать, **пока компьютер включён** — задачу «выключить ПК»
это не решает, но защищает от случайного ребута.

Поставьте Docker Desktop и добавьте в автозагрузку:

```powershell
docker compose -f docker-compose.yml up -d
```

Плюс постоянный туннель (Named Tunnel из раздела выше) вместо временного —
иначе адрес будет меняться при каждом перезапуске.

---

## Частые проблемы

| Симптом | Причина и что делать |
|---|---|
| Caddy не выпускает сертификат | A-запись ещё не разошлась или закрыт порт 80. Проверьте `nslookup` и `ufw status` |
| `502 Bad Gateway` | backend не поднялся. `docker compose -f docker-compose.prod.yml logs backend` |
| Бот молчит | Проверьте `BOT_TOKEN` и что запущен один экземпляр: два процесса polling конфликтуют |
| Mini App открывается пустым | `WEBAPP_URL` и `ALLOWED_ORIGINS` должны точно совпадать с доменом, вместе с `https://` |
| «Раздел недоступен» в админке | Ваш Telegram ID не попал в `ADMIN_TELEGRAM_IDS`. После правки — `up -d` заново |
| Не сохраняются фото | Проверьте том: `docker volume inspect dogmeat_uploads` |
