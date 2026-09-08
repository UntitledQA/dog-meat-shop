import { describe, expect, it } from 'vitest';
import { API_PREFIX, normalizeBaseUrl } from './client';

describe('normalizeBaseUrl', () => {
  it('пустое значение означает тот же origin', () => {
    expect(normalizeBaseUrl('')).toBe('');
    expect(normalizeBaseUrl(undefined)).toBe('');
    expect(normalizeBaseUrl(null)).toBe('');
    expect(normalizeBaseUrl('   ')).toBe('');
  });

  it('срезает завершающие слэши', () => {
    expect(normalizeBaseUrl('https://api.example.com/')).toBe('https://api.example.com');
    expect(normalizeBaseUrl('https://api.example.com///')).toBe('https://api.example.com');
  });

  it('оставляет origin без префикса как есть', () => {
    expect(normalizeBaseUrl('https://api.example.com')).toBe('https://api.example.com');
  });

  // Регрессия: из-за /api/v1 в VITE_API_BASE_URL адреса превращались
  // в /api/v1/api/v1/catalog и весь SPA получал 404 в Docker-сборке.
  it('срезает ошибочно указанный префикс /api/v1', () => {
    expect(normalizeBaseUrl('/api/v1')).toBe('');
    expect(normalizeBaseUrl('/api/v1/')).toBe('');
    expect(normalizeBaseUrl('https://api.example.com/api/v1')).toBe('https://api.example.com');
  });

  it('итоговый адрес содержит префикс ровно один раз', () => {
    for (const configured of ['', '/api/v1', 'https://api.example.com/api/v1']) {
      const url = normalizeBaseUrl(configured) + API_PREFIX + '/catalog';
      expect(url.match(/\/api\/v1/g)).toHaveLength(1);
      expect(url.endsWith('/api/v1/catalog')).toBe(true);
    }
  });
});
