import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Page } from '../../components/Layout';
import { Button, EmptyState, ErrorState, ListSkeleton, StatusBadge } from '../../components/ui';
import { errorMessage } from '../../api/client';
import { useAdminOrders } from '../../api/queries';
import type { OrderStatus } from '../../api/types';
import { ORDER_STATUSES, deliveryTypeLabel, statusLabel } from '../../lib/orderStatus';
import { formatPrice } from '../../lib/money';
import { formatDateTime } from '../../lib/date';

const PAGE_SIZE = 20;

export function AdminOrdersPage() {
  const [status, setStatus] = useState<OrderStatus | ''>('');
  const [offset, setOffset] = useState(0);

  const { data, isPending, isError, error, isFetching, refetch } = useAdminOrders({
    status,
    limit: PAGE_SIZE,
    offset,
  });

  const applyStatus = (next: OrderStatus | '') => {
    setStatus(next);
    setOffset(0);
  };

  const total = data?.total ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = Math.min(offset + (data?.items.length ?? 0), total);
  const hasPrev = offset > 0;
  const hasNext = offset + PAGE_SIZE < total;

  return (
    <Page title="Заказы" back backTo="/admin">
      <div className="stack">
        <div className="chips" role="group" aria-label="Фильтр по статусу">
          <button
            type="button"
            className={'chip' + (status === '' ? ' is-active' : '')}
            aria-pressed={status === ''}
            onClick={() => applyStatus('')}
          >
            Все
          </button>
          {ORDER_STATUSES.map((value) => (
            <button
              key={value}
              type="button"
              className={'chip' + (status === value ? ' is-active' : '')}
              aria-pressed={status === value}
              onClick={() => applyStatus(value)}
            >
              {statusLabel(value)}
            </button>
          ))}
        </div>

        {isPending ? <ListSkeleton count={5} /> : null}

        {isError ? (
          <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
        ) : null}

        {!isPending && !isError && data ? (
          data.items.length === 0 ? (
            <EmptyState
              icon="📦"
              title="Заказов нет"
              text={
                status === ''
                  ? 'Как только покупатель оформит заказ, он появится здесь.'
                  : 'Нет заказов с выбранным статусом.'
              }
              action={
                status === '' ? undefined : (
                  <Button variant="secondary" onClick={() => applyStatus('')}>
                    Показать все
                  </Button>
                )
              }
            />
          ) : (
            <>
              <div className="list">
                {data.items.map((order) => (
                  <Link className="list-row" key={order.id} to={'/admin/orders/' + order.id}>
                    <div className="grow stack stack--tight">
                      <div className="row row--between">
                        <strong>{order.order_number}</strong>
                        <StatusBadge status={order.status} label={order.status_label} />
                      </div>
                      <div className="muted">{formatDateTime(order.created_at)}</div>
                      <div className="row row--between">
                        <span className="muted">
                          {order.customer_name} · {deliveryTypeLabel(order.delivery_type)}
                        </span>
                        <strong>{formatPrice(order.total)}</strong>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>

              <div className="pagination">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!hasPrev || isFetching}
                  onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
                >
                  Назад
                </Button>
                <span className="muted">
                  {shownFrom}–{shownTo} из {total}
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!hasNext || isFetching}
                  onClick={() => setOffset((current) => current + PAGE_SIZE)}
                >
                  Вперёд
                </Button>
              </div>
            </>
          )
        ) : null}
      </div>
    </Page>
  );
}
