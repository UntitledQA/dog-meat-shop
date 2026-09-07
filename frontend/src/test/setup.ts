/**
 * Глобальная настройка тестов (подключается из vite.config.ts → test.setupFiles).
 * Добавляет матчеры @testing-library/jest-dom и чистит DOM между тестами.
 */

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

/** localStorage в jsdom общий на весь файл — чистим, чтобы стор корзины не «протекал». */
beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
