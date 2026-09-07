import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Page } from '../../components/Layout';
import { Button, EmptyState, ErrorState, LinkButton, ListSkeleton, Photo } from '../../components/ui';
import { useToast } from '../../components/ToastContext';
import { errorMessage } from '../../api/client';
import { useAdminProducts, useToggleProductActive } from '../../api/queries';
import type { Product } from '../../api/types';
import { formatPricePerKg, formatWeight, hasSellableStock } from '../../lib/money';
import { haptic, showConfirm } from '../../telegram/webapp';

const PAGE_SIZE = 20;

export function AdminProductsPage() {
  const [search, setSearch] = useState('');
  const [limit, setLimit] = useState(PAGE_SIZE);

  const { data, isPending, isError, error, isFetching, refetch } = useAdminProducts({
    include_inactive: true,
    search: search.trim() === '' ? undefined : search.trim(),
    limit,
    offset: 0,
  });

  const toggleActive = useToggleProductActive();
  const toast = useToast();

  const handleToggle = async (product: Product) => {
    const nextActive = !product.is_active;
    const question = nextActive
      ? 'Вернуть «' + product.name + '» в каталог?'
      : 'Скрыть «' + product.name + '» из каталога?';

    const confirmed = await showConfirm(question);
    if (!confirmed) return;

    try {
      await toggleActive.mutateAsync({ id: product.id, nextActive });
      haptic.notification('success');
      toast.success(nextActive ? 'Товар снова в каталоге' : 'Товар скрыт из каталога');
    } catch (mutationError) {
      haptic.notification('error');
      toast.error(errorMessage(mutationError));
    }
  };

  return (
    <Page
      title="Товары"
      back
      backTo="/admin"
      actions={<LinkButton to="/admin/products/new" variant="ghost">+ Товар</LinkButton>}
    >
      <div className="stack">
        <input
          className="input"
          type="search"
          placeholder="Поиск по названию"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label="Поиск по названию"
        />

        {isPending ? <ListSkeleton count={5} /> : null}

        {isError ? (
          <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
        ) : null}

        {!isPending && !isError && data ? (
          data.items.length === 0 ? (
            <EmptyState
              icon="🥩"
              title={search.trim() === '' ? 'Товаров пока нет' : 'Ничего не найдено'}
              text={
                search.trim() === ''
                  ? 'Добавьте первую позицию — она сразу появится в каталоге.'
                  : 'Попробуйте изменить запрос.'
              }
              action={<LinkButton to="/admin/products/new">Добавить товар</LinkButton>}
            />
          ) : (
            <>
              <div className="list">
                {data.items.map((product) => (
                  <div className="list-row" key={product.id}>
                    <div className="list-row__thumb">
                      <Photo url={product.photo_url} alt={product.name} />
                    </div>

                    <div className="grow stack stack--tight">
                      <Link className="product-card__name" to={'/admin/products/' + product.id}>
                        {product.name}
                      </Link>
                      <div className="muted">
                        {formatPricePerKg(product.price_per_kg)} · остаток{' '}
                        {formatWeight(product.stock_kg)}
                      </div>
                      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                        {product.is_active ? null : <span className="badge badge--muted">Скрыт</span>}
                        {hasSellableStock(product.stock_kg) ? null : (
                          <span className="badge badge--cancelled">Нет остатка</span>
                        )}
                      </div>
                    </div>

                    <div className="stack stack--tight" style={{ flex: '0 0 auto' }}>
                      <LinkButton to={'/admin/products/' + product.id} variant="secondary">
                        Изменить
                      </LinkButton>
                      <Button
                        variant={product.is_active ? 'danger' : 'secondary'}
                        size="sm"
                        disabled={toggleActive.isPending}
                        onClick={() => void handleToggle(product)}
                      >
                        {product.is_active ? 'Скрыть' : 'Вернуть'}
                      </Button>
                    </div>
                  </div>
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
      </div>
    </Page>
  );
}
