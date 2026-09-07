import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Page } from '../components/Layout';
import { Button, EmptyState, LinkButton, Photo } from '../components/ui';
import { useToast } from '../components/ToastContext';
import { ApiError, errorMessage } from '../api/client';
import { useCreateOrder, useMe, useSettings } from '../api/queries';
import type { InsufficientStockItem, Order, OrderCreate } from '../api/types';
import { useCartStore } from '../store/cart';
import {
  calcCartTotal,
  calcLineTotal,
  formatPrice,
  formatPricePerKg,
  formatWeight,
  toWeightString,
} from '../lib/money';
import { formatDate, isoDatePlusDays } from '../lib/date';
import {
  COMMENT_MAX_LENGTH,
  DELIVERY_TIME_SLOTS,
  formatTimeSlot,
  hasErrors,
  normalizePhone,
  todayIsoDate,
  validateCheckout,
} from '../lib/validation';
import type { CheckoutErrors, CheckoutFormValues } from '../lib/validation';
import { getTelegramUserName, haptic } from '../telegram/webapp';

/** Подпись поля с ошибкой валидации. */
function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <span className="field__error">{message}</span>;
}

function initialValues(): CheckoutFormValues {
  return {
    customerName: getTelegramUserName(),
    phone: '',
    deliveryType: 'delivery',
    address: '',
    deliveryDate: isoDatePlusDays(1),
    deliveryTime: DELIVERY_TIME_SLOTS[0],
    comment: '',
  };
}

/** Экран «заказ принят» — показывается вместо формы после успешного создания. */
function OrderCreated({ order, pickupAddress }: { order: Order; pickupAddress: string }) {
  return (
    <Page title="Заказ оформлен">
      <div className="stack">
        <EmptyState
          icon="✅"
          title={'Заказ ' + order.order_number + ' принят'}
          text="Мы свяжемся с вами для подтверждения. Оплата — при получении."
        />

        <div className="panel stack stack--tight">
          <div className="info-row">
            <span className="info-row__label">Способ получения</span>
            <span className="info-row__value">
              {order.delivery_type === 'delivery' ? 'Доставка' : 'Самовывоз'}
            </span>
          </div>
          <div className="info-row">
            <span className="info-row__label">
              {order.delivery_type === 'delivery' ? 'Адрес' : 'Забрать по адресу'}
            </span>
            <span className="info-row__value">
              {order.delivery_type === 'delivery' ? (order.address ?? '—') : pickupAddress || '—'}
            </span>
          </div>
          <div className="info-row">
            <span className="info-row__label">Когда</span>
            <span className="info-row__value">
              {formatDate(order.delivery_date)}
              {order.delivery_time ? ', ' + formatTimeSlot(order.delivery_time) : ''}
            </span>
          </div>
          <div className="summary-row summary-row--total">
            <span>Итого</span>
            <span>{formatPrice(order.total)}</span>
          </div>
        </div>

        <LinkButton to={'/orders/' + order.id} block>
          Открыть заказ
        </LinkButton>
        <LinkButton to="/" variant="secondary" block>
          Вернуться в каталог
        </LinkButton>
      </div>
    </Page>
  );
}

