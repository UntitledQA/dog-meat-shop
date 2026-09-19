#!/usr/bin/env bash
#
# Разворачивает «Мясо для собак» на чистом Ubuntu-сервере.
# Скрипт идемпотентный: повторный запуск обновляет код и пересобирает контейнеры,
# не теряя базу, загруженные фотографии и сертификат.
#
# Запуск на сервере:
#   DOMAIN=shop.example.com BOT_TOKEN=... BOT_USERNAME=... \
#   ADMIN_TELEGRAM_IDS=... LETSENCRYPT_EMAIL=... \
#   bash scripts/vps-bootstrap.sh
#
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/UntitledQA/dog-meat-shop.git}"
APP_DIR="${APP_DIR:-/opt/dogmeat}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mОШИБКА: %s\033[0m\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------- 0. проверки
[ "$(id -u)" -eq 0 ] || fail "запускайте от root"

for var in DOMAIN BOT_TOKEN BOT_USERNAME ADMIN_TELEGRAM_IDS; do
    [ -n "${!var:-}" ] || fail "не задана переменная $var"
done
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"
PICKUP_ADDRESS="${PICKUP_ADDRESS:-Уточните адрес самовывоза}"
DELIVERY_PRICE="${DELIVERY_PRICE:-300.00}"

# --------------------------------------------------------- 1. swap для 1 ГБ
# Сборка фронтенда (vite) и Postgres на 1 ГБ без подкачки упираются в OOM-killer.
RAM_MB=$(free -m | awk '/^Mem:/ {print $2}')
SWAP_MB=$(free -m | awk '/^Swap:/ {print $2}')
log "Память: ${RAM_MB} МБ RAM, ${SWAP_MB} МБ swap"
if [ "$RAM_MB" -lt 2048 ] && [ "$SWAP_MB" -lt 1024 ]; then
    log "Создаю файл подкачки 2 ГБ"
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
    sysctl -w vm.swappiness=10 >/dev/null
    grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

# На 1 ГБ два воркера uvicorn — лишний расход памяти.
if [ "$RAM_MB" -lt 2048 ]; then UVICORN_WORKERS=1; else UVICORN_WORKERS=2; fi

# ------------------------------------------------------------- 2. пакеты
log "Обновляю пакеты и ставлю git/curl"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates dnsutils >/dev/null

if ! command -v docker >/dev/null 2>&1; then
    log "Ставлю Docker"
    curl -fsSL https://get.docker.com | sh
fi
# Автозапуск после перезагрузки сервера — вместе с restart: always в compose
# это и означает «работает, когда мой ПК выключен».
systemctl enable --now docker

# -------------------------------------------------------------- 3. файрвол
if command -v ufw >/dev/null 2>&1; then
    log "Открываю порты 22, 80, 443"
    ufw allow 22/tcp  >/dev/null || true
    ufw allow 80/tcp  >/dev/null || true
    ufw allow 443/tcp >/dev/null || true
    ufw --force enable >/dev/null || true
fi

# ------------------------------------------------------------------ 4. DNS
log "Проверяю, что $DOMAIN указывает на этот сервер"
SERVER_IP="$(curl -fsS --max-time 10 https://api.ipify.org || echo '')"
DOMAIN_IP="$(dig +short A "$DOMAIN" | tail -1 || echo '')"
echo "    IP сервера : ${SERVER_IP:-неизвестен}"
echo "    A-запись   : ${DOMAIN_IP:-отсутствует}"
if [ -z "$DOMAIN_IP" ]; then
    fail "у домена $DOMAIN нет A-записи. Пропишите её в DNS и запустите скрипт снова —
      без этого Let's Encrypt не выдаст сертификат, а Telegram не откроет Mini App."
