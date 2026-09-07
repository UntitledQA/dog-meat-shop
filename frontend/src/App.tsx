import { Navigate, Route, Routes } from 'react-router-dom';
import type { ReactNode } from 'react';
import { AppShell, Page } from './components/Layout';
import { EmptyState, LinkButton, ListSkeleton } from './components/ui';
import { useMe } from './api/queries';
import { useTelegramTheme } from './telegram/theme';
import { CatalogPage } from './pages/CatalogPage';
import { ProductPage } from './pages/ProductPage';
import { CartPage } from './pages/CartPage';
import { CheckoutPage } from './pages/CheckoutPage';
import { OrdersPage } from './pages/OrdersPage';
import { OrderDetailPage } from './pages/OrderDetailPage';
import { AdminHomePage } from './pages/admin/AdminHomePage';
import { AdminProductsPage } from './pages/admin/AdminProductsPage';
import { AdminProductFormPage } from './pages/admin/AdminProductFormPage';
import { AdminOrdersPage } from './pages/admin/AdminOrdersPage';
import { AdminOrderDetailPage } from './pages/admin/AdminOrderDetailPage';

/** Пускает в админку только пользователей с me.is_admin. */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { data: me, isPending } = useMe();

  if (isPending) {
    return (
      <Page title="Админ-панель">
        <ListSkeleton count={3} />
      </Page>
    );
  }

  if (!me?.is_admin) {
    return (
      <Page title="Админ-панель" back backTo="/">
        <EmptyState
          icon="🔒"
          title="Раздел недоступен"
          text="Админ-панель доступна только администраторам магазина."
          action={<LinkButton to="/">Вернуться в каталог</LinkButton>}
        />
      </Page>
    );
  }

  return <>{children}</>;
}

export function App() {
  useTelegramTheme();
  const { data: me } = useMe();

  return (
    <AppShell isAdmin={Boolean(me?.is_admin)}>
      <Routes>
        <Route path="/" element={<CatalogPage />} />
        <Route path="/product/:id" element={<ProductPage />} />
        <Route path="/cart" element={<CartPage />} />
        <Route path="/checkout" element={<CheckoutPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/orders/:id" element={<OrderDetailPage />} />

        <Route
          path="/admin"
          element={
            <RequireAdmin>
              <AdminHomePage />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/products"
          element={
            <RequireAdmin>
              <AdminProductsPage />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/products/new"
          element={
            <RequireAdmin>
              <AdminProductFormPage mode="create" />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/products/:id"
          element={
            <RequireAdmin>
              <AdminProductFormPage mode="edit" />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/orders"
          element={
            <RequireAdmin>
              <AdminOrdersPage />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/orders/:id"
          element={
            <RequireAdmin>
              <AdminOrderDetailPage />
            </RequireAdmin>
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
