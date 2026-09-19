/**
 * Условия доставки и график работы магазина.
 *
 * Данные бизнес-постоянные: с бэкенда они не приходят и меняются вместе с кодом.
 * Единственное исключение — адрес самовывоза: он настраивается администратором
 * и приходит в `settings.pickup_address`, поэтому здесь его нет.
 *
 * В текстах только живые символы Unicode — никаких HTML-сущностей.
 */

/** Строка условий доставки: подпись слева, значение справа. */
export interface DeliveryTerm {
  label: string;
  value: string;
}

/** Как именно доставляем: своим курьером и через inDrive. */
export const DELIVERY_TERMS: readonly DeliveryTerm[] = [
  { label: 'Свой курьер', value: 'с 18:30 до 22:00' },
  { label: 'Нужно раньше 18:30', value: 'отправляем через inDrive' },
];

/** Часы работы в рабочий день. */
export const WORK_HOURS = 'с 10:00 до 18:00';

/** Обозначение выходного дня. */
export const DAY_OFF = 'выходной';

/** День недели в графике работы. */
export interface WorkDay {
  /** Короткая подпись дня: ПН, ВТ, … */
  day: string;
  /** Часы работы или обозначение выходного. */
  hours: string;
  /** Выходной день — в вёрстке приглушается классом `.muted`. */
  isDayOff: boolean;
}

/** График работы: выходные — понедельник и четверг. */
export const WORK_SCHEDULE: readonly WorkDay[] = [
  { day: 'ПН', hours: DAY_OFF, isDayOff: true },
  { day: 'ВТ', hours: WORK_HOURS, isDayOff: false },
  { day: 'СР', hours: WORK_HOURS, isDayOff: false },
  { day: 'ЧТ', hours: DAY_OFF, isDayOff: true },
  { day: 'ПТ', hours: WORK_HOURS, isDayOff: false },
  { day: 'СБ', hours: WORK_HOURS, isDayOff: false },
  { day: 'ВС', hours: WORK_HOURS, isDayOff: false },
];

/** Подпись под условиями доставки. */
export const DELIVERY_NOTE =
  'Точное время доставки согласуем по телефону при подтверждении заказа.';

/** Подпись под условиями самовывоза. */
export const PICKUP_NOTE =
  'Забрать заказ можно в рабочие часы — мы свяжемся с вами для подтверждения.';

/** Заглушка, пока адрес самовывоза не пришёл из настроек. */
export const PICKUP_ADDRESS_FALLBACK = 'уточним при подтверждении';
