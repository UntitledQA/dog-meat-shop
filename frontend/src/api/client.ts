/**
 * Единственный HTTP-клиент приложения.
 *
 * — базовый URL берётся из VITE_API_BASE_URL (пусто → относительные пути + прокси Vite);
 * — заголовок авторизации X-Telegram-Init-Data (раздел 4 контракта);
 * — в dev вне Telegram — X-Dev-Telegram-Id из VITE_DEV_TELEGRAM_ID;
 * — единый формат ошибок { error: { code, message, details } } → ApiError.
 */

import { getInitData } from '../telegram/webapp';
import type { ApiErrorPayload, InsufficientStockItem } from './types';

/**
 * Базовый URL API — только origin. Пустая строка = тот же origin (dev-прокси Vite).
 *
 * Префикс `/api/v1` добавляет `API_PREFIX`, поэтому в `VITE_API_BASE_URL` его быть
 * не должно. Частая ошибка в конфигурации — записать туда `/api/v1` и получить
 * `/api/v1/api/v1/catalog`, поэтому лишний префикс здесь срезается принудительно.
 */
export function normalizeBaseUrl(raw: string | undefined | null): string {
  const trimmed = (raw ?? '').trim().replace(/\/+$/, '');
  return trimmed.replace(/\/api\/v1$/, '');
}

export const API_BASE_URL: string = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL);

/** Telegram-id для dev-режима без Telegram (бэкенд: DEV_AUTH_ENABLED=true). */
const DEV_TELEGRAM_ID: string = import.meta.env.VITE_DEV_TELEGRAM_ID ?? '';

export const API_PREFIX = '/api/v1';

/** Ошибка API в едином формате контракта. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(code: string, message: string, status: number, details: Record<string, unknown> = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }

  /** Нет сети / запрос не дошёл до сервера. */
  get isNetwork(): boolean {
    return this.code === 'network_error';
  }

  get isUnauthorized(): boolean {
    return this.status === 401 || this.code === 'unauthorized';
  }

  get isForbidden(): boolean {
    return this.status === 403 || this.code === 'forbidden';
  }

  get isNotFound(): boolean {
    return this.status === 404 || this.code === 'not_found';
  }

  /** Позиции, которых не хватило на складе. */
  get insufficientStockItems(): InsufficientStockItem[] {
    if (this.code !== 'insufficient_stock') return [];
    const items = this.details?.items;
    return Array.isArray(items) ? (items as InsufficientStockItem[]) : [];
  }
}

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  query?: Record<string, QueryValue>;
  body?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = API_BASE_URL + path;
  if (!query) return url;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    search.append(key, String(value));
  }
  const qs = search.toString();
  return qs ? url + '?' + qs : url;
}

function buildHeaders(hasJsonBody: boolean): Headers {
  const headers = new Headers();
  headers.set('Accept', 'application/json');
  if (hasJsonBody) headers.set('Content-Type', 'application/json');

  const initData = getInitData();
  if (initData) {
    headers.set('X-Telegram-Init-Data', initData);
  } else if (import.meta.env.DEV && DEV_TELEGRAM_ID) {
    // Только для локальной разработки вне Telegram.
    headers.set('X-Dev-Telegram-Id', DEV_TELEGRAM_ID);
  }
  return headers;
}

function isErrorPayload(value: unknown): value is ApiErrorPayload {
  if (typeof value !== 'object' || value === null) return false;
  const error = (value as { error?: unknown }).error;
  if (typeof error !== 'object' || error === null) return false;
  return typeof (error as { code?: unknown }).code === 'string';
}

const STATUS_FALLBACK_MESSAGES: Record<number, string> = {
  400: 'Некорректный запрос. Проверьте данные.',
  401: 'Не удалось авторизоваться. Откройте приложение через Telegram.',
  403: 'Недостаточно прав для этого действия.',
  404: 'Запрошенные данные не найдены.',
  409: 'Данные изменились. Обновите страницу и попробуйте снова.',
  413: 'Файл слишком большой.',
  415: 'Неподдерживаемый формат файла. Нужен JPEG, PNG или WebP.',
  422: 'Проверьте правильность заполнения полей.',
  429: 'Слишком много запросов. Подождите немного.',
};

function fallbackMessage(status: number): string {
  if (STATUS_FALLBACK_MESSAGES[status]) return STATUS_FALLBACK_MESSAGES[status];
  if (status >= 500) return 'Сервис временно недоступен. Попробуйте позже.';
  return 'Не удалось выполнить запрос. Попробуйте ещё раз.';
}

function fallbackCode(status: number): string {
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 429) return 'rate_limited';
  if (status >= 500) return 'internal_error';
  return 'bad_request';
}

async function toApiError(response: Response): Promise<ApiError> {
  let payload: unknown = null;
  try {
    const text = await response.text();
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }

  if (isErrorPayload(payload)) {
    const { code, message, details } = payload.error;
    const enriched: Record<string, unknown> = { ...(details ?? {}) };
    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After');
      if (retryAfter) enriched.retry_after = retryAfter;
    }
    return new ApiError(
      code,
      message && message.trim() !== '' ? message : fallbackMessage(response.status),
      response.status,
      enriched,
    );
  }

  const details: Record<string, unknown> = {};
  if (response.status === 429) {
    const retryAfter = response.headers.get('Retry-After');
    if (retryAfter) details.retry_after = retryAfter;
  }
  let message = fallbackMessage(response.status);
  if (response.status === 429) {
    const retryAfter = details.retry_after;
    if (typeof retryAfter === 'string') {
      message = 'Слишком много запросов. Повторите через ' + retryAfter + ' с.';
    }
  }
  return new ApiError(fallbackCode(response.status), message, response.status, details);
}

/** Низкоуровневый запрос. Все эндпоинты ходят только через него. */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', query, body, formData, signal } = options;
  const hasJsonBody = body !== undefined && formData === undefined;

  const headers = buildHeaders(hasJsonBody);

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: formData ?? (hasJsonBody ? JSON.stringify(body) : undefined),
      signal,
      credentials: 'same-origin',
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError('network_error', 'Нет соединения. Проверьте интернет', 0, {
      cause: error instanceof Error ? error.message : String(error),
    });
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (text === '') return undefined as T;

  try {
    return JSON.parse(text) as T;
  } catch {
    throw new ApiError('internal_error', 'Сервер вернул некорректный ответ.', response.status);
  }
}

/**
 * Абсолютный URL для файла из /uploads. Нужен, когда фронт и бэкенд
 * разнесены по разным доменам (VITE_API_BASE_URL задан).
 */
export function resolveAssetUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (/^(https?:)?\/\//.test(url) || url.startsWith('data:')) return url;
  const path = url.startsWith('/') ? url : '/' + url;
  return API_BASE_URL + path;
}

/** Человекочитаемый текст любой ошибки — для тостов и экранов ошибок. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return 'Что-то пошло не так. Попробуйте ещё раз.';
}
