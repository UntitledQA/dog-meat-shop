import { describe, expect, it } from 'vitest';
import {
  hasErrors,
  isValidPhone,
  normalizePhone,
  validateCheckout,
  validateProductForm,
} from './validation';
import type { CheckoutFormValues, ProductFormValues } from './validation';

const NOW = new Date('2026-09-08T10:00:00');

function form(overrides: Partial<CheckoutFormValues> = {}): CheckoutFormValues {
  return {
    customerName: 'Иван',
    phone: '+79991234567',
    deliveryType: 'delivery',
    address: 'ул. Ленина, 1',
    deliveryDate: '2026-09-09',
    comment: '',
    ...overrides,
  };
}

describe('validateCheckout — адрес', () => {
  it('адрес обязателен при доставке', () => {
    const errors = validateCheckout(form({ deliveryType: 'delivery', address: '' }), { now: NOW });
    expect(errors.address).toBe('Укажите адрес доставки');
  });

  it('слишком короткий адрес при доставке отклоняется', () => {
    const errors = validateCheckout(form({ deliveryType: 'delivery', address: 'дом' }), {
      now: NOW,
    });
    expect(errors.address).toBeDefined();
  });

  it('адрес НЕ обязателен при самовывозе', () => {
    const errors = validateCheckout(form({ deliveryType: 'pickup', address: '' }), { now: NOW });
    expect(errors.address).toBeUndefined();
    expect(hasErrors(errors)).toBe(false);
  });

  it('корректная форма доставки не даёт ошибок', () => {
    expect(hasErrors(validateCheckout(form(), { now: NOW }))).toBe(false);
  });
});

describe('validateCheckout — имя и телефон', () => {
  it('пустое имя — ошибка', () => {
    const errors = validateCheckout(form({ customerName: '   ' }), { now: NOW });
    expect(errors.customerName).toBe('Укажите имя');
  });

  it('имя из одной буквы — ошибка', () => {
    const errors = validateCheckout(form({ customerName: 'И' }), { now: NOW });
    expect(errors.customerName).toBeDefined();
  });

  it('пустой телефон — ошибка', () => {
    const errors = validateCheckout(form({ phone: '' }), { now: NOW });
    expect(errors.phone).toBe('Укажите телефон');
  });

  it('непохожий на российский номер — ошибка', () => {
    expect(validateCheckout(form({ phone: '12345' }), { now: NOW }).phone).toBeDefined();
    expect(validateCheckout(form({ phone: '+7 199 123-45-67' }), { now: NOW }).phone).toBeDefined();
  });

  it('принимает разные записи одного номера', () => {
    for (const phone of ['8 999 123-45-67', '+7 (999) 1234567', '9991234567']) {
      expect(validateCheckout(form({ phone }), { now: NOW }).phone).toBeUndefined();
      expect(normalizePhone(phone)).toBe('+79991234567');
    }
    expect(isValidPhone('123')).toBe(false);
    expect(isValidPhone('+79991234567')).toBe(true);
  });
});

describe('validateCheckout — дата', () => {
  it('дата в прошлом — ошибка', () => {
    const errors = validateCheckout(form({ deliveryDate: '2026-09-07' }), { now: NOW });
    expect(errors.deliveryDate).toBe('Дата не может быть в прошлом');
  });

  it('сегодняшняя дата допустима', () => {
    const errors = validateCheckout(form({ deliveryDate: '2026-09-08' }), { now: NOW });
    expect(errors.deliveryDate).toBeUndefined();
  });
});

describe('validateProductForm — админская форма', () => {
  const base: ProductFormValues = {
    name: 'Говядина',
    description: '',
    category: '',
    pricePerKg: '890',
    stockKg: '12.5',
    photoUrl: '',
    isActive: true,
  };

  it('корректные значения проходят', () => {
    expect(hasErrors(validateProductForm(base))).toBe(false);
  });

  it('цена должна быть положительным числом', () => {
    expect(validateProductForm({ ...base, pricePerKg: '' }).pricePerKg).toBeDefined();
    expect(validateProductForm({ ...base, pricePerKg: '0' }).pricePerKg).toBeDefined();
    expect(validateProductForm({ ...base, pricePerKg: 'дорого' }).pricePerKg).toBeDefined();
  });

  it('остаток обязателен и должен быть числом', () => {
    expect(validateProductForm({ ...base, stockKg: '' }).stockKg).toBeDefined();
    expect(validateProductForm({ ...base, stockKg: 'нет' }).stockKg).toBeDefined();
    expect(validateProductForm({ ...base, stockKg: '0' }).stockKg).toBeUndefined();
  });
});
