import { useEffect, useState } from 'react';
import {
  DEFAULT_MIN_WEIGHT,
  DEFAULT_WEIGHT_STEP,
  clampWeight,
  formatWeightInput,
  stepWeight,
  toGrams,
} from '../lib/money';
import { haptic } from '../telegram/webapp';

export interface WeightPickerProps {
  /** Каноническая строка веса, «1.500». */
  value: string;
  onChange: (weightKg: string) => void;
  /** Максимум — остаток товара. */
  max: string;
  min?: string;
  step?: string;
  disabled?: boolean;
  id?: string;
}

/** Выбор веса: кнопки −/+ с шагом 0,1 кг и поле ручного ввода. */
export function WeightPicker({
  value,
  onChange,
  max,
  min = DEFAULT_MIN_WEIGHT,
  step = DEFAULT_WEIGHT_STEP,
  disabled = false,
  id,
}: WeightPickerProps) {
  const [text, setText] = useState(() => formatWeightInput(value));

  // Внешнее изменение веса синхронизируем в поле, но не перебиваем ввод
  // пользователя, если он набрал то же самое значение в другой записи («1,5»).
  useEffect(() => {
    setText((current) => (toGrams(current) === toGrams(value) ? current : formatWeightInput(value)));
  }, [value]);

  const grams = toGrams(value);
  const minGrams = toGrams(min);
  const maxGrams = toGrams(max);

  const canDecrease = !disabled && grams > minGrams;
  const canIncrease = !disabled && grams < maxGrams;

  const apply = (next: string) => {
    onChange(next);
    setText(formatWeightInput(next));
  };

  const handleStep = (direction: 1 | -1) => {
    haptic.selection();
    apply(stepWeight(value, direction, { min, max, step }));
  };

  return (
    <div className="weight-picker">
      <button
        type="button"
        className="weight-picker__btn"
        onClick={() => handleStep(-1)}
        disabled={!canDecrease}
        aria-label="Уменьшить вес"
      >
        −
      </button>

      <input
        id={id}
        className="input weight-picker__input"
        type="text"
        inputMode="decimal"
        value={text}
        disabled={disabled}
        aria-label="Вес в килограммах"
        onChange={(event) => {
          const raw = event.target.value.replace(/[^\d.,]/g, '');
          setText(raw);
          if (raw !== '' && /\d/.test(raw)) {
            onChange(clampWeight(raw, { min, max }));
          }
        }}
        onBlur={() => apply(clampWeight(text, { min, max }))}
      />

      <button
        type="button"
        className="weight-picker__btn"
        onClick={() => handleStep(1)}
        disabled={!canIncrease}
        aria-label="Увеличить вес"
      >
        +
      </button>
    </div>
  );
}