fi
if [ -n "$SERVER_IP" ] && [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
    fail "домен указывает на $DOMAIN_IP, а сервер имеет адрес $SERVER_IP.
      Исправьте A-запись (DNS обновляется до нескольких часов) и повторите."
fi

# -------------------------------------------------------------- 5. код
if [ -d "$APP_DIR/.git" ]; then
    log "Обновляю код в $APP_DIR"
    git -C "$APP_DIR" fetch --quiet origin
    git -C "$APP_DIR" reset --hard --quiet origin/main
else
    log "Клонирую репозиторий в $APP_DIR"
    git clone --quiet "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# --------------------------------------------------------------- 6. .env
# Пароль базы генерируем один раз: при повторном запуске переиспользуем старый,
# иначе Postgres с уже созданным томом перестанет пускать backend.
if [ -f .env ] && grep -q '^POSTGRES_PASSWORD=' .env; then
    PG_PASS="$(grep '^POSTGRES_PASSWORD=' .env | head -1 | cut -d= -f2-)"
    log "Переиспользую существующий пароль базы"
else
    PG_PASS="$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 32)"
    log "Сгенерировал новый пароль базы"
fi

log "Пишу .env"
umask 077
cat > .env <<ENV_EOF
# Сгенерировано scripts/vps-bootstrap.sh. Файл содержит секреты — права 600.
ENVIRONMENT=production
LOG_LEVEL=INFO

BOT_TOKEN=${BOT_TOKEN}
BOT_USERNAME=${BOT_USERNAME}
BOT_MODE=polling

ADMIN_TELEGRAM_IDS=${ADMIN_TELEGRAM_IDS}

# Вход вне Telegram запрещён: только подпись initData.
DEV_AUTH_ENABLED=false
DEV_TELEGRAM_ID=0

DOMAIN=${DOMAIN}
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL}
WEBAPP_URL=https://${DOMAIN}
PUBLIC_BASE_URL=https://${DOMAIN}
ALLOWED_ORIGINS=https://${DOMAIN}

POSTGRES_USER=meat
POSTGRES_PASSWORD=${PG_PASS}
POSTGRES_DB=meat
DATABASE_URL=postgresql+asyncpg://meat:${PG_PASS}@db:5432/meat

UVICORN_WORKERS=${UVICORN_WORKERS}

DELIVERY_PRICE=${DELIVERY_PRICE}
PICKUP_ADDRESS=${PICKUP_ADDRESS}

UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE_MB=5

INIT_DATA_TTL_SECONDS=86400
RATE_LIMIT_AUTH=30/60
RATE_LIMIT_ORDERS=10/60
RATE_LIMIT_UPLOADS=20/60
ENV_EOF
chmod 600 .env
umask 022

# ------------------------------------------------------------- 7. запуск
log "Собираю и запускаю контейнеры (первый раз это 5–15 минут)"
docker compose -f docker-compose.prod.yml up -d --build

# --------------------------------------------------------------- 8. проверка
log "Убираю промежуточные образы (на диске 10 ГБ — иначе забьётся за несколько пересборок)"
docker image prune -f >/dev/null || true

log "Жду, пока сервисы станут здоровыми"
for _ in $(seq 1 60); do
    if docker exec dogmeat-backend python -c \
        "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5).status==200 else 1)" \
        >/dev/null 2>&1; then
        break
    fi
    sleep 5
done

log "Состояние контейнеров"
docker compose -f docker-compose.prod.yml ps

log "Проверка снаружи"
echo -n "    https://${DOMAIN}/health -> "
curl -fsS --max-time 20 "https://${DOMAIN}/health" || echo "пока недоступно (сертификат выпускается до минуты)"
echo ""

cat <<DONE_EOF

Готово. Осталось два шага в Telegram:
  1. @BotFather -> /setmenubutton -> выбрать @${BOT_USERNAME}
     -> адрес https://${DOMAIN} -> текст кнопки «Магазин»
  2. Открыть @${BOT_USERNAME} и отправить /start

Полезное:
  docker compose -f ${APP_DIR}/docker-compose.prod.yml logs -f backend bot
  docker compose -f ${APP_DIR}/docker-compose.prod.yml restart
  bash ${APP_DIR}/scripts/vps-bootstrap.sh    # обновить до свежего main
DONE_EOF
