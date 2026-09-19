#!/usr/bin/env bash
#
# Развёртывание БЕЗ Docker: systemd + системные nginx и PostgreSQL.
#
# Когда нужен этот скрипт, а не vps-bootstrap.sh:
#   * на сервере уже есть nginx, занимающий 80/443 (Caddy их просто не получит);
#   * мало памяти или диска — контейнер со вторым PostgreSQL не окупается;
#   * на машине уже живёт другой проект, который нельзя трогать.
# В остальных случаях проще и переносимее Docker-вариант.
#
# Скрипт идемпотентный: повторный запуск обновляет код, пересобирает фронтенд
# и перезапускает службы, не теряя базу, фотографии и сертификат.
#
# Первый запуск (секреты передаются один раз, дальше берутся из .env):
#   DOMAIN=shop.example.com BOT_TOKEN=... BOT_USERNAME=... \
#   ADMIN_TELEGRAM_IDS=... bash scripts/vps-native.sh
#
# Обновление до свежего main:
#   bash /opt/dogmeat/scripts/vps-native.sh
#
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/UntitledQA/dog-meat-shop.git}"
APP_DIR="${APP_DIR:-/opt/dogmeat}"
APP_USER="${APP_USER:-meat}"
API_PORT="${API_PORT:-8001}"
STATE_DIR="${STATE_DIR:-/var/lib/dogmeat}"
WEB_ROOT="${WEB_ROOT:-/var/www/dogmeat}"
PYTHON_DIR="${PYTHON_DIR:-/opt/pythons}"
# Ubuntu 26.04 приносит Python 3.14, под который у asyncpg и psycopg2 нет колёс,
# поэтому ставим отдельный 3.12 в общий каталог — не в /root, куда служебному
# пользователю хода нет из-за ProtectHome в юните.
PY_VERSION="${PY_VERSION:-3.12}"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31mОШИБКА: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "запускайте от root"

# ------------------------------------------ 1. секреты: из .env или из окружения
if [ -f "$APP_DIR/.env" ]; then
    from_env() { grep "^$1=" "$APP_DIR/.env" | head -1 | cut -d= -f2- || true; }
    DOMAIN="${DOMAIN:-$(from_env DOMAIN)}"
    BOT_TOKEN="${BOT_TOKEN:-$(from_env BOT_TOKEN)}"
    BOT_USERNAME="${BOT_USERNAME:-$(from_env BOT_USERNAME)}"
    ADMIN_TELEGRAM_IDS="${ADMIN_TELEGRAM_IDS:-$(from_env ADMIN_TELEGRAM_IDS)}"
    DELIVERY_PRICE="${DELIVERY_PRICE:-$(from_env DELIVERY_PRICE)}"
    PICKUP_ADDRESS="${PICKUP_ADDRESS:-$(from_env PICKUP_ADDRESS)}"
    ADDRESS_SUGGEST_PROVIDER="${ADDRESS_SUGGEST_PROVIDER:-$(from_env ADDRESS_SUGGEST_PROVIDER)}"
    DADATA_API_KEY="${DADATA_API_KEY:-$(from_env DADATA_API_KEY)}"
    # Пароль базы переиспользуем всегда: том с данными уже создан под него.
    PG_PASS="$(from_env POSTGRES_PASSWORD)"
fi
for var in DOMAIN BOT_TOKEN BOT_USERNAME ADMIN_TELEGRAM_IDS; do
    [ -n "${!var:-}" ] || fail "не задана переменная $var"
done
PG_PASS="${PG_PASS:-$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 32)}"
DELIVERY_PRICE="${DELIVERY_PRICE:-300.00}"
PICKUP_ADDRESS="${PICKUP_ADDRESS:-Уточните адрес самовывоза}"
# Подсказки адреса выключены, пока владелец магазина не выберет провайдера:
# включение отправляет набранный покупателем адрес стороннему сервису.
ADDRESS_SUGGEST_PROVIDER="${ADDRESS_SUGGEST_PROVIDER:-none}"
DADATA_API_KEY="${DADATA_API_KEY:-}"

