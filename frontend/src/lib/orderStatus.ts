/** Статусы заказа: подписи, цвета бейджей и допустимые переходы (раздел 6.7). */

import type { OrderStatus } from '../api/types';

export const ORDER_STATUSES: OrderStatus[] = [
  'new',
  'confirmed',
  'preparing',
  'delivering',
  'completed',
  'cancelled',
];

const LABELS: Record<OrderStatus, string> = {
  new: 'Новый',
  confirmed: 'Подтверждён',
  preparing: 'Готовится',
  delivering: 'Доставляется',
  completed: 'Выполнен',
  cancelled: 'Отменён',
};

/** Подпись статуса. Если бэкенд прислал status_label — используем его. */
export function statusLabel(status: OrderStatus, fromServer?: string | null): string {
  if (fromServer && fromServer.trim() !== '') return fromServer;
  return LABELS[status] ?? status;
}

/** CSS-модификатор бейджа: badge--new и т. д. */
export function statusModifier(status: OrderStatus): string {
  return 'badge--' + status;
}

/**
 * Допустимые следующие статусы.
 * new → confirmed → preparing → delivering → completed;
 * cancelled — из любого, кроме completed/cancelled.
 */
export function allowedTransitions(status: OrderStatus): OrderStatus[] {
  const chain: Record<OrderStatus, OrderStatus[]> = {
    new: ['confirmed'],
    confirmed: ['preparing'],
    preparing: ['delivering'],
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
