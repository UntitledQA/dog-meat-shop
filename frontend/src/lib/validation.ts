/**
 * Валидация формы оформления заказа.
 * Все сообщения — на русском, ключи совпадают с именами полей формы.
 */

import type { DeliveryType, ProductCategory } from '../api/types';

export interface CheckoutFormValues {
  customerName: string;
  phone: string;
  deliveryType: DeliveryType;
  address: string;
  deliveryDate: string;
  comment: string;
}

export type CheckoutErrors = Record<string, string>;

export const NAME_MIN_LENGTH = 2;
export const NAME_MAX_LENGTH = 100;
export const COMMENT_MAX_LENGTH = 500;
/** Совпадает с ограничением бэкенда: OrderCreate.address — max_length=512. */
export const ADDRESS_MAX_LENGTH = 512;

/**
 * Нормализация российского телефона к формату +7XXXXXXXXXX.
 * Принимает «8 999 123-45-67», «+7 (999) 1234567», «9991234567».
 * Возвращает пустую строку, если номер не распознан.
 */
export function normalizePhone(raw: string): string {
  const digits = (raw ?? '').replace(/\D/g, '');
  if (digits === '') return '';

  let national = digits;
  if (digits.length === 11 && (digits.startsWith('7') || digits.startsWith('8'))) {
    national = digits.slice(1);
  } else if (digits.length === 10) {
    national = digits;
  } else {
    return '';
  }

  // Российские мобильные и городские коды не начинаются с 0 и 1.
  if (!/^[3-9]\d{9}$/.test(national)) return '';
  return '+7' + national;
}

/** Проверка телефона без нормализации результата. */
export function isValidPhone(raw: string): boolean {
  return normalizePhone(raw) !== '';
}

/** Маска для отображения: +7 (999) 123-45-67 */
export function formatPhone(raw: string): string {
  const normalized = normalizePhone(raw);
  if (normalized === '') return raw;
  const d = normalized.slice(2);
  return '+7 (' + d.slice(0, 3) + ') ' + d.slice(3, 6) + '-' + d.slice(6, 8) + '-' + d.slice(8, 10);
}

/** Сегодняшняя дата в формате YYYY-MM-DD по локальному времени пользователя. */
export function todayIsoDate(now: Date = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return year + '-' + month + '-' + day;
}

/** Дата в прошлом? Сравнение строк YYYY-MM-DD корректно лексикографически. */
export function isPastDate(value: string, now: Date = new Date()): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  return value < todayIsoDate(now);
}

/**
 * Валидация формы оформления.
 * Адрес обязателен ТОЛЬКО при доставке (раздел «Оформление» ТЗ).
 */
export function validateCheckout(
  values: CheckoutFormValues,
  options: { now?: Date } = {},
): CheckoutErrors {
  const errors: CheckoutErrors = {};
  const now = options.now ?? new Date();

  const name = (values.customerName ?? '').trim();
  if (name === '') {
    errors.customerName = 'Укажите имя';
  } else if (name.length < NAME_MIN_LENGTH) {
    errors.customerName = 'Имя должно содержать минимум ' + NAME_MIN_LENGTH + ' символа';
  } else if (name.length > NAME_MAX_LENGTH) {
    errors.customerName = 'Имя не длиннее ' + NAME_MAX_LENGTH + ' символов';
  }

  const phone = (values.phone ?? '').trim();
  if (phone === '') {
    errors.phone = 'Укажите телефон';
  } else if (!isValidPhone(phone)) {
    errors.phone = 'Введите телефон в формате +7 999 123-45-67';
  }

  if (values.deliveryType !== 'delivery' && values.deliveryType !== 'pickup') {
    errors.deliveryType = 'Выберите способ получения';
  }

  const address = (values.address ?? '').trim();
  if (values.deliveryType === 'delivery') {
    if (address === '') {
      errors.address = 'Укажите адрес доставки';
    } else if (address.length < 5) {
      errors.address = 'Адрес слишком короткий — укажите улицу и дом';
    } else if (address.length > ADDRESS_MAX_LENGTH) {
      errors.address = 'Адрес не длиннее ' + ADDRESS_MAX_LENGTH + ' символов';
    }
  }

  const date = (values.deliveryDate ?? '').trim();
  if (date === '') {
    errors.deliveryDate = 'Выберите дату';
  } else if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    errors.deliveryDate = 'Некорректная дата';
  } else if (isPastDate(date, now)) {
    errors.deliveryDate = 'Дата не может быть в прошлом';
  }

  const comment = values.comment ?? '';
  if (comment.length > COMMENT_MAX_LENGTH) {
    errors.comment = 'Комментарий не длиннее ' + COMMENT_MAX_LENGTH + ' символов';
  }

  return errors;
}

export interface ProductFormValues {
  name: string;
  description: string;
  /** Пустая строка — «без категории» (в payload уходит как null). */
  category: ProductCategory | '';
  pricePerKg: string;
  stockKg: string;
  photoUrl: string;
  isActive: boolean;
}

const DECIMAL_INPUT_RE = /^\d+([.,]\d+)?$/;

/** Валидация админской формы товара. */
export function validateProductForm(values: ProductFormValues): CheckoutErrors {
  const errors: CheckoutErrors = {};

  const name = (values.name ?? '').trim();
  if (name === '') {
    errors.name = 'Укажите название';
  } else if (name.length < 2) {
    errors.name = 'Название должно содержать минимум 2 символа';
  } else if (name.length > 200) {
    errors.name = 'Название не длиннее 200 символов';
  }

  const price = (values.pricePerKg ?? '').trim();
  if (price === '') {
    errors.pricePerKg = 'Укажите цену за килограмм';
  } else if (!DECIMAL_INPUT_RE.test(price)) {
    errors.pricePerKg = 'Цена — число, например 890 или 890.50';
  } else if (Number(price.replace(',', '.')) <= 0) {
    errors.pricePerKg = 'Цена должна быть больше нуля';
  }

  const stock = (values.stockKg ?? '').trim();
  if (stock === '') {
    errors.stockKg = 'Укажите остаток в килограммах';
  } else if (!DECIMAL_INPUT_RE.test(stock)) {
    errors.stockKg = 'Остаток — число, например 12.5';
  } else if (Number(stock.replace(',', '.')) < 0) {
    errors.stockKg = 'Остаток не может быть отрицательным';
  }

  if ((values.description ?? '').length > 2000) {
    errors.description = 'Описание не длиннее 2000 символов';
  }

  return errors;
}

/** Есть ли хотя бы одна ошибка. */
export function hasErrors(errors: CheckoutErrors): boolean {
  return Object.keys(errors).length > 0;
}