# ---------------------------------------------------------------- 2. пакеты
# Ставим только недостающее. Скопом нельзя: если Node пришёл из репозитория
# NodeSource, пакет npm из репозитория Ubuntu конфликтует с ним и apt падает.
log "Проверяю системные пакеты"
export DEBIAN_FRONTEND=noninteractive
declare -A NEEDS=(
    [git]=git [curl]=curl [rsync]=rsync [nginx]=nginx
    [psql]=postgresql [certbot]=certbot [node]=nodejs [npm]=npm [dig]=dnsutils
)
MISSING=()
for cmd in "${!NEEDS[@]}"; do
    command -v "$cmd" >/dev/null 2>&1 || MISSING+=("${NEEDS[$cmd]}")
done
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "    ставлю: ${MISSING[*]}"
    apt-get update -qq
    apt-get install -y -qq "${MISSING[@]}" >/dev/null
else
    echo "    всё на месте"
fi
systemctl enable --now nginx postgresql >/dev/null 2>&1 || true

# ------------------------------------------------------------------- 3. DNS
log "Проверяю A-запись домена $DOMAIN"
SERVER_IP="$(curl -fsS --max-time 10 https://api.ipify.org || echo '')"
DOMAIN_IP="$(dig +short A "$DOMAIN" | tail -1 || echo '')"
echo "    сервер: ${SERVER_IP:-?}   домен: ${DOMAIN_IP:-нет записи}"
[ -n "$DOMAIN_IP" ] || fail "у $DOMAIN нет A-записи — сертификат не выпустится"
if [ -n "$SERVER_IP" ] && [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
    fail "домен указывает на $DOMAIN_IP, а сервер — $SERVER_IP"
fi

# ------------------------------------------------------ 4. пользователь и код
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
if [ -d "$APP_DIR/.git" ]; then
    log "Обновляю код"
    git -C "$APP_DIR" fetch -q origin
    git -C "$APP_DIR" reset -q --hard origin/main
else
    log "Клонирую репозиторий"
    git clone -q "$REPO_URL" "$APP_DIR"
fi
install -d -o "$APP_USER" -g "$APP_USER" "$STATE_DIR" "$STATE_DIR/uploads"

# ------------------------------------------------------------ 5. Python и venv
if ! command -v uv >/dev/null 2>&1; then
    log "Ставлю uv"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh >/dev/null 2>&1
fi
export UV_PYTHON_INSTALL_DIR="$PYTHON_DIR"
mkdir -p "$PYTHON_DIR"
uv python install "$PY_VERSION" >/dev/null 2>&1 || true
chmod -R a+rX "$PYTHON_DIR"

log "Собираю виртуальное окружение"
cd "$APP_DIR"
[ -x .venv/bin/python ] || uv venv --python "$PY_VERSION" .venv >/dev/null
uv pip install -q --python .venv/bin/python -e ./backend
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ------------------------------------------------------------------ 6. база
log "Настраиваю базу в системном PostgreSQL"
if sudo -u postgres psql -qtAc "SELECT 1 FROM pg_roles WHERE rolname='$APP_USER'" | grep -q 1; then
    sudo -u postgres psql -qc "ALTER ROLE $APP_USER WITH LOGIN PASSWORD '$PG_PASS'"
else
    sudo -u postgres psql -qc "CREATE ROLE $APP_USER WITH LOGIN PASSWORD '$PG_PASS'"
fi
sudo -u postgres psql -qtAc "SELECT 1 FROM pg_database WHERE datname='meat'" | grep -q 1 \
    || sudo -u postgres createdb -O "$APP_USER" -E UTF8 meat

# ------------------------------------------------------------------ 7. .env
log "Пишу .env"
umask 077
cat > "$APP_DIR/.env" <<ENVEOF
# Сгенерировано scripts/vps-native.sh. Файл содержит секреты — права 600.
ENVIRONMENT=production
LOG_LEVEL=INFO

BOT_TOKEN=${BOT_TOKEN}
BOT_USERNAME=${BOT_USERNAME}
BOT_MODE=polling

ADMIN_TELEGRAM_IDS=${ADMIN_TELEGRAM_IDS}

DEV_AUTH_ENABLED=false
DEV_TELEGRAM_ID=0

DOMAIN=${DOMAIN}
WEBAPP_URL=https://${DOMAIN}
PUBLIC_BASE_URL=https://${DOMAIN}
ALLOWED_ORIGINS=https://${DOMAIN}

POSTGRES_USER=${APP_USER}
POSTGRES_PASSWORD=${PG_PASS}
POSTGRES_DB=meat
DATABASE_URL=postgresql+asyncpg://${APP_USER}:${PG_PASS}@127.0.0.1:5432/meat

DELIVERY_PRICE=${DELIVERY_PRICE}
PICKUP_ADDRESS=${PICKUP_ADDRESS}

# Подсказки адреса: none | photon | dadata. Ключ DaData никогда не уходит
# в браузер — запрос идёт через backend-прокси.
ADDRESS_SUGGEST_PROVIDER=${ADDRESS_SUGGEST_PROVIDER}
DADATA_API_KEY=${DADATA_API_KEY}

UPLOAD_DIR=${STATE_DIR}/uploads
MAX_UPLOAD_SIZE_MB=5

INIT_DATA_TTL_SECONDS=86400
RATE_LIMIT_AUTH=30/60
RATE_LIMIT_ORDERS=10/60
RATE_LIMIT_UPLOADS=20/60
ENVEOF
umask 022
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

# --------------------------------------------------------------- 8. миграции
log "Применяю миграции"
cd "$APP_DIR/backend"
sudo -u "$APP_USER" HOME="$STATE_DIR" "$APP_DIR/.venv/bin/alembic" upgrade head 2>&1 | tail -3

# -------------------------------------------------------------- 9. фронтенд
log "Собираю фронтенд"
cd "$APP_DIR/frontend"
export NODE_OPTIONS=--max-old-space-size=700
export CI=true
npm ci --no-audit --no-fund >/dev/null
VITE_API_BASE_URL="" npm run build >/dev/null
install -d -o www-data -g www-data "$WEB_ROOT"
rsync -a --delete dist/ "$WEB_ROOT/"
chown -R www-data:www-data "$WEB_ROOT"
# node_modules весит больше, чем всё приложение, а нужен только на время сборки.
rm -rf node_modules

# -------------------------------------------------------------- 10. systemd
log "Ставлю службы"
write_unit() {
    local name="$1" descr="$2" exec_start="$3" restart_sec="$4"
    cat > "/etc/systemd/system/${name}.service" <<UNITEOF
[Unit]
Description=${descr}
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=exec
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}/backend
# ProtectHome=true прячет /home, а asyncpg ищет там \$HOME/.postgresql/postgresql.key
# и падает с PermissionError вместо «файла нет». Поэтому HOME — в каталоге состояния.
Environment=HOME=${STATE_DIR}
ExecStart=${exec_start}
Restart=always
RestartSec=${restart_sec}
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${STATE_DIR}

[Install]
WantedBy=multi-user.target
UNITEOF
}

