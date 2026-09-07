/**
 * Тема Telegram → CSS-переменные --tg-theme-*.
 *
 * Вне Telegram подставляются фолбэки для светлой и тёмной схемы, поэтому
 * приложение выглядит корректно и в обычном браузере.
 */

import { useEffect } from 'react';
import { colorScheme, onEvent, themeParams } from './webapp';
import type { TelegramThemeParams } from './types';

type ThemeVars = Record<string, string>;

const LIGHT_FALLBACK: ThemeVars = {
  '--tg-theme-bg-color': '#ffffff',
  '--tg-theme-text-color': '#1a1a1a',
  '--tg-theme-hint-color': '#8b8f96',
  '--tg-theme-link-color': '#2b7cd3',
  '--tg-theme-button-color': '#c0392b',
  '--tg-theme-button-text-color': '#ffffff',
  '--tg-theme-secondary-bg-color': '#f2f3f5',
  '--tg-theme-header-bg-color': '#ffffff',
  '--tg-theme-accent-text-color': '#c0392b',
  '--tg-theme-section-bg-color': '#ffffff',
  '--tg-theme-section-header-text-color': '#8b8f96',
  '--tg-theme-subtitle-text-color': '#8b8f96',
  '--tg-theme-destructive-text-color': '#d64545',
};

const DARK_FALLBACK: ThemeVars = {
  '--tg-theme-bg-color': '#17212b',
  '--tg-theme-text-color': '#f5f5f5',
  '--tg-theme-hint-color': '#8d9aa8',
  '--tg-theme-link-color': '#6ab3f3',
  '--tg-theme-button-color': '#e05a47',
  '--tg-theme-button-text-color': '#ffffff',
  '--tg-theme-secondary-bg-color': '#232e3c',
  '--tg-theme-header-bg-color': '#17212b',
  '--tg-theme-accent-text-color': '#e05a47',
  '--tg-theme-section-bg-color': '#1d2733',
  '--tg-theme-section-header-text-color': '#8d9aa8',
  '--tg-theme-subtitle-text-color': '#8d9aa8',
  '--tg-theme-destructive-text-color': '#ec6a5e',
};

const PARAM_TO_VAR: Record<keyof TelegramThemeParams, string> = {
  bg_color: '--tg-theme-bg-color',
  text_color: '--tg-theme-text-color',
  hint_color: '--tg-theme-hint-color',
  link_color: '--tg-theme-link-color',
  button_color: '--tg-theme-button-color',
  button_text_color: '--tg-theme-button-text-color',
  secondary_bg_color: '--tg-theme-secondary-bg-color',
  header_bg_color: '--tg-theme-header-bg-color',
  accent_text_color: '--tg-theme-accent-text-color',
  section_bg_color: '--tg-theme-section-bg-color',
  section_header_text_color: '--tg-theme-section-header-text-color',
  subtitle_text_color: '--tg-theme-subtitle-text-color',
  destructive_text_color: '--tg-theme-destructive-text-color',
};

const HEX_RE = /^#[0-9a-fA-F]{3,8}$/;

/** Записывает переменные темы в :root. Безопасно вызывать повторно. */
export function applyTelegramTheme(): void {
  if (typeof document === 'undefined') return;

  const scheme = colorScheme();
  const root = document.documentElement;
  root.setAttribute('data-color-scheme', scheme);

  const vars: ThemeVars = { ...(scheme === 'dark' ? DARK_FALLBACK : LIGHT_FALLBACK) };
  const params = themeParams() as Record<string, string | undefined>;

  for (const key of Object.keys(PARAM_TO_VAR) as (keyof TelegramThemeParams)[]) {
    const value = params[key];
    if (typeof value === 'string' && HEX_RE.test(value)) {
      vars[PARAM_TO_VAR[key]] = value;
    }
  }

  for (const [name, value] of Object.entries(vars)) {
    root.style.setProperty(name, value);
  }

  const themeColorMeta = document.querySelector('meta[name="theme-color"]');
  if (themeColorMeta) {
    themeColorMeta.setAttribute('content', vars['--tg-theme-bg-color']);
  }
}

/** Применяет тему и переподписывается на themeChanged / системную смену темы. */
export function useTelegramTheme(): void {
  useEffect(() => {
    applyTelegramTheme();

    const unsubscribe = onEvent('themeChanged', applyTelegramTheme);

    let media: MediaQueryList | null = null;
    const onSystemChange = () => applyTelegramTheme();
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      media = window.matchMedia('(prefers-color-scheme: dark)');
      if (typeof media.addEventListener === 'function') {
        media.addEventListener('change', onSystemChange);
      }
    }

    return () => {
      unsubscribe();
      if (media && typeof media.removeEventListener === 'function') {
        media.removeEventListener('change', onSystemChange);
      }
    };
  }, []);
}
