/** Хуки TanStack Query поверх src/api/endpoints.ts. */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query';
import { ApiError } from './client';
import * as api from './endpoints';
import type {
  AddressSuggestions,
  AdminOrder,
  AdminOrderListParams,
  AdminProductListParams,
  AppSettings,
  Order,
  OrderCreate,
  OrderStatus,
  Page,
  PageParams,
  Product,
  ProductCreate,
  ProductUpdate,
  User,
} from './types';

/** Короче этого подсказки адреса не запрашиваем — сервис вернёт мусор. */
export const ADDRESS_SUGGEST_MIN_LENGTH = 3;

/** Длиннее бэкенд отвечает 422: `query` у /addresses/suggest ограничен 200. */
const ADDRESS_SUGGEST_MAX_LENGTH = 200;

/** Сколько вариантов просим у сервиса подсказок (бэкенд ограничивает 1..10). */
const ADDRESS_SUGGEST_LIMIT = 7;

export const queryKeys = {
  me: ['me'] as const,
  settings: ['settings'] as const,
  addressSuggestions: (query: string, limit: number) =>
    ['addresses', 'suggest', query, limit] as const,
  catalog: (params: PageParams) => ['catalog', params] as const,
  product: (id: number) => ['product', id] as const,
  myOrders: (params: PageParams) => ['orders', params] as const,
  myOrder: (id: number) => ['order', id] as const,
  adminProducts: (params: AdminProductListParams) => ['admin', 'products', params] as const,
  adminOrders: (params: AdminOrderListParams) => ['admin', 'orders', params] as const,
  adminOrder: (id: number) => ['admin', 'order', id] as const,
};

/** Не повторять запрос, если проблема в правах или данных. */
function retryPolicy(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError) {
    if (error.status >= 400 && error.status < 500) return false;
  }
  return failureCount < 2;
}

export function useMe(): UseQueryResult<User, unknown> {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: api.getMe,
    retry: retryPolicy,
    staleTime: 5 * 60 * 1000,
  });
}

export function useSettings(): UseQueryResult<AppSettings, unknown> {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: api.getSettings,
    retry: retryPolicy,
    staleTime: 10 * 60 * 1000,
  });
}

/**
 * Подсказки адреса. Запрос уходит только при достаточно длинном вводе,
 * `enabled` позволяет вызывающему коду дополнительно погасить его (например,
 * пока выпадающий список закрыт).
 */
export function useAddressSuggestions(
  query: string,
  options: { enabled?: boolean; limit?: number } = {},
): UseQueryResult<AddressSuggestions, unknown> {
  const text = query.trim();
  const limit = options.limit ?? ADDRESS_SUGGEST_LIMIT;
  return useQuery({
    queryKey: queryKeys.addressSuggestions(text, limit),
    queryFn: ({ signal }) => api.suggestAddresses(text, { limit, signal }),
    enabled:
      (options.enabled ?? true) &&
      text.length >= ADDRESS_SUGGEST_MIN_LENGTH &&
      text.length <= ADDRESS_SUGGEST_MAX_LENGTH,
    retry: retryPolicy,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCatalog(params: PageParams = {}): UseQueryResult<Page<Product>, unknown> {
  return useQuery({
    queryKey: queryKeys.catalog(params),
    queryFn: () => api.getCatalog(params),
    retry: retryPolicy,
  });
}

export function useProduct(id: number): UseQueryResult<Product, unknown> {
  return useQuery({
    queryKey: queryKeys.product(id),
    queryFn: () => api.getProduct(id),
    enabled: Number.isFinite(id) && id > 0,
    retry: retryPolicy,
  });
}

export function useMyOrders(params: PageParams = {}): UseQueryResult<Page<Order>, unknown> {
  return useQuery({
    queryKey: queryKeys.myOrders(params),
    queryFn: () => api.getMyOrders(params),
    retry: retryPolicy,
  });
}

export function useMyOrder(id: number): UseQueryResult<Order, unknown> {
  return useQuery({
    queryKey: queryKeys.myOrder(id),
    queryFn: () => api.getMyOrder(id),
    enabled: Number.isFinite(id) && id > 0,
    retry: retryPolicy,
  });
}

export function useCreateOrder(): UseMutationResult<Order, unknown, OrderCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OrderCreate) => api.createOrder(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['orders'] });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
    },
  });
}

/* ------------------------------ Администратор ------------------------------ */

export function useAdminProducts(
  params: AdminProductListParams = {},
): UseQueryResult<Page<Product>, unknown> {
  return useQuery({
    queryKey: queryKeys.adminProducts(params),
    queryFn: () => api.getAdminProducts(params),
    retry: retryPolicy,
  });
}

export function useAdminOrders(
  params: AdminOrderListParams = {},
): UseQueryResult<Page<AdminOrder>, unknown> {
  return useQuery({
    queryKey: queryKeys.adminOrders(params),
    queryFn: () => api.getAdminOrders(params),
    retry: retryPolicy,
  });
}

export function useAdminOrder(id: number): UseQueryResult<AdminOrder, unknown> {
  return useQuery({
    queryKey: queryKeys.adminOrder(id),
    queryFn: () => api.getAdminOrder(id),
    enabled: Number.isFinite(id) && id > 0,
    retry: retryPolicy,
  });
}

export function useCreateProduct(): UseMutationResult<Product, unknown, ProductCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProductCreate) => api.createProduct(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'products'] });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
    },
  });
}

export function useUpdateProduct(): UseMutationResult<
  Product,
  unknown,
  { id: number; payload: ProductUpdate }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ProductUpdate }) =>
      api.updateProduct(id, payload),
    onSuccess: (product) => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'products'] });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
      queryClient.setQueryData(queryKeys.product(product.id), product);
    },
  });
}

export function useToggleProductActive(): UseMutationResult<
  Product,
  unknown,
  { id: number; nextActive: boolean }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, nextActive }: { id: number; nextActive: boolean }) =>
      nextActive ? api.restoreProduct(id) : api.archiveProduct(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'products'] });
      void queryClient.invalidateQueries({ queryKey: ['catalog'] });
    },
  });
}

export function useUpdateOrderStatus(): UseMutationResult<
  AdminOrder,
  unknown,
  { id: number; status: OrderStatus }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: OrderStatus }) =>
      api.updateOrderStatus(id, status),
    onSuccess: (order) => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'orders'] });
      void queryClient.invalidateQueries({ queryKey: ['orders'] });
      queryClient.setQueryData(queryKeys.adminOrder(order.id), order);
    },
  });
}
