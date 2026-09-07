/**
 * Денежные и весовые вычисления.
 *
 * Контракт (раздел 2) требует передавать Decimal строками, а раздел 6 —
 * округление ROUND_HALF_UP до 2 знаков. Поэтому ВСЕ вычисления идут в целых
 * числах: деньги — в копейках (scale 2), вес — в граммах (scale 3).
 * Ни одного промежуточного float.
 */

export const MONEY_SCALE = 2;
export const WEIGHT_SCALE = 3;

/** Неразрывный пробел — чтобы «890 ₽» не разрывалось переносом строки. */
export const NBSP = String.fromCharCode(160);

const DIGITS_RE = /^\d*$/;

/**
 * Разбирает decimal («890.00», «1,5», 12.5) в целое число с масштабом `scale`.
 * Дробная часть за пределами масштаба округляется ROUND_HALF_UP (от нуля).
 * Некорректный ввод даёт 0 — вызывающий код валидирует данные отдельно.
 */
export function parseScaled(value: string | number | null | undefined, scale: number): number {
  if (value === null || value === undefined) return 0;

  let raw: string;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 0;
    // toFixed убирает экспоненциальную запись и лишний «хвост» double.
    raw = value.toFixed(Math.min(scale + 4, 20));
  } else {
    raw = value.trim().replace(',', '.');
  }

  if (raw === '') return 0;

  let sign = 1;
  if (raw.startsWith('-')) {
    sign = -1;
    raw = raw.slice(1);
  } else if (raw.startsWith('+')) {
    raw = raw.slice(1);
  }

  const dot = raw.indexOf('.');
  const intPart = dot === -1 ? raw : raw.slice(0, dot);
  const fracPart = dot === -1 ? '' : raw.slice(dot + 1);

  if (!DIGITS_RE.test(intPart) || !DIGITS_RE.test(fracPart)) return 0;
  if (intPart === '' && fracPart === '') return 0;

  const kept = fracPart.slice(0, scale).padEnd(scale, '0');
  const nextDigit = fracPart.charAt(scale);

  const units = intPart === '' ? 0 : Number(intPart);
  let scaled = units * 10 ** scale + (kept === '' ? 0 : Number(kept));
  if (nextDigit !== '' && Number(nextDigit) >= 5) {
    scaled += 1;
  }
  return sign * scaled;
}

/** Обратное преобразование: целое с масштабом → каноническая строка «1780.00». */
export function fromScaled(scaled: number, scale: number): string {
  const sign = scaled < 0 ? '-' : '';
  const abs = Math.abs(Math.trunc(scaled)).toString().padStart(scale + 1, '0');
  const intPart = abs.slice(0, abs.length - scale);
  const fracPart = scale > 0 ? '.' + abs.slice(abs.length - scale) : '';
  return sign + intPart + fracPart;
}

/** Деление с округлением ROUND_HALF_UP (от нуля). */
function divRoundHalfUp(numerator: number, denominator: number): number {
  const sign = numerator < 0 ? -1 : 1;
  const abs = Math.abs(numerator);
  return sign * Math.floor((abs + Math.floor(denominator / 2)) / denominator);
}

/** Деньги → копейки. */
export function toKopecks(value: string | number | null | undefined): number {
  return parseScaled(value, MONEY_SCALE);
}

/** Вес → граммы. */
export function toGrams(value: string | number | null | undefined): number {
  return parseScaled(value, WEIGHT_SCALE);
}