export function CheckoutPage() {
  const items = useCartStore((state) => state.items);
  const clearCart = useCartStore((state) => state.clear);
  const { data: settings } = useSettings();
  const { data: me } = useMe();
  const createOrder = useCreateOrder();
  const toast = useToast();
  const navigate = useNavigate();

  const [values, setValues] = useState<CheckoutFormValues>(initialValues);
  const [errors, setErrors] = useState<CheckoutErrors>({});
  const [stockIssues, setStockIssues] = useState<InsufficientStockItem[]>([]);
  const [createdOrder, setCreatedOrder] = useState<Order | null>(null);

  // Телефон и имя из профиля подставляем один раз — если пользователь ещё не вводил свои.
  useEffect(() => {
    if (!me) return;
    setValues((current) => {
      const next = { ...current };
      if (current.phone.trim() === '' && me.phone) next.phone = me.phone;
      if (current.customerName.trim() === '') {
        next.customerName = [me.first_name, me.last_name].filter(Boolean).join(' ').trim();
      }
      return next;
    });
  }, [me]);

  const isDelivery = values.deliveryType === 'delivery';
  const deliveryPrice = isDelivery ? (settings?.delivery_price ?? '0.00') : '0.00';
  const totals = calcCartTotal(
    items.map((item) => ({ weightKg: item.weightKg, pricePerKg: item.pricePerKg })),
    deliveryPrice,
  );

  const setField = <K extends keyof CheckoutFormValues>(key: K, value: CheckoutFormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }));
    setErrors((current) => {
      if (!(key in current)) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  };

  const handleSubmit = async () => {
    const nextErrors = validateCheckout(values);
    setErrors(nextErrors);
    setStockIssues([]);

    if (hasErrors(nextErrors)) {
      haptic.notification('error');
      toast.error('Проверьте заполнение формы');
      return;
    }

    const comment = values.comment.trim();
    const payload: OrderCreate = {
      items: items.map((item) => ({
        product_id: item.productId,
        weight_kg: toWeightString(item.weightKg),
      })),
      delivery_type: values.deliveryType,
      customer_name: values.customerName.trim(),
      phone: normalizePhone(values.phone),
      address: isDelivery ? values.address.trim() : null,
      delivery_date: values.deliveryDate,
      delivery_time: values.deliveryTime,
      comment: comment === '' ? null : comment,
    };

    try {
      const order = await createOrder.mutateAsync(payload);
      clearCart();
      setCreatedOrder(order);
      haptic.notification('success');
    } catch (error) {
      haptic.notification('error');
      if (error instanceof ApiError && error.code === 'insufficient_stock') {
        setStockIssues(error.insufficientStockItems);
      }
      toast.error(errorMessage(error));
    }
  };

  if (createdOrder) {
    return <OrderCreated order={createdOrder} pickupAddress={settings?.pickup_address ?? ''} />;
  }

  if (items.length === 0) {
    return (
      <Page title="Оформление" back backTo="/cart">
        <EmptyState
          icon="🛒"
          title="Корзина пуста"
          text="Добавьте товары, чтобы оформить заказ."
          action={<LinkButton to="/">Перейти в каталог</LinkButton>}
        />
      </Page>
    );
  }

  const submitting = createOrder.isPending;

  return (
    <Page title="Оформление" back backTo="/cart">
      <div className="stack">
        {/* --------------------------- Контактные данные -------------------------- */}
        <div className="panel stack">
          <h2>Получатель</h2>

          <div className="field">
            <label className="field__label" htmlFor="checkout-name">
              Имя
            </label>
            <input
              id="checkout-name"
              className={'input' + (errors.customerName ? ' has-error' : '')}
              type="text"
              autoComplete="name"
              placeholder="Как к вам обращаться"
              value={values.customerName}
              onChange={(event) => setField('customerName', event.target.value)}
            />
            <FieldError message={errors.customerName} />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="checkout-phone">
              Телефон
            </label>
            <input
              id="checkout-phone"
              className={'input' + (errors.phone ? ' has-error' : '')}
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="+7 999 123-45-67"
              value={values.phone}
              onChange={(event) => setField('phone', event.target.value)}
            />
            <FieldError message={errors.phone} />
          </div>
        </div>

        {/* ---------------------------- Способ получения --------------------------- */}
        <div className="panel stack">
          <h2>Получение</h2>

          <div className="segmented" role="group" aria-label="Способ получения">
            <button
              type="button"
              className={'segmented__option' + (isDelivery ? ' is-active' : '')}
              aria-pressed={isDelivery}
              onClick={() => setField('deliveryType', 'delivery')}
            >
              Доставка
            </button>
            <button
              type="button"
              className={'segmented__option' + (!isDelivery ? ' is-active' : '')}
              aria-pressed={!isDelivery}
              onClick={() => setField('deliveryType', 'pickup')}
            >
              Самовывоз
            </button>
          </div>

          {isDelivery ? (
            <div className="field">
              <label className="field__label" htmlFor="checkout-address">
                Адрес доставки
              </label>
              <input
                id="checkout-address"
                className={'input' + (errors.address ? ' has-error' : '')}
                type="text"
                autoComplete="street-address"
                placeholder="Улица, дом, квартира"
                value={values.address}
                onChange={(event) => setField('address', event.target.value)}
              />
              <FieldError message={errors.address} />
            </div>
          ) : (
            <p className="field__hint">
              Заберите заказ по адресу: {settings?.pickup_address ?? 'уточним при подтверждении'}
            </p>
          )}

          <div className="field">
            <label className="field__label" htmlFor="checkout-date">
              {isDelivery ? 'Дата доставки' : 'Дата получения'}
            </label>
            <input
              id="checkout-date"
              className={'input' + (errors.deliveryDate ? ' has-error' : '')}
              type="date"
              min={todayIsoDate()}
              value={values.deliveryDate}
              onChange={(event) => setField('deliveryDate', event.target.value)}
            />
            <FieldError message={errors.deliveryDate} />
          </div>

          <div className="field">
            <span className="field__label" id="checkout-time-label">
              Интервал времени
            </span>
            <div className="chips" role="group" aria-labelledby="checkout-time-label">
              {DELIVERY_TIME_SLOTS.map((slot) => (
                <button
                  key={slot}
                  type="button"
                  className={'chip' + (values.deliveryTime === slot ? ' is-active' : '')}
                  aria-pressed={values.deliveryTime === slot}
                  onClick={() => setField('deliveryTime', slot)}
                >
                  {formatTimeSlot(slot)}
                </button>
              ))}
            </div>
            <FieldError message={errors.deliveryTime} />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="checkout-comment">
              Комментарий
            </label>
            <textarea
              id="checkout-comment"
              className={'textarea' + (errors.comment ? ' has-error' : '')}
              placeholder="Домофон, пожелания по нарезке и т. п."
              maxLength={COMMENT_MAX_LENGTH}
              value={values.comment}
              onChange={(event) => setField('comment', event.target.value)}
            />
            <FieldError message={errors.comment} />
          </div>
        </div>

        {/* ------------------------------ Состав заказа ---------------------------- */}
        <div className="panel stack stack--tight">
          <h2>Состав заказа</h2>

          {items.map((item) => (
            <div className="row" key={item.productId}>
              <div className="list-row__thumb" style={{ flex: '0 0 44px', width: 44, height: 44 }}>
                <Photo url={item.photoUrl} alt={item.name} />
              </div>
              <div className="grow">
                <div>{item.name}</div>
                <div className="muted">
                  {formatWeight(item.weightKg)} × {formatPricePerKg(item.pricePerKg)}
                </div>
              </div>
              <strong style={{ whiteSpace: 'nowrap' }}>
                {formatPrice(calcLineTotal(item.weightKg, item.pricePerKg))}
              </strong>
            </div>
          ))}

          <hr className="divider" />

          <div className="summary-row">
            <span className="muted">Товары</span>
            <span>{formatPrice(totals.subtotal)}</span>
          </div>
          <div className="summary-row">
            <span className="muted">Доставка</span>
            <span>{isDelivery ? formatPrice(totals.deliveryPrice) : 'Бесплатно'}</span>
          </div>
          <div className="summary-row summary-row--total">
            <span>Итого</span>
            <span>{formatPrice(totals.total)}</span>
          </div>
          <p className="field__hint">{settings?.payment_note ?? 'Оплата при получении'}</p>
        </div>

        {/* --------------------------- Не хватило остатка -------------------------- */}
        {stockIssues.length > 0 ? (
          <div className="panel stack stack--tight">
            <h2 className="text-danger">Не хватает на складе</h2>
            {stockIssues.map((issue) => (
              <div className="info-row" key={issue.product_id}>
                <span className="info-row__label">{issue.product_name}</span>
                <span className="info-row__value">
                  нужно {formatWeight(issue.requested_kg)}, доступно{' '}
                  {formatWeight(issue.available_kg)}
                </span>
              </div>
            ))}
            <Button variant="secondary" block onClick={() => navigate('/cart')}>
              Изменить корзину
            </Button>
          </div>
        ) : null}
      </div>

      <div className="sticky-bar">
        <Button block loading={submitting} disabled={submitting} onClick={() => void handleSubmit()}>
          {submitting ? 'Отправляем…' : 'Подтвердить заказ · ' + formatPrice(totals.total)}
        </Button>
      </div>
    </Page>
  );
}
