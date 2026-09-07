/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Базовый URL API. Пусто → относительные пути (dev-прокси Vite / один домен). */
  readonly VITE_API_BASE_URL?: string;
  /** Telegram-id для локальной разработки вне Telegram (заголовок X-Dev-Telegram-Id). */
  readonly VITE_DEV_TELEGRAM_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
