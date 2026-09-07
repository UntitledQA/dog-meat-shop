/**
 * Корзина: Zustand + persist в localStorage.
 *
 * Хранится product_id, снимок названия/цены/фото (на случай, если товар изменится)
 * и вес. Вес — ВСЕГДА каноническая строка с 3 знаками («1.500»), как того требует
 * контракт для Numeric(10,3). Корзина переживает переходы между страницами
 * и перезагрузку приложения.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import {
  DEFAULT_MIN_WEIGHT,
  WEIGHT_SCALE,
  calcCartTotal,
  calcLineTotal,
  clampWeight,
  fromScaled,
  toGrams,
  toWeightString,
} from '../lib/money';
import type { Product } from '../api/types';

export interface CartItem {
  productId: number;
  name: string;
  /** Снимок цены на момент добавления, «890.00». Итог всё равно считает бэкенд. */
  pricePerKg: string;
  photoUrl: string | null;
  /** Вес в килограммах, каноническая строка «1.500». */
  weightKg: string;
}

export interface CartState {
  items: CartItem[];
  add: (product: Product, weightKg: string | number) => void;
  updateWeight: (productId: number, weightKg: string | number) => void;
  remove: (productId: number) => void;
  clear: () => void;
}

const STORAGE_KEY = 'meat-cart-v1';

export const useCartStore = create<CartState>()(
  persist(
    (set) => ({
      items: [],

      add: (product, weightKg) => {
        const added = toGrams(weightKg);
        if (added <= 0) return;

        set((state) => {
          const existing = state.items.find((item) => item.productId === product.id);
          const maxGrams = toGrams(product.stock_kg);

          if (existing) {
            const merged = fromScaled(toGrams(existing.weightKg) + added, WEIGHT_SCALE);
            const next = clampWeight(merged, {
              min: DEFAULT_MIN_WEIGHT,
              max: fromScaled(maxGrams, WEIGHT_SCALE),
            });
            return {
              items: state.items.map((item) =>
                item.productId === product.id
                  ? {
                      ...item,
                      name: product.name,
                      pricePerKg: product.price_per_kg,
                      photoUrl: product.photo_url,
                      weightKg: next,
                    }
                  : item,
              ),
            };
          }

          const item: CartItem = {
            productId: product.id,
            name: product.name,
            pricePerKg: product.price_per_kg,
            photoUrl: product.photo_url,
            weightKg: clampWeight(weightKg, { min: DEFAULT_MIN_WEIGHT, max: product.stock_kg }),
          };
          return { items: [...state.items, item] };
        });
      },

      updateWeight: (productId, weightKg) => {
        set((state) => ({
          items: state.items.map((item) =>
            item.productId === productId ? { ...item, weightKg: toWeightString(weightKg) } : item,
          ),
        }));
      },

      remove: (productId) => {
        set((state) => ({ items: state.items.filter((item) => item.productId !== productId) }));
      },

      clear: () => set({ items: [] }),
    }),
    {
      name: STORAGE_KEY,
      version: 1,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ items: state.items }) as CartState,
    },
  ),
);

/* --------------------------------- Селекторы -------------------------------- */

/** Количество позиций в корзине (не суммарный вес). */
export function selectItemsCount(state: CartState): number {
  return state.items.length;
}

/** Стоимость товаров без доставки, «1780.00». */
export function selectSubtotal(state: CartState): string {
  return calcCartTotal(
    state.items.map((item) => ({ weightKg: item.weightKg, pricePerKg: item.pricePerKg })),
    0,
  ).subtotal;
}

/** Позиция корзины по товару. */
export function selectItem(state: CartState, productId: number): CartItem | undefined {
  return state.items.find((item) => item.productId === productId);
}

/** Стоимость одной позиции, «1780.00». */
export function lineTotal(item: CartItem): string {
  return calcLineTotal(item.weightKg, item.pricePerKg);
}

/** Хук: количество позиций (для бейджа в навигации). */
export function useCartCount(): number {
  return useCartStore(selectItemsCount);
}

/** Хук: стоимость товаров. */
export function useCartSubtotal(): string {
  return useCartStore(selectSubtotal);
}
