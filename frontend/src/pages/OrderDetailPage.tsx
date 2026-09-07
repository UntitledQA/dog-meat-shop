import { useParams } from 'react-router-dom';
import { Page } from '../components/Layout';
import { EmptyState, ErrorState, LinkButton, ListSkeleton, StatusBadge } from '../components/ui';
import { OrderInfo, OrderItems } from '../components/OrderDetails';
import { ApiError, errorMessage } from '../api/client';
import { useMyOrder } from '../api/queries';

export function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const orderId = Number(params.id);
  const { data: order, isPending, isError, error, refetch } = useMyOrder(orderId);

  if (!Number.isFinite(orderId) || orderId <= 0) {
    return (
      <Page title="Заказ" back backTo="/orders">
        <EmptyState
          icon="🔎"
          title="Заказ не найден"
          text="Ссылка выглядит некорректной."
          action={<LinkButton to="/orders">К списку заказов</LinkButton>}
        />
      </Page>
    );
  }

  if (isPending) {
    return (
      <Page title="Заказ" back backTo="/orders">
        <ListSkeleton count={3} />
      </Page>
    );
  }

  if (isError || !order) {
    const apiError = error instanceof ApiError ? error : null;
    if (apiError && (apiError.isNotFound || apiError.isForbidden)) {
      return (
        <Page title="Заказ" back backTo="/orders">
          <EmptyState
            icon="🔒"
            title="Заказ недоступен"
            text="Он не найден или принадлежит другому пользователю."
            action={<LinkButton to="/orders">К списку заказов</LinkButton>}
          />
        </Page>
      );
    }
    return (
      <Page title="Заказ" back backTo="/orders">
        <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
      </Page>
    );
  }

  return (
    <Page title={order.order_number} back backTo="/orders">
      <div className="stack">
        <div className="panel row row--between">
          <div>
            <div className="muted">Статус заказа</div>
            <strong>{order.order_number}</strong>
          </div>
          <StatusBadge status={order.status} label={order.status_label} />
        </div>

        <OrderInfo order={order} />
        <OrderItems order={order} />
      </div>
    </Page>
  );
}
