/**
 * Дымовой тест маршрутов: каждая страница из App.tsx должна монтироваться
 * и показывать осмысленный контент на замоканных ответах API.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { ToastProvider } from './components/ToastProvider';
import { useCartStore } from './store/cart';
import type { AdminOrder, AppSettings, Order, Product, User } from './api/types';

const admin: User = {
  id: 1,
  telegram_id: 100500,
  username: 'admin',
  first_name: 'Админ',
  last_name: null,
  phone: '+79991234567',
  is_admin: true,
  created_at: '2026-09-01T10:00:00Z',
};

const settings: AppSettings = {
  delivery_price: '300.00',
  pickup_address: 'ул. Ленина, 1',
  min_weight_kg: '0.100',
  weight_step_kg: '0.100',
  currency: 'RUB',
  payment_note: 'Оплата при получении',
};

const product: Product = {
  id: 1,
  name: 'Говядина',
  description: 'Свежая говядина',
  category: null,
  price_per_kg: '890.00',
  stock_kg: '12.500',
  photo_url: null,
  is_active: true,
  in_stock: true,
  created_at: '2026-09-01T10:00:00Z',
  updated_at: '2026-09-01T10:00:00Z',
};

const order: Order = {
  id: 1,
  order_number: 'ORD-20260907-00001',
  status: 'confirmed',
  status_label: 'Подтверждён',
  delivery_type: 'delivery',
  customer_name: 'Иван',
  phone: '+79991234567',
  address: 'ул. Ленина, 1',
  address_city: null,
  address_street: null,
  address_house: null,
  address_postal_code: null,
  address_lat: null,
  address_lon: null,
  delivery_date: '2026-09-09',
  comment: null,
  subtotal: '1780.00',
  delivery_price: '300.00',
  total: '2080.00',
  payment_method: 'cash_on_delivery',
  items: [
    {
      id: 1,
      product_id: 1,
      product_name: 'Говядина',
      weight_kg: '2.000',
      price_per_kg: '890.00',
      line_total: '1780.00',
    },
  ],
  created_at: '2026-09-07T10:00:00Z',
  updated_at: '2026-09-07T10:00:00Z',
};

const adminOrder: AdminOrder = { ...order, user: admin };

function page<T>(items: T[]) {
  return { items, total: items.length, limit: 20, offset: 0 };
}

function json(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

function installFetch() {
  const fetchMock = vi.fn(async (input: unknown) => {
    const url = String(input);
    if (url.includes('/api/v1/me')) return json(admin);
    if (url.includes('/api/v1/settings')) return json(settings);
    if (url.includes('/api/v1/catalog/1')) return json(product);
    if (url.includes('/api/v1/catalog')) return json(page([product]));
    if (url.includes('/api/v1/admin/products')) return json(page([product]));
    if (url.includes('/api/v1/admin/orders/1')) return json(adminOrder);
    if (url.includes('/api/v1/admin/orders')) return json(page([adminOrder]));
    if (url.includes('/api/v1/orders/1')) return json(order);
    if (url.includes('/api/v1/orders')) return json(page([order]));
    return json({ error: { code: 'not_found', message: 'Не найдено', details: {} } }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function renderRoute(path: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <ToastProvider>
          <App />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('маршруты покупателя', () => {
  beforeEach(() => {
    installFetch();
    window.scrollTo = vi.fn();
    useCartStore.setState({ items: [] });
  });

  it('/ — каталог показывает товары', async () => {
    renderRoute('/');
    // «Говядина» встречается и как название товара, и как чип категории,
    // поэтому проверяем уникальную кнопку карточки.
    expect(await screen.findByRole('button', { name: 'В корзину' })).toBeEnabled();
  });

  it('/ — есть фильтр категорий, по умолчанию активна «Все»', async () => {
    renderRoute('/');
    await screen.findByRole('button', { name: 'В корзину' });

    expect(screen.getByRole('button', { name: 'Все' })).toHaveAttribute('aria-pressed', 'true');
    // Чипы категорий отрисованы с русскими подписями.
    expect(screen.getByRole('button', { name: 'Телятина' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Сушёные лакомства' })).toBeInTheDocument();
  });

  it('/?category=beef — deep-link отмечает чип и уходит в запрос каталога', async () => {
    const fetchMock = installFetch();
    renderRoute('/?category=beef');
    await screen.findByRole('button', { name: 'В корзину' });

    // Чип категории активен, «Все» — нет.
    expect(screen.getByRole('button', { name: 'Говядина' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Все' })).toHaveAttribute('aria-pressed', 'false');

    // В запрос каталога передан category=beef.
    const catalogCall = fetchMock.mock.calls.find(
      ([url]) => String(url).includes('/api/v1/catalog') && String(url).includes('category=beef'),
    );
    expect(catalogCall).toBeDefined();
  });

  it('/?category=НЕВАЛИД — неизвестный slug трактуется как «Все»', async () => {
    const fetchMock = installFetch();
    renderRoute('/?category=not-a-real-category');
    await screen.findByRole('button', { name: 'В корзину' });

    expect(screen.getByRole('button', { name: 'Все' })).toHaveAttribute('aria-pressed', 'true');

    // Запрос каталога ушёл без параметра category.
    const catalogCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes('/api/v1/catalog'),
    );
    expect(catalogCall).toBeDefined();
    expect(String(catalogCall?.[0])).not.toContain('category=');
  });

  it('/ — клик по чипу фильтрует каталог по категории', async () => {
    const user = userEvent.setup();
    const fetchMock = installFetch();
    renderRoute('/');
    await screen.findByRole('button', { name: 'В корзину' });

    await user.click(screen.getByRole('button', { name: 'Утка' }));

    expect(screen.getByRole('button', { name: 'Утка' })).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url]) =>
          String(url).includes('/api/v1/catalog') && String(url).includes('category=duck'),
      );
      expect(call).toBeDefined();
    });
  });

  it('/product/:id — карточка товара с выбором веса', async () => {
    renderRoute('/product/1');
    expect(await screen.findByRole('button', { name: /Добавить в корзину/ })).toBeEnabled();
    expect(screen.getByLabelText('Вес в килограммах')).toBeInTheDocument();
  });

  it('/cart — пустая корзина предлагает каталог', async () => {
    renderRoute('/cart');
    expect(await screen.findByText('Корзина пуста')).toBeInTheDocument();
  });

  it('/cart — позиция показывает свою стоимость', async () => {
    useCartStore.getState().add(product, '2.000');
    renderRoute('/cart');
    expect(await screen.findByRole('button', { name: /Оформить заказ/ })).toBeEnabled();
  });

  it('/checkout — форма оформления с итогом', async () => {
    useCartStore.getState().add(product, '2.000');
    renderRoute('/checkout');
    expect(await screen.findByRole('button', { name: /Подтвердить заказ/ })).toBeInTheDocument();
    expect(screen.getByLabelText('Адрес доставки')).toBeInTheDocument();
    // Выбора интервала времени в форме больше нет.
    expect(screen.queryByText('Интервал времени')).not.toBeInTheDocument();
    // Постоянный блок с условиями доставки и графиком работы.
    expect(screen.getByText('Условия доставки')).toBeInTheDocument();
    expect(screen.getByText('График работы')).toBeInTheDocument();
    expect(screen.getByText('ВТ')).toBeInTheDocument();
  });

  it('/checkout — выбранная подсказка адреса уходит в заказ', async () => {
    const user = userEvent.setup();
    const suggestion = {
      value: 'Омск, ул. 2-я Солнечная, 31А',
      city: 'Омск',
      street: '2-я Солнечная',
      house: '31А',
      postal_code: '644073',
      lat: '54.989342',
      lon: '73.368212',
    };

    // Подсказки и создание заказа поверх общего мока.
    const fetchMock = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/addresses/suggest')) {
        return json({ enabled: true, provider: 'photon', items: [suggestion] });
      }
      if (url.includes('/api/v1/orders') && init?.method === 'POST') {
        return json({ ...order, address: suggestion.value }, 201);
      }
      if (url.includes('/api/v1/me')) return json(admin);
      if (url.includes('/api/v1/settings')) return json(settings);
      return json({ error: { code: 'not_found', message: 'Не найдено', details: {} } }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);

    useCartStore.getState().add(product, '2.000');
    renderRoute('/checkout');

    await screen.findByRole('button', { name: /Подтвердить заказ/ });
    // Имя и телефон подставляются из профиля Telegram — очищаем перед вводом.
    const name = screen.getByLabelText('Имя');
    await user.clear(name);
    await user.type(name, 'Иван');
    const phone = screen.getByLabelText('Телефон');
    await user.clear(phone);
    await user.type(phone, '+79991234567');
    await user.type(screen.getByLabelText('Адрес доставки'), 'Солнечная');

    // Подсказка приходит после задержки в 300 мс.
    const option = await screen.findByRole('option', { name: suggestion.value }, { timeout: 3000 });
    await user.click(option);

    await user.click(screen.getByRole('button', { name: /Подтвердить заказ/ }));

    const post = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).includes('/api/v1/orders') && (init as RequestInit | undefined)?.method === 'POST',
    );
    expect(post).toBeDefined();
    const body = JSON.parse(String((post?.[1] as RequestInit).body));
    expect(body.address).toBe(suggestion.value);
    expect(body.address_city).toBe('Омск');
    expect(body.address_street).toBe('2-я Солнечная');
    expect(body.address_house).toBe('31А');
    expect(body.address_postal_code).toBe('644073');
    // Координаты остаются строками — Decimal в JSON сериализуется строкой.
    expect(body.address_lat).toBe('54.989342');
    expect(body.address_lon).toBe('73.368212');
    // Интервала времени в теле запроса быть не должно.
    expect(body).not.toHaveProperty('delivery_time');
  });

  it('/orders — список заказов', async () => {
    renderRoute('/orders');
    expect(await screen.findByText('ORD-20260907-00001')).toBeInTheDocument();
  });

  it('/orders/:id — детали заказа', async () => {
    renderRoute('/orders/1');
    expect(await screen.findByText('Состав заказа')).toBeInTheDocument();
  });
});

describe('маршруты администратора', () => {
  beforeEach(() => {
    installFetch();
    window.scrollTo = vi.fn();
    useCartStore.setState({ items: [] });
  });

  it('/admin — плитки и сводка', async () => {
    renderRoute('/admin');
    expect(await screen.findByText('Сводка')).toBeInTheDocument();
    // Плитки-ссылки на разделы админки (подпись «Заказы» есть ещё и в нижней навигации).
    expect(screen.getByText('Статусы и отмена')).toBeInTheDocument();
    expect(screen.getByText('Цены, остатки, фото, скрытие')).toBeInTheDocument();
  });

  it('/admin/products — список товаров с редактированием', async () => {
    renderRoute('/admin/products');
    expect(await screen.findByRole('link', { name: 'Изменить' })).toBeInTheDocument();
  });

  it('/admin/products/new — пустая форма создания', async () => {
    renderRoute('/admin/products/new');
    expect(await screen.findByRole('button', { name: 'Добавить товар' })).toBeInTheDocument();
    expect(screen.getByLabelText('Название')).toHaveValue('');
  });

  it('/admin/products/:id — форма заполнена данными товара', async () => {
    renderRoute('/admin/products/1');
    expect(await screen.findByDisplayValue('Говядина')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Сохранить изменения' })).toBeInTheDocument();
  });

  it('/admin/orders — список заказов с фильтром', async () => {
    renderRoute('/admin/orders');
    expect(await screen.findByText('ORD-20260907-00001')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подтверждён' })).toBeInTheDocument();
  });

  it('/admin/orders/:id — управление статусом', async () => {
    renderRoute('/admin/orders/1');
    expect(await screen.findByText('Управление статусом')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Отменить заказ' })).toBeInTheDocument();
  });
});
