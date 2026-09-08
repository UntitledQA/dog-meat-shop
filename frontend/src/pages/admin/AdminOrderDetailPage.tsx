import { useParams } from 'react-router-dom';
import { Page } from '../../components/Layout';
import { Button, EmptyState, ErrorState, LinkButton, ListSkeleton, StatusBadge } from '../../components/ui';
import { InfoRow, OrderInfo, OrderItems } from '../../components/OrderDetails';
import { useToast } from '../../components/ToastContext';
import { ApiError, errorMessage } from '../../api/client';
import { useAdminOrder, useUpdateOrderStatus } from '../../api/queries';
import type { AdminOrder, OrderStatus } from '../../api/types';
import { allowedTransitions, statusLabel } from '../../lib/orderStatus';
import { haptic, showConfirm } from '../../telegram/webapp';

/** Кто оформил заказ — блок доступен только администратору. */
function CustomerPanel({ order }: { order: AdminOrder }) {
  const telegramName = [order.user.first_name, order.user.last_name].filter(Boolean).join(' ').trim();

  return (
    <div className="panel stack stack--tight">
      <h2>Покупатель</h2>
      <InfoRow label="Имя в Telegram" value={telegramName === '' ? '—' : telegramName} />
      <InfoRow label="Username" value={order.user.username ? '@' + order.user.username : '—'} />
      <InfoRow label="Telegram ID" value={String(order.user.telegram_id)} />
    </div>
  );
}

export function AdminOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const orderId = Number(params.id);

  const { data: order, isPending, isError, error, refetch } = useAdminOrder(orderId);
  const updateStatus = useUpdateOrderStatus();
  const toast = useToast();

  const handleStatus = async (next: OrderStatus, current: AdminOrder) => {
    const question =
      next === 'cancelled'
        ? 'Отменить заказ ' + current.order_number + '? Остатки вернутся на склад.'
        : 'Перевести заказ в статус «' + statusLabel(next) + '»?';

    const confirmed = await showConfirm(question);
    if (!confirmed) return;

    try {
      await updateStatus.mutateAsync({ id: current.id, status: next });
      haptic.notification('success');
      toast.success(
        next === 'cancelled' ? 'Заказ отменён' : 'Статус изменён: ' + statusLabel(next),
      );
    } catch (mutationError) {
      haptic.notification('error');
      toast.error(errorMessage(mutationError));
    }
  };

  if (!Number.isFinite(orderId) || orderId <= 0) {
    return (
      <Page title="Заказ" back backTo="/admin/orders">
        <EmptyState
          icon="🔎"
          title="Заказ не найден"
          text="Ссылка выглядит некорректной."
          action={<LinkButton to="/admin/orders">К списку заказов</LinkButton>}
        />
      </Page>
    );
  }

  if (isPending) {
    return (
      <Page title="Заказ" back backTo="/admin/orders">
        <ListSkeleton count={4} />
      </Page>
    );
  }

  if (isError || !order) {
    const apiError = error instanceof ApiError ? error : null;
    if (apiError?.isNotFound) {
      return (
        <Page title="Заказ" back backTo="/admin/orders">
          <EmptyState
            icon="🔎"
            title="Заказ не найден"
            text="Возможно, он был удалён."
            action={<LinkButton to="/admin/orders">К списку заказов</LinkButton>}
          />
        </Page>
      );
    }
    return (
      <Page title="Заказ" back backTo="/admin/orders">
        <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
      </Page>
    );
  }

  const transitions = allowedTransitions(order.status);
  const nextStatuses = transitions.filter((value) => value !== 'cancelled');
  const canCancel = transitions.includes('cancelled');
  const busy = updateStatus.isPending;

  return (
    <Page title={order.order_number} back backTo="/admin/orders">
      <div className="stack">
        <div className="panel row row--between">
          <div>
            <div className="muted">Текущий статус</div>
            <strong>{order.order_number}</strong>
          </div>
          <StatusBadge status={order.status} label={order.status_label} />
        </div>

        <OrderInfo order={order} />
        <CustomerPanel order={order} />
        <OrderItems order={order} />

        <div className="panel stack stack--tight">
          <h2>Управление статусом</h2>

          {nextStatuses.length === 0 && !canCancel ? (
            <p className="field__hint">Заказ завершён — статус больше не меняется.</p>
          ) : null}

          {nextStatuses.map((next) => (
            <Button
              key={next}
              block
              loading={busy}
              disabled={busy}
              onClick={() => void handleStatus(next, order)}
            >
              Перевести в «{statusLabel(next)}»
            </Button>
          ))}

          {canCancel ? (
            <Button
              variant="danger"
              block
              disabled={busy}
              onClick={() => void handleStatus('cancelled', order)}
            >
              Отменить заказ
            </Button>
          ) : null}
        </div>
      </div>
    </Page>
  );
}
