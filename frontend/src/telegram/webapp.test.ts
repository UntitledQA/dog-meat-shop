import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { disableVerticalSwipes, initTelegram, syncViewportHeight } from './webapp';

type Handler = () => void;

/** Минимальный мок Telegram.WebApp с управляемой высотой окна. */
function mockWebApp(overrides: Record<string, unknown> = {}) {
  const handlers: Record<string, Handler[]> = {};
  const app = {
    initData: '',
    initDataUnsafe: {},
    version: '7.7',
    platform: 'android',
    colorScheme: 'light',
    themeParams: {},
    isExpanded: false,
    viewportHeight: 500,
    viewportStableHeight: 520,
    ready: vi.fn(),
    expand: vi.fn(),
    close: vi.fn(),
    disableVerticalSwipes: vi.fn(),
    onEvent: vi.fn((event: string, handler: Handler) => {
      (handlers[event] ??= []).push(handler);
    }),
    offEvent: vi.fn((event: string, handler: Handler) => {
      handlers[event] = (handlers[event] ?? []).filter((h) => h !== handler);
    }),
    showAlert: vi.fn(),
    showConfirm: vi.fn(),
    ...overrides,
  };
  (window as unknown as { Telegram: unknown }).Telegram = { WebApp: app };
  return {
    app,
    fire: (event: string) => (handlers[event] ?? []).forEach((h) => h()),
  };
}

afterEach(() => {
  delete (window as unknown as { Telegram?: unknown }).Telegram;
  document.documentElement.style.removeProperty('--tg-viewport');
  vi.restoreAllMocks();
});

describe('disableVerticalSwipes', () => {
  it('снимает жест «смахнуть вниз, чтобы закрыть»', () => {
    const { app } = mockWebApp();

    disableVerticalSwipes();

    expect(app.disableVerticalSwipes).toHaveBeenCalledTimes(1);
  });

  it('не падает на старых клиентах без этого метода', () => {
    mockWebApp({ disableVerticalSwipes: undefined });

    expect(() => disableVerticalSwipes()).not.toThrow();
  });

  it('не падает вне Telegram', () => {
    expect(() => disableVerticalSwipes()).not.toThrow();
  });
});

describe('syncViewportHeight', () => {
  beforeEach(() => {
    document.documentElement.style.removeProperty('--tg-viewport');
  });

  it('прокидывает viewportStableHeight в CSS-переменную', () => {
    mockWebApp();

    syncViewportHeight();

    expect(document.documentElement.style.getPropertyValue('--tg-viewport')).toBe('520px');
  });

  it('обновляет высоту по событию viewportChanged', () => {
    const { app, fire } = mockWebApp();
    syncViewportHeight();

    app.viewportStableHeight = 640;
    fire('viewportChanged');

    expect(document.documentElement.style.getPropertyValue('--tg-viewport')).toBe('640px');
  });

  it('берёт viewportHeight, если stable-высота нулевая', () => {
    mockWebApp({ viewportStableHeight: 0, viewportHeight: 480 });

    syncViewportHeight();

    expect(document.documentElement.style.getPropertyValue('--tg-viewport')).toBe('480px');
  });

  it('вне Telegram оставляет CSS-фолбэк 100dvh', () => {
    syncViewportHeight();

    expect(document.documentElement.style.getPropertyValue('--tg-viewport')).toBe('');
  });

  it('отписка снимает обработчик', () => {
    const { app } = mockWebApp();

    const stop = syncViewportHeight();
    stop();

    expect(app.offEvent).toHaveBeenCalled();
  });
});

describe('initTelegram', () => {
  it('разворачивает окно и отключает свайпы', () => {
    const { app } = mockWebApp();

    initTelegram();

    expect(app.ready).toHaveBeenCalled();
    expect(app.expand).toHaveBeenCalled();
    expect(app.disableVerticalSwipes).toHaveBeenCalled();
    expect(document.documentElement.style.getPropertyValue('--tg-viewport')).toBe('520px');
  });

  it('вне Telegram отрабатывает без ошибок', () => {
    expect(() => initTelegram()).not.toThrow();
  });
});
