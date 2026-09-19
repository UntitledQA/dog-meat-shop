/** Категории товаров: список, подписи, хелперы. Slug'и — из раздела 5 контракта. */

import type { ProductCategory } from '../api/types';

/** Все категории в порядке отображения (совпадает с backend ProductCategory). */
export const PRODUCT_CATEGORIES: ProductCategory[] = [
  'beef',
  'veal',
  'horse-meat',
  'duck',
  'fish',
  'dried-treats',
];

const LABELS: Record<ProductCategory, string> = {
  'beef': 'Говядина',
  'veal': 'Телятина',
  'horse-meat': 'Конина',
  'duck': 'Утка',
  'fish': 'Рыба',
  'dried-treats': 'Сушёные лакомства',
};

/**
 * Подпись категории. Для `null`/`undefined` (товар без категории) — «Без категории»;
 * для неизвестного slug — сам slug (страховка на случай рассинхрона с бэкендом).
 */
export function categoryLabel(category: ProductCategory | null | undefined): string {
  if (!category) return 'Без категории';
  return LABELS[category] ?? category;
}

/** Проверяет, что строка — валидный slug категории (например, из `?category=` в URL). */
export function isProductCategory(value: unknown): value is ProductCategory {
  return typeof value === 'string' && (PRODUCT_CATEGORIES as string[]).includes(value);
}
