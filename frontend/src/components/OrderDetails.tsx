/** Общий блок с составом и суммами заказа: покупательский и админский экраны. */

import { formatPrice, formatPricePerKg, formatWeight } from '../lib/money';
import { formatDate, formatDateTime } from '../lib/date';
import { deliveryTypeLabel } from '../lib/orderStatus';
import { formatPhone } from '../lib/validation';
import type { Order } from '../api/types';

/** Строка «подпись — значение». `muted` приглушает значение (например, выходной день). */
export function InfoRow({
  label,
  value,
  muted = false,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div className="info-row">
      <span className="info-row__label">{label}</span>
      <span className={'info-row__value' + (muted ? ' muted' : '')}>{value}</span>
    </div>
  );
}

/** Данные доставки/самовывоза и контакты покупателя. */
export function OrderInfo({ order }: { order: Order }) {
  const isDelivery = order.delivery_type === 'delivery';

  return (
    <div className="panel stack stack--tight">
      <h2>Доставка</h2>
      <InfoRow label="Оформлен" value={formatDateTime(order.created_at)} />
      <InfoRow label="Способ" value={deliveryTypeLabel(order.delivery_type)} />
      {isDelivery ? <InfoRow label="Адрес" value={order.address ?? '—'} /> : null}
      <InfoRow label="Когда" value={formatDate(order.delivery_date)} />
      <InfoRow label="Получатель" value={order.customer_name} />
      <InfoRow label="Телефон" value={formatPhone(order.phone)} />
      {order.comment ? <InfoRow label="Комментарий" value={order.comment} /> : null}
    </div>
  );
}

/** Позиции заказа и итоговые суммы. */
export function OrderItems({ order }: { order: Order }) {
  return (
    <div className="panel stack stack--tight">
      <h2>Состав заказа</h2>

      {order.items.map((item) => (
        <div className="row" key={item.id}>
          <div className="grow">
            <div>{item.product_name}</div>
            <div className="muted">
              {formatWeight(item.weight_kg)} × {formatPricePerKg(item.price_per_kg)}
            </div>
          </div>
          <strong style={{ whiteSpace: 'nowrap' }}>{formatPrice(item.line_total)}</strong>
        </div>
      ))}

      <hr className="divider" />

      <div className="summary-row">
        <span className="muted">Товары</span>
        <span>{formatPrice(order.subtotal)}</span>
      </div>
      <div className="summary-row">
        <span className="muted">Доставка</span>
        <span>{formatPrice(order.delivery_price)}</span>
      </div>
      <div className="summary-row summary-row--total">
        <span>Итого</span>
        <span>{formatPrice(order.total)}</span>
      </div>
      <p className="field__hint">Оплата при получении</p>
    </div>
  );
}
