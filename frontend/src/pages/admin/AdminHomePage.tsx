import { Link } from 'react-router-dom';
import { Page } from '../../components/Layout';
import { Skeleton } from '../../components/ui';
import { useAdminOrders, useAdminProducts } from '../../api/queries';

interface TileProps {
  to: string;
  icon: string;
  title: string;
  hint: string;
}

function Tile({ to, icon, title, hint }: TileProps) {
  return (
    <Link className="admin-tile" to={to}>
      <span className="admin-tile__icon" aria-hidden="true">
        {icon}
      </span>
      <span className="admin-tile__title">{title}</span>
      <span className="admin-tile__hint">{hint}</span>
    </Link>
  );
}

function Stat({ label, value, loading }: { label: string; value: number; loading: boolean }) {
  return (
    <div className="stat">
      <span className="stat__label">{label}</span>
      {loading ? (
        <Skeleton className="skeleton--text" style={{ width: 40, height: 20 }} />
      ) : (
        <strong className="stat__value">{value}</strong>
      )}
    </div>
  );
}

export function AdminHomePage() {
  // limit: 1 — нужны только счётчики total, а не сами списки.
  const products = useAdminProducts({ include_inactive: true, limit: 1, offset: 0 });
  const activeProducts = useAdminProducts({ include_inactive: false, limit: 1, offset: 0 });
  const allOrders = useAdminOrders({ limit: 1, offset: 0 });
  const newOrders = useAdminOrders({ status: 'new', limit: 1, offset: 0 });

  return (
    <Page title="Админ-панель">
      <div className="stack">
        <div className="panel">
          <div className="section-title" style={{ marginTop: 0 }}>
            Сводка
          </div>
          <div className="stat-grid">
            <Stat label="Товаров всего" value={products.data?.total ?? 0} loading={products.isPending} />
            <Stat
              label="Активных"
              value={activeProducts.data?.total ?? 0}
              loading={activeProducts.isPending}
            />
            <Stat label="Заказов всего" value={allOrders.data?.total ?? 0} loading={allOrders.isPending} />
            <Stat label="Новых заказов" value={newOrders.data?.total ?? 0} loading={newOrders.isPending} />
          </div>
        </div>

        <div className="admin-tiles">
          <Tile
            to="/admin/products"
            icon="🥩"
            title="Товары"
            hint="Цены, остатки, фото, скрытие"
          />
          <Tile to="/admin/orders" icon="📦" title="Заказы" hint="Статусы и отмена" />
          <Tile to="/admin/products/new" icon="➕" title="Новый товар" hint="Добавить позицию" />
          <Tile to="/" icon="🛍" title="Витрина" hint="Как видит покупатель" />
        </div>
      </div>
    </Page>
  );
}
