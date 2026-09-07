/**
 * Функции на каждый эндпоинт из раздела 7 контракта.
 * Компоненты обращаются к API только через этот модуль.
 */

import { API_PREFIX, request } from './client';
import type {
  AdminOrder,
  AdminOrderListParams,
  AdminProductListParams,
  AppSettings,
  Order,
  OrderCreate,
  OrderStatus,
  Page,
  PageParams,
  PhotoUploadResponse,
  Product,
  ProductCreate,
  ProductUpdate,
  User,
} from './types';

const p = (path: string): string => API_PREFIX + path;

/* -------------------------------- Покупатель ------------------------------- */

/** POST /api/v1/auth/telegram */
export function authTelegram(): Promise<User> {
  return request<User>(p('/auth/telegram'), { method: 'POST' });
}

/** GET /api/v1/me */
export function getMe(): Promise<User> {
  return request<User>(p('/me'));
}

/** GET /api/v1/settings */
export function getSettings(): Promise<AppSettings> {
  return request<AppSettings>(p('/settings'));
}

/** GET /api/v1/catalog */
export function getCatalog(params: PageParams = {}): Promise<Page<Product>> {
  return request<Page<Product>>(p('/catalog'), {
    query: { limit: params.limit, offset: params.offset },
  });
}

/** GET /api/v1/catalog/{id} */
export function getProduct(id: number): Promise<Product> {
  return request<Product>(p('/catalog/' + id));
}

/** POST /api/v1/orders */
export function createOrder(payload: OrderCreate): Promise<Order> {
  return request<Order>(p('/orders'), { method: 'POST', body: payload });
}

/** GET /api/v1/orders */
export function getMyOrders(params: PageParams = {}): Promise<Page<Order>> {
  return request<Page<Order>>(p('/orders'), {
    query: { limit: params.limit, offset: params.offset },
  });
}

/** GET /api/v1/orders/{id} */
export function getMyOrder(id: number): Promise<Order> {
  return request<Order>(p('/orders/' + id));
}

/* ------------------------------ Администратор ------------------------------ */

/** GET /api/v1/admin/products */
export function getAdminProducts(params: AdminProductListParams = {}): Promise<Page<Product>> {
  return request<Page<Product>>(p('/admin/products'), {
    query: {
      include_inactive: params.include_inactive,
      search: params.search,
      limit: params.limit,
      offset: params.offset,
    },
  });
}

/** POST /api/v1/admin/products */
export function createProduct(payload: ProductCreate): Promise<Product> {
  return request<Product>(p('/admin/products'), { method: 'POST', body: payload });
}

/** PATCH /api/v1/admin/products/{id} */
export function updateProduct(id: number, payload: ProductUpdate): Promise<Product> {
  return request<Product>(p('/admin/products/' + id), { method: 'PATCH', body: payload });
}

/** POST /api/v1/admin/products/{id}/archive */
export function archiveProduct(id: number): Promise<Product> {
  return request<Product>(p('/admin/products/' + id + '/archive'), { method: 'POST' });
}

/** POST /api/v1/admin/products/{id}/restore */
export function restoreProduct(id: number): Promise<Product> {
  return request<Product>(p('/admin/products/' + id + '/restore'), { method: 'POST' });
}

/** POST /api/v1/admin/products/{id}/photo — multipart `file` */
export function uploadProductPhoto(id: number, file: File): Promise<Product> {
  const formData = new FormData();
  formData.append('file', file);
  return request<Product>(p('/admin/products/' + id + '/photo'), { method: 'POST', formData });
}

/** POST /api/v1/admin/uploads/photo — multipart `file` */
export function uploadPhoto(file: File): Promise<PhotoUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return request<PhotoUploadResponse>(p('/admin/uploads/photo'), { method: 'POST', formData });
}

/** GET /api/v1/admin/orders */
export function getAdminOrders(params: AdminOrderListParams = {}): Promise<Page<AdminOrder>> {
  return request<Page<AdminOrder>>(p('/admin/orders'), {
    query: {
      status: params.status,
      limit: params.limit,
      offset: params.offset,
    },
  });
}

/** GET /api/v1/admin/orders/{id} */
export function getAdminOrder(id: number): Promise<AdminOrder> {
  return request<AdminOrder>(p('/admin/orders/' + id));
}

/** PATCH /api/v1/admin/orders/{id}/status */
export function updateOrderStatus(id: number, status: OrderStatus): Promise<AdminOrder> {
  return request<AdminOrder>(p('/admin/orders/' + id + '/status'), {
    method: 'PATCH',
    body: { status },
  });
}
