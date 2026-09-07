import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Page } from '../components/Layout';
import { Button, EmptyState, ErrorState, LinkButton, Photo, Skeleton } from '../components/ui';
import { WeightPicker } from '../components/WeightPicker';
import { defaultAddWeight } from '../components/ProductCard';
import { useToast } from '../components/ToastContext';
import { ApiError, errorMessage } from '../api/client';
import { useProduct, useSettings } from '../api/queries';
import { useCartStore } from '../store/cart';
import {
  DEFAULT_MIN_WEIGHT,
  DEFAULT_WEIGHT_STEP,
  calcLineTotal,
  formatPrice,
  formatPricePerKg,
  formatWeight,
  hasSellableStock,
} from '../lib/money';
import { haptic } from '../telegram/webapp';

/** Скелетон карточки товара на время загрузки. */
function ProductSkeleton() {
  return (
    <div className="stack">
      <div className="product-hero">
        <Skeleton style={{ width: '100%', height: '100%', borderRadius: 0 }} />
      </div>
      <Skeleton className="skeleton--text" style={{ width: '70%', height: 22 }} />
      <Skeleton className="skeleton--text" style={{ width: '40%', height: 18 }} />
      <Skeleton className="skeleton--text" style={{ width: '90%' }} />
      <Skeleton className="skeleton--text" style={{ width: '85%' }} />
      <Skeleton style={{ width: '100%', height: 44 }} />
    </div>
  );
}

export function ProductPage() {
  const params = useParams<{ id: string }>();
  const productId = Number(params.id);

  const { data: product, isPending, isError, error, refetch } = useProduct(productId);
  const { data: settings } = useSettings();
  const addToCart = useCartStore((state) => state.add);
  const toast = useToast();

  // null — пользователь ещё не трогал вес, показываем значение по умолчанию.
  const [chosenWeight, setChosenWeight] = useState<string | null>(null);

  const minWeight = settings?.min_weight_kg ?? DEFAULT_MIN_WEIGHT;
  const stepWeight = settings?.weight_step_kg ?? DEFAULT_WEIGHT_STEP;

  if (!Number.isFinite(productId) || productId <= 0) {
    return (
      <Page title="Товар" back backTo="/">
        <EmptyState
          icon="🔎"
          title="Товар не найден"
          text="Ссылка выглядит некорректной."
          action={<LinkButton to="/">В каталог</LinkButton>}
        />
      </Page>
    );
  }

  if (isPending) {
    return (
      <Page title="Товар" back backTo="/">
        <ProductSkeleton />
      </Page>
    );
  }

  if (isError) {
    const apiError = error instanceof ApiError ? error : null;
    const isMissing = Boolean(apiError && (apiError.isNotFound || apiError.code === 'product_unavailable'));

    return (
      <Page title="Товар" back backTo="/">
        {isMissing ? (
          <EmptyState
            icon="🔎"
            title="Товар не найден"
            text="Возможно, он больше не продаётся."
            action={<LinkButton to="/">В каталог</LinkButton>}
          />
        ) : (
          <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
        )}
      </Page>
    );
  }

  if (!product) {
    return (
      <Page title="Товар" back backTo="/">
        <ProductSkeleton />
      </Page>
    );
  }

  const available = product.in_stock && hasSellableStock(product.stock_kg, minWeight);
  const weight = chosenWeight ?? defaultAddWeight(product);
  const lineTotal = calcLineTotal(weight, product.price_per_kg);

  const handleAdd = () => {
    if (!available) return;
    addToCart(product, weight);
    haptic.notification('success');
    toast.success(product.name + ' — ' + formatWeight(weight) + ' в корзине');
  };

  return (
    <Page title={product.name} back backTo="/">
      <div className="stack">
        <div className="product-hero">
          <Photo url={product.photo_url} alt={product.name} />
        </div>

        <div className="stack stack--tight">
          <div className="row row--between">
            <h1>{product.name}</h1>
            {available ? null : <span className="badge badge--cancelled">Нет в наличии</span>}
          </div>
          <div className="price-line">{formatPricePerKg(product.price_per_kg)}</div>
          <div className="muted">
            {available ? 'В наличии ' + formatWeight(product.stock_kg) : 'Товар закончился'}
          </div>
        </div>

        {product.description ? (
          <div className="panel">
            <p style={{ whiteSpace: 'pre-line' }}>{product.description}</p>
          </div>
        ) : null}

        <div className="panel stack">
          <div className="field">
            <label className="field__label" htmlFor="product-weight">
              Сколько взвесить?
            </label>
            <WeightPicker
              id="product-weight"
              value={weight}
              onChange={setChosenWeight}
              min={minWeight}
              max={product.stock_kg}
              step={stepWeight}
              disabled={!available}
            />
            <span className="field__hint">
              Шаг {formatWeight(stepWeight)}, минимум {formatWeight(minWeight)}
              {available ? ', максимум ' + formatWeight(product.stock_kg) : ''}
            </span>
          </div>

          <div className="summary-row summary-row--total">
            <span>Стоимость</span>
            <span>{formatPrice(available ? lineTotal : '0.00')}</span>
          </div>
        </div>
      </div>

      <div className="sticky-bar">
        <Button block disabled={!available} onClick={handleAdd}>
          {available ? 'Добавить в корзину · ' + formatPrice(lineTotal) : 'Нет в наличии'}
        </Button>
      </div>
    </Page>
  );
}
