# syntax=docker/dockerfile:1
#
# Многоступенчатая сборка фронтенда:
#   build   — node собирает SPA в /app/dist;
#   runtime — nginx:alpine отдаёт статику и проксирует /api и /uploads на backend.
# Node в итоговый образ не попадает.

# ----------------------------------------------------------------------- build
FROM node:22-alpine AS build

ENV CI=true \
    NODE_ENV=development

WORKDIR /app

# Манифесты отдельным слоем: установка зависимостей переиспользуется, пока
# package.json / package-lock.json не изменились.
# `*` после package-lock.json — чтобы COPY не падал, если lock-файла ещё нет.
COPY package.json ./
COPY package-lock.json* ./

# npm ci — воспроизводимая установка по lock-файлу; без него откатываемся на npm install.
RUN if [ -f package-lock.json ]; then \
        npm ci --no-audit --no-fund; \
    else \
        echo "package-lock.json не найден — npm install (сборка невоспроизводима)"; \
        npm install --no-audit --no-fund; \
    fi

COPY . .

# Origin API. Пусто: nginx отдаёт SPA и проксирует /api и /uploads на backend,
# а префикс /api/v1 клиент подставляет сам (frontend/src/api/client.ts).
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# --------------------------------------------------------------------- runtime
FROM nginx:alpine AS runtime

# Дефолтный конфиг заменяем своим (SPA fallback + прокси + gzip + кэш).
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# В busybox есть wget — отдельная зависимость не нужна.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --spider --tries=1 http://127.0.0.1/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
