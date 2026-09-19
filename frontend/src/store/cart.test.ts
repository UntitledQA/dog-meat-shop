import { beforeEach, describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';
import {
  lineTotal,
  selectItemsCount,
  selectSubtotal,
  useCartCount,
  useCartStore,
} from './cart';
import type { Product } from '../api/types';

function makeProduct(overrides: Partial<Product> = {}): Product {
  return {
    id: 1,
    name: 'Говядина',
    description: null,
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

const beef = makeProduct();
const chicken = makeProduct({ id: 2, name: 'Курица', price_per_kg: '450.00', stock_kg: '3.000' });

describe('стор корзины', () => {
  beforeEach(() => {
    useCartStore.setState({ items: [] });
  });

  it('add добавляет позицию со снимком названия, цены и веса', () => {
    useCartStore.getState().add(beef, '1.500');

    const items = useCartStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      productId: 1,
      name: 'Говядина',
      pricePerKg: '890.00',
      weightKg: '1.500',
    });
  });

  it('add складывает вес при повторном добавлении того же товара', () => {
    const cart = useCartStore.getState();
    cart.add(beef, '1.000');
    cart.add(beef, '0.500');

    expect(useCartStore.getState().items).toHaveLength(1);
    expect(useCartStore.getState().items[0].weightKg).toBe('1.500');
  });

  it('add не даёт превысить остаток товара', () => {
    useCartStore.getState().add(chicken, '10.000');
    expect(useCartStore.getState().items[0].weightKg).toBe('3.000');
  });

  it('add игнорирует нулевой вес', () => {
    useCartStore.getState().add(beef, '0');
    expect(useCartStore.getState().items).toHaveLength(0);
  });

  it('updateWeight меняет вес и канонизирует его', () => {
    const cart = useCartStore.getState();
    cart.add(beef, '1.000');
    cart.updateWeight(1, '2,25');

    expect(useCartStore.getState().items[0].weightKg).toBe('2.250');
  });

  it('remove удаляет только выбранную позицию', () => {
    const cart = useCartStore.getState();
    cart.add(beef, '1.000');
    cart.add(chicken, '1.000');
    cart.remove(1);

    const items = useCartStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].productId).toBe(2);
  });

  it('clear опустошает корзину', () => {
    const cart = useCartStore.getState();
    cart.add(beef, '1.000');
    cart.add(chicken, '1.000');
    cart.clear();

    expect(useCartStore.getState().items).toEqual([]);
  });

  it('счётчик позиций считает товары, а не килограммы', () => {
    const cart = useCartStore.getState();
    cart.add(beef, '2.500');
    expect(selectItemsCount(useCartStore.getState())).toBe(1);

    cart.add(chicken, '1.000');
    expect(selectItemsCount(useCartStore.getState())).toBe(2);

    cart.remove(2);
    expect(selectItemsCount(useCartStore.getState())).toBe(1);
  });

  it('хук useCartCount отражает изменения стора', () => {
    const { result, rerender } = renderHook(() => useCartCount());
    expect(result.current).toBe(0);

    useCartStore.getState().add(beef, '1.000');
    rerender();
    expect(result.current).toBe(1);
  });

  it('считает стоимость позиции и товаров', () => {
    const cart = useCartStore.getState();
    cart.add(beef, '0.500'); // 445.00
    cart.add(chicken, '1.200'); // 540.00

    expect(lineTotal(useCartStore.getState().items[0])).toBe('445.00');
    expect(selectSubtotal(useCartStore.getState())).toBe('985.00');
  });
});
