/**
 * Поле ввода адреса с подсказками GET /api/v1/addresses/suggest.
 *
 * Подсказки — необязательная надстройка над обычным текстовым полем: если
 * сервис выключен (`enabled: false`) или недоступен, поле продолжает работать
 * как простой ввод, без списка и без сообщений об ошибке. Адрес всегда можно
 * дописать или исправить руками, в том числе после выбора варианта.
 *
 * Разметка — паттерн ARIA 1.2 combobox: фокус не уходит из поля, стрелки
 * двигают подсветку, Enter выбирает подсвеченный вариант, Escape закрывает
 * список. Количество найденного объявляется в скрытой aria-live области.
 *
 * Компонент не меняет `value` сам: при выборе он зовёт `onSelect`, а записать
 * `suggestion.value` в форму (вместе с городом, улицей и координатами) —
 * задача родителя.
 */

import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { ADDRESS_SUGGEST_MIN_LENGTH, useAddressSuggestions } from '../api/queries';
import type { AddressSuggestion } from '../api/types';
import { haptic } from '../telegram/webapp';

/** Пауза между вводом и запросом подсказок, мс. */
const DEBOUNCE_MS = 300;

export interface AddressAutocompleteProps {
  /** id инпута: к нему привязаны label, listbox и варианты. */
  id: string;
  label: string;
  value: string;
  error?: string;
  placeholder?: string;
  /** Свободный ввод: адрес можно исправлять руками. */
  onChange: (value: string) => void;
  /** Выбран вариант из списка — приходит вся подсказка целиком. */
  onSelect: (suggestion: AddressSuggestion) => void;
}

export function AddressAutocomplete({
  id,
  label,
  value,
  error,
  placeholder,
  onChange,
  onSelect,
}: AddressAutocompleteProps): JSX.Element {
  const listboxId = id + '-listbox';
  const optionId = (index: number): string => id + '-option-' + index;

  // Текст, за которым пошёл запрос: отстаёт от value на время debounce.
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  // Значение, только что выбранное из списка: по нему подсказки не перезапрашиваем.
  const pickedRef = useRef<string | null>(null);

  // Запрос уходит не на каждую букву, а когда пользователь остановился.
  useEffect(() => {
    const timer = setTimeout(() => setQuery(value.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value]);

  // Новый текст — прежняя подсветка не имеет смысла.
  useEffect(() => {
    setActiveIndex(-1);
  }, [query]);

  const suggestions = useAddressSuggestions(query, {
    enabled: open && query !== pickedRef.current,
  });

  // Сервис могли выключить на бэкенде — тогда ведём себя как обычное поле.
  const serviceEnabled = suggestions.data ? suggestions.data.enabled : true;
  const items: AddressSuggestion[] = serviceEnabled ? (suggestions.data?.items ?? []) : [];

  const longEnough = query.length >= ADDRESS_SUGGEST_MIN_LENGTH;
  const isLoading = suggestions.isFetching;
  const listVisible = open && items.length > 0;
  const emptyVisible =
    open &&
    serviceEnabled &&
    longEnough &&
    !isLoading &&
    suggestions.isSuccess &&
    items.length === 0;

  let liveMessage = '';
  if (open && longEnough) {
    if (isLoading) liveMessage = 'Ищем адрес';
    else if (items.length > 0) liveMessage = 'Найдено вариантов: ' + items.length;
    else if (emptyVisible) liveMessage = 'Совпадений нет';
  }

  const close = (): void => {
    setOpen(false);
    setActiveIndex(-1);
  };

  const pick = (suggestion: AddressSuggestion): void => {
    haptic.selection();
    pickedRef.current = suggestion.value;
    close();
    onSelect(suggestion);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        setActiveIndex(items.length > 0 ? 0 : -1);
        return;
      }
      if (items.length === 0) return;
      setActiveIndex(activeIndex >= items.length - 1 ? 0 : activeIndex + 1);
      return;
    }

    if (event.key === 'ArrowUp') {
      if (!open || items.length === 0) return;
      event.preventDefault();
      setActiveIndex(activeIndex <= 0 ? items.length - 1 : activeIndex - 1);
      return;
    }

    if (event.key === 'Enter') {
      const picked = listVisible && activeIndex >= 0 ? items[activeIndex] : undefined;
      if (!picked) return;
      // Не даём форме отправиться: Enter здесь выбирает вариант.
      event.preventDefault();
      pick(picked);
      return;
    }

    if (event.key === 'Escape') {
      if (!open) return;
      event.preventDefault();
      close();
      return;
    }

    if (event.key === 'Tab') close();
  };

  return (
    <div className="field address-field">
      <label className="field__label" htmlFor={id}>
        {label}
      </label>

      <div className="address-field__control">
        <input
          id={id}
          className={'input address-field__input' + (error ? ' has-error' : '')}
          type="text"
          role="combobox"
          aria-expanded={listVisible}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={listVisible && activeIndex >= 0 ? optionId(activeIndex) : undefined}
          aria-invalid={error ? true : undefined}
          // Нативная автоподстановка браузера наложилась бы на свой список.
          autoComplete="off"
          placeholder={placeholder}
          value={value}
          onChange={(event) => {
            pickedRef.current = null;
            setOpen(true);
            onChange(event.target.value);
          }}
          onKeyDown={handleKeyDown}
          onBlur={close}
        />

        {isLoading ? <span className="address-field__spinner" aria-hidden="true" /> : null}

        {listVisible ? (
          <ul className="address-field__list" role="listbox" id={listboxId} aria-label="Подсказки адреса">
            {items.map((suggestion, index) => (
              <li
                key={suggestion.value + '#' + index}
                id={optionId(index)}
                role="option"
                aria-selected={index === activeIndex}
                className={'address-field__option' + (index === activeIndex ? ' is-active' : '')}
                // Именно onPointerDown с preventDefault: onClick на телефоне
                // не успевает — blur инпута закрывает список раньше.
                onPointerDown={(event) => {
                  event.preventDefault();
                  pick(suggestion);
                }}
                onPointerEnter={() => setActiveIndex(index)}
              >
                {suggestion.value}
              </li>
            ))}
          </ul>
        ) : null}

        {emptyVisible ? <div className="address-field__empty">Ничего не найдено</div> : null}
      </div>

      <span className="visually-hidden" aria-live="polite">
        {liveMessage}
      </span>

      {error ? <span className="field__error">{error}</span> : null}
    </div>
  );
}