# Один воркер: на гигабайте памяти рядом с PostgreSQL второй не окупается.
write_unit dogmeat-api "Мясо для собак — API" \
    "${APP_DIR}/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT} --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1" \
    5
write_unit dogmeat-bot "Мясо для собак — Telegram-бот" \
    "${APP_DIR}/.venv/bin/python -m app.bot_main" \
    10

systemctl daemon-reload
systemctl enable dogmeat-api dogmeat-bot >/dev/null 2>&1
systemctl restart dogmeat-api
sleep 6
systemctl restart dogmeat-bot

# ---------------------------------------------------------------- 11. nginx
log "Настраиваю nginx"
mkdir -p /var/www/html/.well-known/acme-challenge

if [ ! -d "/etc/letsencrypt/live/${DOMAIN}" ]; then
    # Пока сертификата нет, 443-й блок описать нельзя — nginx не примет конфиг.
    cat > /etc/nginx/sites-available/dogmeat <<TMPEOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 200 "ok"; add_header Content-Type text/plain; }
}
TMPEOF
    ln -sfn /etc/nginx/sites-available/dogmeat /etc/nginx/sites-enabled/dogmeat
    nginx -t && systemctl reload nginx
    log "Выпускаю сертификат Let's Encrypt"
    if [ -n "${LETSENCRYPT_EMAIL:-}" ]; then
        certbot certonly --webroot -w /var/www/html -d "$DOMAIN" -d "www.${DOMAIN}" \
            --non-interactive --agree-tos --keep-until-expiring --email "$LETSENCRYPT_EMAIL"
    else
        # Если на сервере уже есть ACME-аккаунт, certbot возьмёт его сам.
        certbot certonly --webroot -w /var/www/html -d "$DOMAIN" -d "www.${DOMAIN}" \
            --non-interactive --agree-tos --keep-until-expiring \
            || certbot certonly --webroot -w /var/www/html -d "$DOMAIN" -d "www.${DOMAIN}" \
               --non-interactive --agree-tos --keep-until-expiring --register-unsafely-without-email
    fi
