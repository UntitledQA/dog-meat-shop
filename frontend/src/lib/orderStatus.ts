/** Статусы заказа: подписи, цвета бейджей и допустимые переходы (раздел 6.7). */

import type { DeliveryType, OrderStatus } from '../api/types';

export const ORDER_STATUSES: OrderStatus[] = [
  'confirmed',
  'delivering',
  'completed',
  'cancelled',
];

const LABELS: Record<OrderStatus, string> = {
  confirmed: 'Подтверждён',
  delivering: 'Доставляется',
  completed: 'Готово',
  cancelled: 'Отменён',
};

/** Подпись статуса. Если бэкенд прислал status_label — используем его. */
export function statusLabel(status: OrderStatus, fromServer?: string | null): string {
  if (fromServer && fromServer.trim() !== '') return fromServer;
  return LABELS[status] ?? status;
}

/** CSS-модификатор бейджа: badge--confirmed и т. д. */
export function statusModifier(status: OrderStatus): string {
  return 'badge--' + status;
}

/**
 * Допустимые следующие статусы.
 *
 * Самовывоз: подтверждён → готово.
 * Доставка:  подтверждён → доставляется → готово (можно и сразу в готово).
 * Отмена — из любого статуса, кроме готового и отменённого.
 *
 * «Доставляется» не предлагается самовывозу: забирают сами, везти некому.
 * Это дублирует проверку бэкенда, а не заменяет её.
 */
export function allowedTransitions(
  status: OrderStatus,
  deliveryType: DeliveryType,
): OrderStatus[] {
  const chain: Record<OrderStatus, OrderStatus[]> = {
    confirmed: deliveryType === 'delivery' ? ['delivering', 'completed'] : ['completed'],
    delivering: ['completed'],
    completed: [],
    cancelled: [],
  };
  const next = [...chain[status]];
  if (status !== 'completed' && status !== 'cancelled') next.push('cancelled');
  return next;
}

export const DELIVERY_TYPE_LABELS: Record<string, string> = {
  delivery: 'Доставка',
  pickup: 'Самовывоз',
};

export function deliveryTypeLabel(value: string): string {
  return DELIVERY_TYPE_LABELS[value] ?? value;
}
