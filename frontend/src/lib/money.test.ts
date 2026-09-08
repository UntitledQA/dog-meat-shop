import { describe, expect, it } from 'vitest';
import {
  DEFAULT_MIN_WEIGHT,
  NBSP,
  calcCartTotal,
  calcLineTotal,
  clampWeight,
  formatPrice,
  formatWeight,
  hasSellableStock,
  stepWeight,
  toWeightString,
} from './money';

describe('calcLineTotal — стоимость позиции', () => {
  it('умножает вес на цену за килограмм', () => {
    expect(calcLineTotal('2.000', '890.00')).toBe('1780.00');
    expect(calcLineTotal('1.500', '890.00')).toBe('1335.00');
  });

  it('работает на минимальном весе 0,1 кг', () => {
    expect(calcLineTotal('0.100', '890.00')).toBe('89.00');
    expect(calcLineTotal(DEFAULT_MIN_WEIGHT, '99.90')).toBe('9.99');
  });

  it('округляет копейки ROUND_HALF_UP', () => {
    // 0.101 кг × 55.00 = 5.555 → 5.56
    expect(calcLineTotal('0.101', '55.00')).toBe('5.56');
    // 0.335 кг × 99.99 = 33.49665 → 33.50
    expect(calcLineTotal('0.335', '99.99')).toBe('33.50');
    // 0.105 кг × 10.00 = 1.05 — ровное значение не «уплывает»
    expect(calcLineTotal('0.105', '10.00')).toBe('1.05');
  });

  it('принимает дробные значения с запятой и числа', () => {
    expect(calcLineTotal('1,5', '890')).toBe('1335.00');
    expect(calcLineTotal(0.25, 1000)).toBe('250.00');
  });

  it('даёт 0.00 на нулевом весе или цене', () => {
    expect(calcLineTotal('0', '890.00')).toBe('0.00');
    expect(calcLineTotal('1.000', '0')).toBe('0.00');
  });

  it('не теряет точность на больших весах', () => {
    expect(calcLineTotal('12.345', '1234.56')).toBe('15240.64');
  });
});

describe('calcCartTotal — итог корзины', () => {
  const items = [
    { weightKg: '0.500', pricePerKg: '890.00' }, // 445.00
    { weightKg: '1.200', pricePerKg: '450.00' }, // 540.00
  ];

  it('складывает позиции и добавляет доставку', () => {
    const totals = calcCartTotal(items, '300.00');
    expect(totals.subtotal).toBe('985.00');
    expect(totals.deliveryPrice).toBe('300.00');
    expect(totals.total).toBe('1285.00');
  });

  it('при самовывозе доставка равна нулю', () => {
    const totals = calcCartTotal(items, 0);
    expect(totals.deliveryPrice).toBe('0.00');
    expect(totals.total).toBe(totals.subtotal);
    expect(totals.total).toBe('985.00');
  });

  it('суммирует округлённые позиции, а не округляет сумму', () => {
    // Каждая позиция округляется отдельно: 5.56 + 5.56 = 11.12
    const totals = calcCartTotal(
      [
        { weightKg: '0.101', pricePerKg: '55.00' },
        { weightKg: '0.101', pricePerKg: '55.00' },
      ],
      0,
    );
    expect(totals.subtotal).toBe('11.12');
  });

  it('пустая корзина — нули', () => {
    const totals = calcCartTotal([], '300.00');
    expect(totals.subtotal).toBe('0.00');
    expect(totals.total).toBe('300.00');
  });
});

describe('вес: границы и шаг', () => {
  it('не опускается ниже минимума и не превышает остаток', () => {
    expect(clampWeight('0.050', { min: '0.100', max: '5.000' })).toBe('0.100');
    expect(clampWeight('9.000', { min: '0.100', max: '5.000' })).toBe('5.000');
    expect(clampWeight('2.5', { min: '0.100', max: '5.000' })).toBe('2.500');
  });

  it('шаг 0,1 кг упирается в остаток', () => {
    expect(stepWeight('1.000', 1, { min: '0.100', max: '5.000' })).toBe('1.100');
    expect(stepWeight('1.000', -1, { min: '0.100', max: '5.000' })).toBe('0.900');
    expect(stepWeight('0.100', -1, { min: '0.100', max: '5.000' })).toBe('0.100');
    expect(stepWeight('5.000', 1, { min: '0.100', max: '5.000' })).toBe('5.000');
  });

  it('остаток меньше минимального веса считается непродаваемым', () => {
    expect(hasSellableStock('0.050')).toBe(false);
    expect(hasSellableStock('0.100')).toBe(true);
    expect(hasSellableStock('0.000')).toBe(false);
  });

  it('канонизирует вес для отправки на бэкенд', () => {
    expect(toWeightString('1,5')).toBe('1.500');
    expect(toWeightString(2)).toBe('2.000');
  });
});

describe('форматирование', () => {
  it('печатает деньги с рублями и копейками', () => {
    expect(formatPrice('890.00')).toBe('890' + NBSP + '₽');
    expect(formatPrice('1780.50')).toBe('1' + NBSP + '780,50' + NBSP + '₽');
  });

  it('печатает вес без лишних нулей', () => {
    expect(formatWeight('1.500')).toBe('1,5' + NBSP + 'кг');
    expect(formatWeight('2.000')).toBe('2' + NBSP + 'кг');
    expect(formatWeight('0.100')).toBe('0,1' + NBSP + 'кг');
  });
});