fi

cat > /etc/nginx/sites-available/dogmeat <<NGINXEOF
# Магазин «Мясо для собак». Статика SPA отдаётся напрямую, /api, /health
# и /uploads проксируются на службу dogmeat-api (127.0.0.1:${API_PORT}).
# Другие сайты этого сервера описаны своими server-блоками и не затрагиваются.

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} www.${DOMAIN};

    # Проверка владения доменом при продлении сертификата.
    location /.well-known/acme-challenge/ { root /var/www/html; }

    location / { return 301 https://${DOMAIN}\$request_uri; }
}

# www -> без www: Mini App должен открываться с одного origin, иначе подпись
# initData и CORS считались бы для разных адресов.
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name www.${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    return 301 https://${DOMAIN}\$request_uri;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    root ${WEB_ROOT};
    index index.html;

    # Бэкенд ограничивает загрузку 5 МБ, здесь небольшой запас.
    client_max_body_size 10m;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    gzip on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_types application/javascript application/json image/svg+xml text/css text/plain;

    location /api/ {
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        # Перезаписываем, а не дополняем: клиентскому X-Forwarded-For доверять
        # нельзя — по нему считается частота запросов с одного адреса.
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
    }

    location = /health {
        proxy_pass http://127.0.0.1:${API_PORT}/health;
        proxy_set_header Host \$host;
        access_log off;
    }

    location /uploads/ {
        proxy_pass http://127.0.0.1:${API_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
        expires 7d;
        add_header Cache-Control "public";
    }

    # В именах файлов есть хеш сборки, поэтому их можно кэшировать надолго.
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files \$uri =404;
    }

    # index.html не кэшируем: иначе после обновления пользователь получит старый SPA.
    location = /index.html { add_header Cache-Control "no-cache"; }

    location / { try_files \$uri \$uri/ /index.html; }
}
NGINXEOF

ln -sfn /etc/nginx/sites-available/dogmeat /etc/nginx/sites-enabled/dogmeat
nginx -t && systemctl reload nginx

# -------------------------------------------------------------- 12. проверка
log "Проверка"
for _ in $(seq 1 20); do
    curl -fsS --max-time 5 "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 && break
    sleep 3
done
printf "    службы: api=%s bot=%s nginx=%s\n" \
    "$(systemctl is-active dogmeat-api)" \
    "$(systemctl is-active dogmeat-bot)" \
    "$(systemctl is-active nginx)"
printf "    /health: %s\n" "$(curl -s --max-time 10 "http://127.0.0.1:${API_PORT}/health")"

cat <<DONEEOF

Готово. Магазин: https://${DOMAIN}

Кнопка меню бота — в @BotFather: /setmenubutton -> @${BOT_USERNAME}
-> адрес https://${DOMAIN} -> текст «Магазин».

Логи:      journalctl -u dogmeat-api -u dogmeat-bot -f
Обновить:  bash ${APP_DIR}/scripts/vps-native.sh
DONEEOF
