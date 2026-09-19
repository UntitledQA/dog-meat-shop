/**
 * Типы API — строго по разделу 7 docs/CONTRACTS.md.
 *
 * ВАЖНО: все денежные (Numeric(10,2)) и весовые (Numeric(10,3)) поля приходят
 * и отправляются СТРОКАМИ ("890.00", "12.500") — см. раздел 2 контракта.
 * Разбирать только через helpers из src/lib/money.ts.
 */

/** Decimal, сериализованный строкой. Алиас для читаемости. */
export type DecimalString = string;

/** Page<T> */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** User */
export interface User {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  is_admin: boolean;
  created_at: string;
}

/** AppSettings */
export interface AppSettings {
  delivery_price: DecimalString;
  pickup_address: string;
  min_weight_kg: DecimalString;
  weight_step_kg: DecimalString;
  currency: string;
  payment_note: string;
}

/** Одна подсказка адреса от GET /api/v1/addresses/suggest */
export interface AddressSuggestion {
  value: string;
  city?: string | null;
  street?: string | null;
  house?: string | null;
  postal_code?: string | null;
  /** Координаты приходят строками (Decimal сериализуется строкой). */
  lat?: string | null;
  lon?: string | null;
}

/** Ответ GET /api/v1/addresses/suggest */
export interface AddressSuggestions {
  enabled: boolean;
  provider: string;
  items: AddressSuggestion[];
}

/** Категории товаров (slug). Русские подписи — в src/lib/categories.ts. */
export type ProductCategory =
  | 'beef'
  | 'veal'
  | 'horse-meat'
  | 'duck'
  | 'fish'
  | 'dried-treats';

/** Product */
export interface Product {
  id: number;
  name: string;
  description: string | null;
  category: ProductCategory | null;
  price_per_kg: DecimalString;
  stock_kg: DecimalString;
  photo_url: string | null;
  is_active: boolean;
  in_stock: boolean;
  created_at: string;
  updated_at: string;
}

export type OrderStatus = 'confirmed' | 'delivering' | 'completed' | 'cancelled';

export type DeliveryType = 'delivery' | 'pickup';

/** Позиция заказа */
export interface OrderItem {
  id: number;
  product_id: number | null;
  product_name: string;
  weight_kg: DecimalString;
  price_per_kg: DecimalString;
  line_total: DecimalString;
}

/** Order */
export interface Order {
  id: number;
  order_number: string;
  status: OrderStatus;
  status_label: string;
  delivery_type: DeliveryType;
  customer_name: string;
  phone: string;
  address: string | null;
  address_city: string | null;
  address_street: string | null;
  address_house: string | null;
  address_postal_code: string | null;
  address_lat: string | null;
  address_lon: string | null;
  delivery_date: string | null;
  comment: string | null;
  subtotal: DecimalString;
  delivery_price: DecimalString;
  total: DecimalString;
  payment_method: string;
  items: OrderItem[];
  created_at: string;
  updated_at: string;
}

/** AdminOrder = Order + user */
export interface AdminOrder extends Order {
  user: User;
}

/** Тело POST /api/v1/orders */
export interface OrderCreateItem {
  product_id: number;
  weight_kg: DecimalString;
}

export interface OrderCreate {
  items: OrderCreateItem[];
  delivery_type: DeliveryType;
  customer_name: string;
  phone: string;
  address?: string | null;
  address_city?: string | null;
  address_street?: string | null;
  address_house?: string | null;
  address_postal_code?: string | null;
  address_lat?: string | null;
  address_lon?: string | null;
  delivery_date?: string | null;
  comment?: string | null;
}

/** Тело POST /api/v1/admin/products */
export interface ProductCreate {
  name: string;
  description?: string | null;
  category?: ProductCategory | null;
  price_per_kg: DecimalString;
  stock_kg: DecimalString;
  photo_url?: string | null;
  is_active?: boolean;
}

/** Тело PATCH /api/v1/admin/products/{id} — частичное обновление */
export type ProductUpdate = Partial<ProductCreate>;

/** Ответ POST /api/v1/admin/uploads/photo */
export interface PhotoUploadResponse {
  photo_url: string;
}

/** Единый формат ошибки (раздел 3 контракта) */
export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

/** details.items для insufficient_stock */
export interface InsufficientStockItem {
  product_id: number;
  product_name: string;
  requested_kg: DecimalString;
  available_kg: DecimalString;
}

/** details.fields[] для validation_error */
export interface ValidationErrorField {
  field?: string;
  loc?: string[];
  message?: string;
  msg?: string;
}

/** Параметры листингов */
export interface PageParams {
  limit?: number;
  offset?: number;
}

/** Параметры каталога покупателя: пагинация + необязательный фильтр по категории. */
export interface CatalogListParams extends PageParams {
  category?: ProductCategory | null;
}

export interface AdminProductListParams extends PageParams {
  include_inactive?: boolean;
  search?: string;
  category?: ProductCategory | null;
}

export interface AdminOrderListParams extends PageParams {
  status?: OrderStatus | '';
}
