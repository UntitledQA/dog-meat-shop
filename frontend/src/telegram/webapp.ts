/**
 * Безопасная обёртка над Telegram.WebApp.
 *
 * Каждая функция работает и вне Telegram: приложение должно открываться
 * в обычном браузере во время разработки. Там, где Telegram недоступен,
 * используются нативные аналоги (confirm/alert) или no-op.
 */

import type {
  HapticImpactStyle,
  HapticNotificationType,
  TelegramThemeParams,
  TelegramWebApp,
} from './types';

/** Возвращает WebApp, если скрипт Telegram загрузился и мы внутри Telegram. */
export function getWebApp(): TelegramWebApp | null {
  if (typeof window === 'undefined') return null;
  const app = window.Telegram?.WebApp;
  if (!app) return null;
  return app;
}

/** Запущены ли мы реально внутри Telegram (есть подписанный initData). */
export function isTelegramEnvironment(): boolean {
  const app = getWebApp();
  return Boolean(app && typeof app.initData === 'string' && app.initData.length > 0);
}

/** Сырой initData для заголовка X-Telegram-Init-Data. */
export function getInitData(): string {
  const app = getWebApp();
  return app?.initData ?? '';
}

/** Telegram-id текущего пользователя (только для подсказок в UI). */
export function getTelegramUserId(): number | null {
  return getWebApp()?.initDataUnsafe?.user?.id ?? null;
}

/** Имя пользователя из initDataUnsafe — подставляем в форму заказа. */
export function getTelegramUserName(): string {
  const user = getWebApp()?.initDataUnsafe?.user;
  if (!user) return '';
  return [user.first_name, user.last_name].filter(Boolean).join(' ').trim();
}

/** Сообщает Telegram, что интерфейс готов, и разворачивает окно. */
export function ready(): void {
  const app = getWebApp();
  if (!app) return;
  try {
    app.ready();
  } catch (error) {
    console.warn('Telegram.WebApp.ready() недоступен', error);
  }
}

export function expand(): void {
  const app = getWebApp();
  if (!app) return;
  try {
    app.expand();
  } catch (error) {
    console.warn('Telegram.WebApp.expand() недоступен', error);
  }
}

export function close(): void {
  const app = getWebApp();
  if (!app) return;
  try {
    app.close();
  } catch (error) {
    console.warn('Telegram.WebApp.close() недоступен', error);
  }
}

/** Параметры темы Telegram (пустой объект вне Telegram). */
export function themeParams(): TelegramThemeParams {
  return getWebApp()?.themeParams ?? {};
}

/** 'light' | 'dark' — вне Telegram определяем по системной теме. */
export function colorScheme(): 'light' | 'dark' {
  const app = getWebApp();
  if (app?.colorScheme) return app.colorScheme;
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

/** Подписка на событие Telegram. Возвращает функцию отписки. */
export function onEvent(eventType: string, handler: () => void): () => void {
  const app = getWebApp();
  if (!app) return () => undefined;
  app.onEvent(eventType, handler);
  return () => app.offEvent(eventType, handler);
}

/* ------------------------------- MainButton ------------------------------- */

export interface MainButtonOptions {
  text: string;
  visible?: boolean;
  enabled?: boolean;
  progress?: boolean;
  onClick?: () => void;
}

/** Управление главной кнопкой Telegram. Вне Telegram — no-op. */
export const mainButton = {
  isAvailable(): boolean {
    return Boolean(getWebApp()?.MainButton);
  },
  show(options: MainButtonOptions): () => void {
    const button = getWebApp()?.MainButton;
    if (!button) return () => undefined;
    button.setText(options.text);
    if (options.enabled === false) button.disable();
    else button.enable();
    if (options.progress) button.showProgress(true);
    else button.hideProgress();
    if (options.visible === false) button.hide();
    else button.show();

    const handler = options.onClick;
    if (handler) button.onClick(handler);
    return () => {
      if (handler) button.offClick(handler);
      button.hideProgress();
      button.hide();
    };
  },
  hide(): void {
    getWebApp()?.MainButton?.hide();
  },
};

/* ------------------------------- BackButton ------------------------------- */

/** Показывает системную кнопку «Назад». Возвращает функцию скрытия. */
export function showBackButton(onClick: () => void): () => void {
  const button = getWebApp()?.BackButton;
  if (!button) return () => undefined;
  button.onClick(onClick);
  button.show();
  return () => {
    button.offClick(onClick);
    button.hide();
  };
}

/* ----------------------------- HapticFeedback ----------------------------- */

export const haptic = {
  impact(style: HapticImpactStyle = 'light'): void {
    getWebApp()?.HapticFeedback?.impactOccurred(style);
  },
  notification(type: HapticNotificationType): void {
    getWebApp()?.HapticFeedback?.notificationOccurred(type);
  },
  selection(): void {
    getWebApp()?.HapticFeedback?.selectionChanged();
  },
};

/* --------------------------------- Диалоги -------------------------------- */

/** Подтверждение действия. Вне Telegram — window.confirm. */
export function showConfirm(message: string): Promise<boolean> {
  const app = getWebApp();
  if (app && typeof app.showConfirm === 'function') {
    return new Promise<boolean>((resolve) => {
      try {
        app.showConfirm(message, (confirmed) => resolve(Boolean(confirmed)));
      } catch {
        resolve(fallbackConfirm(message));
      }
    });
  }
  return Promise.resolve(fallbackConfirm(message));
}

function fallbackConfirm(message: string): boolean {
  if (typeof window === 'undefined' || typeof window.confirm !== 'function') return true;
  return window.confirm(message);
}

/** Сообщение пользователю. Вне Telegram — window.alert. */
export function showAlert(message: string): void {
  const app = getWebApp();
  if (app && typeof app.showAlert === 'function') {
    try {
      app.showAlert(message);
      return;
    } catch (error) {
      console.warn('Telegram.WebApp.showAlert() недоступен', error);
    }
  }
  if (typeof window !== 'undefined' && typeof window.alert === 'function') {
    window.alert(message);
  }
}

/** Инициализация при старте приложения. */
export function initTelegram(): void {
  ready();
  expand();
}
