/**
 * Поле адреса с подсказками: debounce, выбор мышью и клавиатурой,
 * состояния загрузки/пустого ответа/выключенного сервиса и разметка ARIA.
 */

import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AddressAutocomplete } from './AddressAutocomplete';
import type { AddressSuggestion, AddressSuggestions } from '../api/types';

const FIELD_ID = 'checkout-address';
const LABEL = 'Адрес доставки';
const LOADING_TEXT = 'Ищем адрес';

const solnechnaya: AddressSuggestion = {
  value: 'Омск, ул. 2-я Солнечная, 31А',
  city: 'Омск',
  street: '2-я Солнечная',
  house: '31А',
  postal_code: '644000',
  lat: '54.989342',
  lon: '73.368212',
};

const lenina: AddressSuggestion = {
  value: 'Омск, ул. Ленина, 10',
  city: 'Омск',
  street: 'Ленина',
  house: '10',
  postal_code: null,
  lat: null,
  lon: null,
};

const twoSuggestions: AddressSuggestions = {
  enabled: true,
  provider: 'photon',
  items: [solnechnaya, lenina],
};

function json(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

/** Сеть отвечает готовым payload. `_input` нужен, чтобы проверять URL запроса. */
function installFetch(payload: AddressSuggestions) {
  const fetchMock = vi.fn(async (_input: unknown) => json(payload));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** Управляемая обёртка: адрес живёт в состоянии формы, как в чекауте. */
function Harness({ onSelect, error }: { onSelect: (s: AddressSuggestion) => void; error?: string }) {
  const [value, setValue] = useState('');
  return (
    <AddressAutocomplete
      id={FIELD_ID}
      label={LABEL}
      value={value}
      error={error}
      placeholder="Улица, дом, квартира"
      onChange={setValue}
      onSelect={(suggestion) => {
        setValue(suggestion.value);
        onSelect(suggestion);
      }}
    />
  );
}

function renderField(error?: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const onSelect = vi.fn();
  const { container } = render(
    <QueryClientProvider client={queryClient}>
      <Harness onSelect={onSelect} error={error} />
    </QueryClientProvider>,
  );
  const input = screen.getByRole('combobox', { name: LABEL });
  return { onSelect, input, container };
}

/** Дождаться, что запрос ушёл и ответ уже разобран. */
async function waitForAnswer(fetchMock: ReturnType<typeof installFetch>) {
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  await waitFor(() => expect(screen.queryByText(LOADING_TEXT)).not.toBeInTheDocument());
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/**
 * Здесь ввод идёт через fireEvent, а не userEvent: асинхронная обёртка
 * testing-library ждёт настоящий setTimeout и умеет двигать только таймеры
 * jest, поэтому под vi.useFakeTimers() любой вызов userEvent зависает.
 */
describe('AddressAutocomplete — когда уходит запрос', () => {
  it('до 300 мс запрос не уходит', async () => {
    vi.useFakeTimers();
    const fetchMock = installFetch(twoSuggestions);
    const { input } = renderField();

    fireEvent.change(input, { target: { value: 'Омская' } });
    expect(fetchMock).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(299);
    });
    expect(fetchMock).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/v1/addresses/suggest');
  });

  it('каждая новая буква откладывает запрос', async () => {
    vi.useFakeTimers();
    const fetchMock = installFetch(twoSuggestions);
    const { input } = renderField();

    fireEvent.change(input, { target: { value: 'Омс' } });
    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    fireEvent.change(input, { target: { value: 'Омск' } });
    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    expect(fetchMock).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(100);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain('query=' + encodeURIComponent('Омск'));
  });

  it('ввод короче трёх символов подсказки не запрашивает', async () => {
    vi.useFakeTimers();
    const fetchMock = installFetch(twoSuggestions);
    const { input } = renderField();

    fireEvent.change(input, { target: { value: 'Ом' } });
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});

describe('AddressAutocomplete — выбор подсказки', () => {
  it('показывает список и отдаёт выбранную подсказку целиком', async () => {
    installFetch(twoSuggestions);
    const user = userEvent.setup();
    const { input, onSelect } = renderField();

    await user.type(input, 'Омск');

    const listbox = await screen.findByRole('listbox', { name: 'Подсказки адреса' });
    const options = within(listbox).getAllByRole('option');
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveTextContent('Омск, ул. 2-я Солнечная, 31А');

    await user.click(options[0]);

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(solnechnaya);
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument());
  });

  it('адрес можно дописать руками после выбора', async () => {
    installFetch(twoSuggestions);
    const user = userEvent.setup();
    const { input } = renderField();

    await user.type(input, 'Омск');
    const listbox = await screen.findByRole('listbox');
    await user.click(within(listbox).getAllByRole('option')[1]);

    expect(input).toHaveValue('Омск, ул. Ленина, 10');
    await user.type(input, ', кв. 5');
    expect(input).toHaveValue('Омск, ул. Ленина, 10, кв. 5');
  });

  it('стрелки двигают подсветку, Enter выбирает подсвеченный вариант', async () => {
    installFetch(twoSuggestions);
    const user = userEvent.setup();
    const { input, onSelect } = renderField();

    await user.type(input, 'Омск');
    await screen.findByRole('listbox');

    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true');
    expect(input).toHaveAttribute('aria-activedescendant', FIELD_ID + '-option-0');

    await user.keyboard('{ArrowDown}');
    expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true');
    expect(input).toHaveAttribute('aria-activedescendant', FIELD_ID + '-option-1');

    await user.keyboard('{ArrowUp}');
    expect(screen.getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{Enter}');
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(solnechnaya);
  });

  it('Escape закрывает список без выбора, ArrowDown открывает снова', async () => {
    installFetch(twoSuggestions);
    const user = userEvent.setup();
    const { input, onSelect } = renderField();

    await user.type(input, 'Омск');
    await screen.findByRole('listbox');

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(input).toHaveAttribute('aria-expanded', 'false');
    expect(onSelect).not.toHaveBeenCalled();

    await user.keyboard('{ArrowDown}');
    expect(await screen.findByRole('listbox')).toBeInTheDocument();
  });
});

describe('AddressAutocomplete — состояния сервиса', () => {
  it('показывает индикатор загрузки, пока идёт запрос', async () => {
    let release: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    const { input, container } = renderField();

    await user.type(input, 'Омск');

    expect(await screen.findByText(LOADING_TEXT)).toBeInTheDocument();
    expect(container.querySelector('.address-field__spinner')).not.toBeNull();
    // Пока грузим — «Ничего не найдено» показывать нельзя.
    expect(screen.queryByText('Ничего не найдено')).not.toBeInTheDocument();

    await act(async () => {
      release(json(twoSuggestions));
    });

    await waitFor(() => expect(screen.queryByText(LOADING_TEXT)).not.toBeInTheDocument());
    expect(container.querySelector('.address-field__spinner')).toBeNull();
  });

  it('пустой ответ — «Ничего не найдено» без списка', async () => {
    const fetchMock = installFetch({ enabled: true, provider: 'photon', items: [] });
    const user = userEvent.setup();
    const { input } = renderField();

    await user.type(input, 'Оммм');
    await waitForAnswer(fetchMock);

    expect(screen.getByText('Ничего не найдено')).toBeInTheDocument();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('enabled: false — обычное текстовое поле без списка и сообщений', async () => {
    const fetchMock = installFetch({ enabled: false, provider: 'none', items: [] });
    const user = userEvent.setup();
    const { input } = renderField();

    await user.type(input, 'Омск');
    await waitForAnswer(fetchMock);

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.queryByText('Ничего не найдено')).not.toBeInTheDocument();
    expect(input).toHaveValue('Омск');

    await user.type(input, ', 31');
    expect(input).toHaveValue('Омск, 31');
  });

  it('ошибка сети не ломает ввод', async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    const { input } = renderField();

    await user.type(input, 'Омск');
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.queryByText('Ничего не найдено')).not.toBeInTheDocument();

    await user.type(input, ', 31');
    expect(input).toHaveValue('Омск, 31');
  });
});

describe('AddressAutocomplete — доступность', () => {
  it('разметка соответствует паттерну combobox', async () => {
    installFetch(twoSuggestions);
    const user = userEvent.setup();
    const { input } = renderField();

    expect(screen.getByLabelText(LABEL)).toBe(input);
    expect(input).toHaveAttribute('aria-expanded', 'false');
    expect(input).toHaveAttribute('aria-controls', FIELD_ID + '-listbox');
    expect(input).toHaveAttribute('aria-autocomplete', 'list');
    expect(input).toHaveAttribute('autocomplete', 'off');

    await user.type(input, 'Омск');

    const listbox = await screen.findByRole('listbox');
    expect(listbox).toHaveAttribute('id', FIELD_ID + '-listbox');
    expect(input).toHaveAttribute('aria-expanded', 'true');

    const options = within(listbox).getAllByRole('option');
    expect(options[0].tagName).toBe('LI');
    expect(options[0]).toHaveAttribute('id', FIELD_ID + '-option-0');
    expect(screen.getByText('Найдено вариантов: 2')).toBeInTheDocument();
  });

  it('ошибка поля помечается aria-invalid и текстом', () => {
    installFetch(twoSuggestions);
    const { input } = renderField('Укажите адрес доставки');

    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input.className).toContain('has-error');
    expect(screen.getByText('Укажите адрес доставки')).toBeInTheDocument();
  });
});
