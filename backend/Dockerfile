# syntax=docker/dockerfile:1
#
# Образ backend: обслуживает и API (uvicorn), и бота (python -m app.bot_main).
# Multi-stage: колёса собираются в builder, в runtime уезжает только готовый venv.

# --------------------------------------------------------------------- builder
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

# Компиляторы нужны только на случай, если для какой-то зависимости нет колеса.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv

WORKDIR /build

# Шаг 1: зависимости отдельным слоем — он пересобирается только при изменении
# pyproject.toml, а не при каждой правке кода.
COPY pyproject.toml ./
RUN python -c "import pathlib, tomllib; data = tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); pathlib.Path('requirements.txt').write_text(chr(10).join(data['project']['dependencies']) + chr(10), encoding='utf-8')" \
    && pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

# Шаг 2: код и установка самого пакета (секция [project] в pyproject.toml).
COPY . .
RUN pip install --no-deps .

# --------------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH" \
    UPLOAD_DIR=/app/uploads \
    TZ=Europe/Moscow

# Непривилегированный пользователь: контейнер не должен работать от root.
RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Исходники нужны и в runtime: alembic/, alembic.ini, scripts/ не входят в пакет,
# а config.py вычисляет BASE_DIR относительно расположения файлов проекта.
COPY --chown=appuser:appuser . /app

# Каталог загрузок создаётся до объявления тома: именованный том наследует
# владельца и права этого каталога при первом монтировании.
RUN mkdir -p /app/uploads \
    && chown -R appuser:appuser /app \
    && chmod +x /app/entrypoint.sh

USER appuser

EXPOSE 8000

# entrypoint: ожидание БД -> alembic upgrade head -> exec "$@"
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
