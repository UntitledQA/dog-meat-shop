import { describe, expect, it } from 'vitest';

import { ORDER_STATUSES, allowedTransitions, statusLabel, statusModifier } from './orderStatus';

describe('статусы заказа', () => {
  it('набор статусов — только подтверждён, доставляется, готово и отменён', () => {
    expect(ORDER_STATUSES).toEqual(['confirmed', 'delivering', 'completed', 'cancelled']);
  });

  it('подписи на русском, completed — «Готово»', () => {
    expect(statusLabel('confirmed')).toBe('Подтверждён');
    expect(statusLabel('delivering')).toBe('Доставляется');
    expect(statusLabel('completed')).toBe('Готово');
    expect(statusLabel('cancelled')).toBe('Отменён');
  });

  it('подпись с бэкенда важнее локальной', () => {
    expect(statusLabel('completed', 'Выдан')).toBe('Выдан');
    expect(statusLabel('completed', '   ')).toBe('Готово');
  });

  it('модификатор бейджа строится по значению статуса', () => {
    expect(statusModifier('delivering')).toBe('badge--delivering');
  });
});

describe('переходы статусов', () => {
  it('самовывозу «Доставляется» не предлагается', () => {
    const next = allowedTransitions('confirmed', 'pickup');
    expect(next).not.toContain('delivering');
    expect(next).toEqual(['completed', 'cancelled']);
  });

  it('доставке предлагается и «Доставляется», и сразу «Готово»', () => {
    expect(allowedTransitions('confirmed', 'delivery')).toEqual([
      'delivering',
      'completed',
      'cancelled',
    ]);
  });

  it('из «Доставляется» — только в «Готово» или отмену', () => {
    expect(allowedTransitions('delivering', 'delivery')).toEqual(['completed', 'cancelled']);
  });

  it('готовый и отменённый заказ — терминальные, отмена больше не предлагается', () => {
    expect(allowedTransitions('completed', 'delivery')).toEqual([]);
    expect(allowedTransitions('completed', 'pickup')).toEqual([]);
    expect(allowedTransitions('cancelled', 'delivery')).toEqual([]);
  });

  it('отмена доступна из любого нетерминального статуса', () => {
    expect(allowedTransitions('confirmed', 'pickup')).toContain('cancelled');
    expect(allowedTransitions('confirmed', 'delivery')).toContain('cancelled');
    expect(allowedTransitions('delivering', 'delivery')).toContain('cancelled');
  });
});
