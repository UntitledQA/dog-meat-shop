import { useState } from 'react';
import { Page } from '../components/Layout';
import { ProductCard } from '../components/ProductCard';
import { Button, CatalogSkeleton, EmptyState, ErrorState } from '../components/ui';
import { useToast } from '../components/ToastContext';
import { useCatalog } from '../api/queries';
import { errorMessage } from '../api/client';
import { useCartStore } from '../store/cart';
import { formatWeight } from '../lib/money';
import { haptic } from '../telegram/webapp';
import type { Product } from '../api/types';

const PAGE_SIZE = 24;

export function CatalogPage() {
  const [limit, setLimit] = useState(PAGE_SIZE);
  const { data, isPending, isError, error, isFetching, refetch } = useCatalog({ limit, offset: 0 });
  const addToCart = useCartStore((state) => state.add);
  const toast = useToast();

  const handleAdd = (product: Product, weightKg: string) => {
    addToCart(product, weightKg);
    haptic.notification('success');
    toast.success(product.name + ' — ' + formatWeight(weightKg) + ' в корзине');
  };

  return (
    <Page title="Мясо для собак">
      {isPending ? <CatalogSkeleton /> : null}

      {isError ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : null}

      {!isPending && !isError && data ? (
        data.items.length === 0 ? (
          <EmptyState
            icon="🥩"
            title="Каталог пока пуст"
            text="Товары скоро появятся. Загляните чуть позже."
            action={
              <Button variant="secondary" onClick={() => void refetch()}>
                Обновить
              </Button>
            }
          />
        ) : (
          <>
            <div className="catalog-grid">
              {data.items.map((product) => (
                <ProductCard key={product.id} product={product} onAdd={handleAdd} />
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