/** Число из decimal-строки. Использовать только для отображения/сравнения. */
export function toNumber(value: string | number | null | undefined): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (value === null || value === undefined) return 0;
  const parsed = Number(String(value).trim().replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Каноническая денежная строка для отправки на бэкенд: «890.00». */
export function toMoneyString(value: string | number | null | undefined): string {
  return fromScaled(toKopecks(value), MONEY_SCALE);
}

/** Каноническая весовая строка для отправки на бэкенд: «1.500». */
export function toWeightString(value: string | number | null | undefined): string {
  return fromScaled(toGrams(value), WEIGHT_SCALE);
}

function groupDigits(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
}

/** «890 ₽», «1 780,50 ₽» */
export function formatPrice(value: string | number | null | undefined): string {
  const kopecks = toKopecks(value);
  const sign = kopecks < 0 ? '-' : '';
  const abs = Math.abs(kopecks);
  const rubles = groupDigits(Math.floor(abs / 100).toString());
  const cents = abs % 100;
  const body = cents === 0 ? rubles : rubles + ',' + cents.toString().padStart(2, '0');
  return sign + body + NBSP + '₽';
}

/** «890 ₽/кг» */
export function formatPricePerKg(value: string | number | null | undefined): string {
  return formatPrice(value) + '/кг';
}

/** «1,5 кг», «2 кг», «0,25 кг» */
export function formatWeight(value: string | number | null | undefined): string {
  return formatWeightInput(value) + NBSP + 'кг';
}

/** Вес для поля ввода: «1,5» (без единиц). */
export function formatWeightInput(value: string | number | null | undefined): string {
  const grams = toGrams(value);
  const sign = grams < 0 ? '-' : '';
  const abs = Math.abs(grams);
  const whole = groupDigits(Math.floor(abs / 1000).toString());
  const frac = (abs % 1000).toString().padStart(3, '0').replace(/0+$/, '');
  const body = frac === '' ? whole : whole + ',' + frac;
  return sign + body;
}

/**
 * Стоимость позиции: round_money(weight_kg * price_per_kg), ROUND_HALF_UP.
 * Возвращает каноническую строку «1780.00» (раздел 6.2 контракта).
 */
export function calcLineTotal(
  weightKg: string | number | null | undefined,
  pricePerKg: string | number | null | undefined,
): string {
  return fromScaled(calcLineTotalKopecks(weightKg, pricePerKg), MONEY_SCALE);
}

/** То же самое, но в копейках — для суммирования без потерь. */
export function calcLineTotalKopecks(
  weightKg: string | number | null | undefined,
  pricePerKg: string | number | null | undefined,
): number {
  const grams = toGrams(weightKg); // вес × 1000
  const kopecksPerKg = toKopecks(pricePerKg); // цена × 100
  // grams * kopecksPerKg = (итог в копейках) × 1000
  return divRoundHalfUp(grams * kopecksPerKg, 1000);
}

export interface CartTotalItem {
  weightKg: string | number;
  pricePerKg: string | number;
}

export interface CartTotals {
  /** Стоимость товаров, «1780.00» */
  subtotal: string;
  /** Стоимость доставки, «300.00» */
  deliveryPrice: string;
  /** ИТОГО, «2080.00» */
  total: string;
}

/**
 * Итог корзины: subtotal = Σ line_total, total = subtotal + delivery_price.
 * Для самовывоза передавать deliveryPrice = 0 / «0.00» (раздел 6.3).
 */
export function calcCartTotal(
  items: readonly CartTotalItem[],
  deliveryPrice: string | number | null | undefined = 0,
): CartTotals {
  const subtotalKopecks = items.reduce(
    (acc, item) => acc + calcLineTotalKopecks(item.weightKg, item.pricePerKg),
    0,
  );
  const deliveryKopecks = toKopecks(deliveryPrice);
  return {
    subtotal: fromScaled(subtotalKopecks, MONEY_SCALE),
    deliveryPrice: fromScaled(deliveryKopecks, MONEY_SCALE),
    total: fromScaled(subtotalKopecks + deliveryKopecks, MONEY_SCALE),
  };
}

/** Минимальный вес по умолчанию (раздел 6.4) — 0.100 кг. */
export const DEFAULT_MIN_WEIGHT = '0.100';
/** Шаг веса по умолчанию — 0.100 кг. */
export const DEFAULT_WEIGHT_STEP = '0.100';

/**
 * Приводит вес к допустимому диапазону: не меньше min, не больше max (остатка),
 * квантование до 3 знаков. Возвращает каноническую строку.
 */
export function clampWeight(
  value: string | number | null | undefined,
  options: { min?: string | number; max?: string | number } = {},
): string {
  const minGrams = toGrams(options.min ?? DEFAULT_MIN_WEIGHT);
  const maxGrams = options.max === undefined || options.max === null ? null : toGrams(options.max);
  let grams = toGrams(value);

  if (maxGrams !== null && maxGrams < minGrams) {
    // Остаток меньше минимального веса — товар фактически недоступен.
    return fromScaled(Math.max(maxGrams, 0), WEIGHT_SCALE);
  }
  if (grams < minGrams) grams = minGrams;
  if (maxGrams !== null && grams > maxGrams) grams = maxGrams;
  return fromScaled(grams, WEIGHT_SCALE);
}

/** Изменение веса кнопками −/+ с шагом (по умолчанию 0,1 кг). */
export function stepWeight(
  value: string | number | null | undefined,
  direction: 1 | -1,
  options: { min?: string | number; max?: string | number; step?: string | number } = {},
): string {
  const stepGrams = toGrams(options.step ?? DEFAULT_WEIGHT_STEP) || 100;
  const next = toGrams(value) + direction * stepGrams;
  return clampWeight(fromScaled(next, WEIGHT_SCALE), options);
}

/** Сравнение весов без float: a > b. */
export function isWeightGreater(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
): boolean {
  return toGrams(a) > toGrams(b);
}

/** Есть ли остаток, достаточный для минимального заказа. */
export function hasSellableStock(
  stockKg: string | number | null | undefined,
  minWeight: string | number = DEFAULT_MIN_WEIGHT,
): boolean {
  return toGrams(stockKg) >= toGrams(minWeight);
}
