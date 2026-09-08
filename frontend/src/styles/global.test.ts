import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Регрессия на прокрутку в Telegram Desktop.
 *
 * По спецификации CSS, если одна ось overflow не `visible`, вторая вычисляется
 * в `auto`. Поэтому `overflow-x: hidden` на html / body / #root молча делал их
 * scroll-контейнерами: сами они не прокручивались (высота росла по контенту),
 * но перехватывали колесо мыши и не пропускали его к вьюпорту — страница
 * двигалась только перетаскиванием полосы справа.
 *
 * Лечится `overflow-x: clip`: горизонтальная прокрутка так же запрещена, но
 * scroll-контейнер не создаётся. Здесь мы следим, чтобы правило не откатили.
 */

// Читаем исходник напрямую: важен именно текст стилей, а не результат сборки.
// Комментарии вырезаем, иначе упоминание правила в пояснении засчиталось бы
// за само правило.
const css = readFileSync(resolve(process.cwd(), 'src/styles/global.css'), 'utf8')
  .split('\r\n')
  .join('\n')
  .replace(/\/\*[\s\S]*?\*\//g, '');

/** Возвращает тело CSS-блока по его селектору. */
function block(selector: string): string {
  const start = css.indexOf(selector);
  expect(start, `селектор ${selector} не найден в global.css`).toBeGreaterThan(-1);
  const open = css.indexOf('{', start);
  const close = css.indexOf('}', open);
  return css.slice(open + 1, close);
}

const ROOT_SELECTORS = ['html,\nbody {', '#root {'];

describe('global.css: корневые элементы не должны быть scroll-контейнерами', () => {
  it.each(ROOT_SELECTORS)('%j использует overflow-x: clip', (selector) => {
    expect(block(selector)).toMatch(/overflow-x:\s*clip/);
  });

  it.each(ROOT_SELECTORS)('%j не оставляет hidden победившим значением', (selector) => {
    const values = [...block(selector).matchAll(/overflow-x:\s*([a-z]+)/g)].map((m) => m[1]);
    expect(values.length).toBeGreaterThan(0);
    // hidden допустим только как фолбэк ПЕРЕД clip: побеждает последнее правило.
    expect(values.at(-1)).toBe('clip');
  });

  it('overscroll-behavior не висит на body — это блокировало передачу колеса вьюпорту', () => {
    expect(block('html,\nbody {')).not.toMatch(/overscroll-behavior/);
  });

  it('высота считается от окна Telegram, а не от 100vh', () => {
    expect(block('#root {')).toMatch(/min-height:\s*var\(--tg-viewport\)/);
    expect(css).not.toMatch(/min-height:\s*100vh/);
    // Единственный оставшийся 100dvh — фолбэк самой переменной.
    expect(css.match(/100dvh/g) ?? []).toHaveLength(1);
  });

  it('вложенный второй «полный экран» у .app-shell убран', () => {
    expect(block('.app-shell {')).not.toMatch(/min-height/);
  });
});
