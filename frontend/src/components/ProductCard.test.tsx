import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ProductCard } from './ProductCard';
import { defaultAddWeight } from '../lib/money';
import type { Product } from '../api/types';

function makeProduct(overrides: Partial<Product> = {}): Product {
  return {
    id: 1,
    name: 'Говядина',
    description: 'Свежая говядина для крупных собак',
    category: null,
    price_per_kg: '890.00',
    stock_kg: '12.500',
    photo_url: null,
    is_active: true,
    in_stock: true,
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
    ...overrides,
  };
}

function renderCard(product: Product, onAdd = vi.fn()) {
  render(
    <MemoryRouter>
      <ProductCard product={product} onAdd={onAdd} />
    </MemoryRouter>,
  );
  return onAdd;
}

describe('ProductCard — товар в наличии', () => {
  it('показывает цену и остаток, кнопка активна', () => {
    renderCard(makeProduct());

    expect(screen.getByText('Говядина')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'В корзину' })).toBeEnabled();
    expect(screen.queryByText('Нет в наличии')).not.toBeInTheDocument();
  });

  it('добавляет товар с весом по умолчанию 1 кг', async () => {
    const user = userEvent.setup();
    const product = makeProduct();
    const onAdd = renderCard(product);

    await user.click(screen.getByRole('button', { name: 'В корзину' }));

    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(onAdd).toHaveBeenCalledWith(product, '1.000');
  });

  it('вес по умолчанию не превышает остаток', () => {
    expect(defaultAddWeight(makeProduct({ stock_kg: '0.400' }))).toBe('0.400');
    expect(defaultAddWeight(makeProduct({ stock_kg: '12.500' }))).toBe('1.000');
  });
});

describe('ProductCard — товара нет в наличии', () => {
  it('in_stock === false: бейдж «Нет в наличии» и заблокированная кнопка', () => {
    const product = makeProduct({ in_stock: false, stock_kg: '0.000' });
    const onAdd = renderCard(product);

    // Подпись встречается дважды: бейдж на фото и текст кнопки.
    expect(screen.getAllByText('Нет в наличии').length).toBeGreaterThanOrEqual(2);

    const button = screen.getByRole('button', { name: 'Нет в наличии' });
    expect(button).toBeDisabled();

    fireEvent.click(button);
    expect(onAdd).not.toHaveBeenCalled();
  });

  it('остаток меньше минимальных 0,1 кг тоже блокирует добавление', () => {
    const onAdd = renderCard(makeProduct({ in_stock: true, stock_kg: '0.050' }));

    expect(screen.getByRole('button', { name: 'Нет в наличии' })).toBeDisabled();
    expect(screen.getByText('Закончился')).toBeInTheDocument();
    expect(onAdd).not.toHaveBeenCalled();
  });
});

describe('ProductCard — подпись категории', () => {
  it('показывает русскую подпись категории', () => {
    renderCard(makeProduct({ category: 'horse-meat' }));

    expect(screen.getByText('Конина')).toBeInTheDocument();
  });

  it('у товара без категории лишней подписи нет', () => {
    // Название заведомо не совпадает с ярлыком категории, чтобы проверка была однозначной.
    renderCard(makeProduct({ name: 'Куриные шейки', category: null }));

    // Не должно появиться ни «Без категории», ни какого-либо ярлыка категории.
    expect(screen.queryByText('Без категории')).not.toBeInTheDocument();
    expect(screen.queryByText('Говядина')).not.toBeInTheDocument();
    expect(screen.getByText('Куриные шейки')).toBeInTheDocument();
  });
});
