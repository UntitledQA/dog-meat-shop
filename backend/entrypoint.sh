#!/bin/sh
# Точка входа контейнера backend/bot.
#   1. ждём, пока PostgreSQL начнёт принимать соединения;
#   2. применяем миграции Alembic (RUN_MIGRATIONS=false — пропустить, так делает бот);
#   3. запускаем переданную команду через exec, чтобы она стала PID 1
#      и корректно получала SIGTERM от `docker compose down`.
#
# ВНИМАНИЕ: файл должен храниться с переводами строк LF, иначе внутри Linux-контейнера
# получим «/bin/sh^M: bad interpreter». В .gitattributes/редакторе следите за eol=lf.

set -e

DB_WAIT_TIMEOUT="${DB_WAIT_TIMEOUT:-60}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
UPLOAD_DIR="${UPLOAD_DIR:-/app/uploads}"

log() {
    echo "[entrypoint] $*"
}

# --------------------------------------------------------------- ожидание БД
log "Ожидание базы данных (таймаут ${DB_WAIT_TIMEOUT} c)..."
python - "$DB_WAIT_TIMEOUT" <<'PYCODE'
import os
import re
import sys
import time

timeout = float(sys.argv[1])
url = os.environ.get("DATABASE_URL", "").strip()

if not url:
    print("[entrypoint] DATABASE_URL не задан — ожидание пропущено", flush=True)
    sys.exit(0)

if url.startswith("sqlite"):
    print("[entrypoint] DATABASE_URL указывает на SQLite — ожидание пропущено", flush=True)
    sys.exit(0)

# postgresql+asyncpg://... -> postgresql://... (psycopg2 не понимает суффикс драйвера)
dsn = re.sub(r"^postgresql\+[a-z0-9_]+://", "postgresql://", url)
dsn = re.sub(r"^postgres\+[a-z0-9_]+://", "postgresql://", dsn)

import psycopg2  # noqa: E402  (импорт после проверки схемы URL)

deadline = time.time() + timeout
last_error = None
while time.time() < deadline:
    try:
        connection = psycopg2.connect(dsn, connect_timeout=3)
        connection.close()
        print("[entrypoint] База данных доступна", flush=True)
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — ждём любую ошибку соединения
        last_error = exc
        time.sleep(1)

print(f"[entrypoint] База данных недоступна за {timeout} c: {last_error}", file=sys.stderr, flush=True)
sys.exit(1)
PYCODE

# ------------------------------------------------------------------ миграции
if [ "$RUN_MIGRATIONS" = "true" ] || [ "$RUN_MIGRATIONS" = "1" ]; then
    if [ -f /app/alembic.ini ]; then
        log "Применение миграций: alembic upgrade head"
        alembic upgrade head
    else
        log "alembic.ini не найден — миграции пропущены"
    fi
else
    log "RUN_MIGRATIONS=${RUN_MIGRATIONS} — миграции пропущены"
fi

# ------------------------------------------------------------ каталог файлов
mkdir -p "$UPLOAD_DIR" 2>/dev/null || log "Не удалось создать ${UPLOAD_DIR} (том смонтирован снаружи?)"

log "Запуск: $*"
exec "$@"
