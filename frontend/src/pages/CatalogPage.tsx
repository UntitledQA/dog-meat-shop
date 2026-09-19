import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Page } from '../components/Layout';
import { ProductCard } from '../components/ProductCard';
import { Button, CatalogSkeleton, EmptyState, ErrorState } from '../components/ui';
import { useToast } from '../components/ToastContext';
import { useCatalog } from '../api/queries';
import { errorMessage } from '../api/client';
import { useCartStore } from '../store/cart';
import { formatWeight } from '../lib/money';
import { haptic } from '../telegram/webapp';
import { PRODUCT_CATEGORIES, categoryLabel, isProductCategory } from '../lib/categories';
import type { Product, ProductCategory } from '../api/types';

const PAGE_SIZE = 24;

/** Имя query-параметра с выбранной категорией — для deep-link (`?category=beef`). */
const CATEGORY_PARAM = 'category';

export function CatalogPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // Категория — источник истины в URL. Невалидный slug трактуем как «Все».
  const rawCategory = searchParams.get(CATEGORY_PARAM);
  const category: ProductCategory | null = isProductCategory(rawCategory) ? rawCategory : null;

  const [limit, setLimit] = useState(PAGE_SIZE);

  // Сброс пагинации при смене категории (клик по чипу, deep-link, кнопка «назад»
  // браузера). Правим состояние прямо во время рендера — React перезапускает
  // компонент до коммита, поэтому лишнего запроса со старым limit не будет и
  // товары разных категорий не смешиваются. См. reactjs «adjusting state on prop change».
  const [prevCategory, setPrevCategory] = useState(category);
  if (category !== prevCategory) {
    setPrevCategory(category);
    setLimit(PAGE_SIZE);
  }

  const { data, isPending, isError, error, isFetching, refetch } = useCatalog({
    limit,
    offset: 0,
    category,
  });

  const addToCart = useCartStore((state) => state.add);
  const toast = useToast();

  /**
   * Меняет фильтр через query-параметр. «Все» убирает параметр из URL,
   * чтобы прямая ссылка на весь каталог оставалась чистой.
   */
  const applyCategory = (next: ProductCategory | null) => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        if (next) params.set(CATEGORY_PARAM, next);
        else params.delete(CATEGORY_PARAM);
        return params;
      },
      { replace: true },
    );
  };

  const handleAdd = (product: Product, weightKg: string) => {
    addToCart(product, weightKg);
    haptic.notification('success');
    toast.success(product.name + ' — ' + formatWeight(weightKg) + ' в корзине');
  };

  return (
    <Page title="Мясо для собак">
      <div className="stack">
        <div className="chips" role="group" aria-label="Фильтр по категории">
          <button
            type="button"
            className={'chip' + (category === null ? ' is-active' : '')}
            aria-pressed={category === null}
            onClick={() => applyCategory(null)}
          >
            Все
          </button>
          {PRODUCT_CATEGORIES.map((value) => (
            <button
              key={value}
              type="button"
              className={'chip' + (category === value ? ' is-active' : '')}
              aria-pressed={category === value}
              onClick={() => applyCategory(value)}
            >
              {categoryLabel(value)}
            </button>
          ))}
        </div>

        {isPending ? <CatalogSkeleton /> : null}

        {isError ? (
          <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
        ) : null}

        {!isPending && !isError && data ? (
          data.items.length === 0 ? (
            category === null ? (
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
              <EmptyState
                icon="🥩"
                title="В этой категории пока нет товаров"
                text={'В категории «' + categoryLabel(category) + '» пока пусто. Посмотрите другие.'}
                action={
                  <Button variant="secondary" onClick={() => applyCategory(null)}>
                    Показать все
                  </Button>
                }
              />
            )
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
      </div>
    </Page>
  );
}
