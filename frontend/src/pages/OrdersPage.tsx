import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Page } from '../components/Layout';
import { Button, EmptyState, ErrorState, LinkButton, ListSkeleton, StatusBadge } from '../components/ui';
import { errorMessage } from '../api/client';
import { useMyOrders } from '../api/queries';
import { formatPrice } from '../lib/money';
import { formatDateTime } from '../lib/date';
import { deliveryTypeLabel } from '../lib/orderStatus';

const PAGE_SIZE = 20;

export function OrdersPage() {
  const [limit, setLimit] = useState(PAGE_SIZE);
  const { data, isPending, isError, error, isFetching, refetch } = useMyOrders({
    limit,
    offset: 0,
  });

  return (
    <Page title="Мои заказы">
      {isPending ? <ListSkeleton count={4} /> : null}

      {isError ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : null}

      {!isPending && !isError && data ? (
        data.items.length === 0 ? (
          <EmptyState
            icon="📋"
            title="Заказов пока нет"
            text="Оформите первый заказ — он появится здесь вместе со статусом."
            action={<LinkButton to="/">Перейти в каталог</LinkButton>}
          />
        ) : (
          <>
            <div className="list">
              {data.items.map((order) => (
                <Link className="list-row" key={order.id} to={'/orders/' + order.id}>
                  <div className="grow stack stack--tight">
                    <div className="row row--between">
                      <strong>{order.order_number}</strong>
                      <StatusBadge status={order.status} label={order.status_label} />
                    </div>
                    <div className="muted">{formatDateTime(order.created_at)}</div>
                    <div className="row row--between">
                      <span className="muted">{deliveryTypeLabel(order.delivery_type)}</span>
                      <strong>{formatPrice(order.total)}</strong>
                    </div>
                  </div>
                </Link>
              ))}
            </div>

            {data.total > data.items.length ? (
              <div className="pagination">
                <Button
                  block
                  variant="secondary"
                  loading={isFetching}
                  onClick={() => setLimit((current) => current + PAGE_SIZE)}
                >
                  Показать ещё
                </Button>
              </div>
            ) : null}
          </>
        )
      ) : null}
    </Page>
  );
}
