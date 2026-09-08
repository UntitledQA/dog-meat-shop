import { Link } from 'react-router-dom';
import { Button, Photo } from './ui';
import {
  defaultAddWeight,
  formatPricePerKg,
  formatWeight,
  hasSellableStock,
} from '../lib/money';
import type { Product } from '../api/types';

export interface ProductCardProps {
  product: Product;
  onAdd?: (product: Product, weightKg: string) => void;
  /** Идёт запрос — блокируем кнопку. */
  busy?: boolean;
}

export function ProductCard({ product, onAdd, busy = false }: ProductCardProps) {
  const available = product.in_stock && hasSellableStock(product.stock_kg);

  return (
    <article className="product-card">
      <Link className="product-card__media" to={'/product/' + product.id}>
        <Photo url={product.photo_url} alt={product.name} />
        {available ? null : <span className="badge badge--out">Нет в наличии</span>}
      </Link>

      <div className="product-card__body">
        <Link className="product-card__name" to={'/product/' + product.id}>
          {product.name}
        </Link>
        {product.description ? (
          <p className="product-card__desc">{product.description}</p>
        ) : null}
        <div className="product-card__price">{formatPricePerKg(product.price_per_kg)}</div>
        <div className="product-card__stock">
          {available ? 'В наличии ' + formatWeight(product.stock_kg) : 'Закончился'}
        </div>
      </div>

      <div className="product-card__action">
        <Button
          block
          size="sm"
          disabled={!available || busy}
          onClick={() => onAdd?.(product, defaultAddWeight(product))}
        >
          {available ? 'В корзину' : 'Нет в наличии'}
        </Button>
      </div>
    </article>
  );
}
