import { Link, useNavigate } from 'react-router-dom';
import { Page } from '../components/Layout';
import { Button, EmptyState, LinkButton, Photo } from '../components/ui';
import { WeightPicker } from '../components/WeightPicker';
import { useToast } from '../components/ToastContext';
import { useSettings } from '../api/queries';
import { useCartStore } from '../store/cart';
import type { CartItem } from '../store/cart';
import {
  DEFAULT_MIN_WEIGHT,
  DEFAULT_WEIGHT_STEP,
  calcCartTotal,
  calcLineTotal,
  formatPrice,
  formatPricePerKg,
} from '../lib/money';
import { haptic, showConfirm } from '../telegram/webapp';

/**
 * Максимальный вес одной позиции в корзине. Реальный остаток знает бэкенд —
 * он же окончательно проверит доступность при создании заказа.
 */
const MAX_ITEM_WEIGHT = '50.000';

function CartRow({
  item,
  minWeight,
  stepWeight,
  onChangeWeight,
  onRemove,
}: {
  item: CartItem;
  minWeight: string;
  stepWeight: string;
  onChangeWeight: (weightKg: string) => void;
  onRemove: () => void;
}) {
  return (
    <div className="card card--padded stack stack--tight">
      <div className="row">
        <div className="list-row__thumb">
          <Photo url={item.photoUrl} alt={item.name} />
        </div>
        <div className="grow">
          <Link to={'/product/' + item.productId} className="product-card__name">
            {item.name}
          </Link>
          <div className="muted">{formatPricePerKg(item.pricePerKg)}</div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          aria-label={'Удалить ' + item.name}
          onClick={onRemove}
        >
          Удалить
        </Button>
      </div>

      <div className="row row--between">
        <WeightPicker
          value={item.weightKg}
          onChange={onChangeWeight}
          min={minWeight}
          max={MAX_ITEM_WEIGHT}
          step={stepWeight}
        />
        <strong style={{ whiteSpace: 'nowrap' }}>
          {formatPrice(calcLineTotal(item.weightKg, item.pricePerKg))}
        </strong>
      </div>
    </div>
  );
}

export function CartPage() {
  const items = useCartStore((state) => state.items);
  const updateWeight = useCartStore((state) => state.updateWeight);
  const remove = useCartStore((state) => state.remove);
  const clear = useCartStore((state) => state.clear);
  const { data: settings } = useSettings();
  const navigate = useNavigate();
  const toast = useToast();

  const minWeight = settings?.min_weight_kg ?? DEFAULT_MIN_WEIGHT;
  const stepWeight = settings?.weight_step_kg ?? DEFAULT_WEIGHT_STEP;

  const totals = calcCartTotal(
    items.map((item) => ({ weightKg: item.weightKg, pricePerKg: item.pricePerKg })),
    0,
  );

  const handleRemove = async (item: CartItem) => {
    const confirmed = await showConfirm('Убрать «' + item.name + '» из корзины?');
    if (!confirmed) return;
    remove(item.productId);
    haptic.impact('light');
    toast.show('«' + item.name + '» убран из корзины');
  };

  const handleClear = async () => {
    const confirmed = await showConfirm('Очистить корзину полностью?');
    if (!confirmed) return;
    clear();
    haptic.impact('medium');
    toast.show('Корзина очищена');
  };

  if (items.length === 0) {
    return (
      <Page title="Корзина">
        <EmptyState
          icon="🛒"
          title="Корзина пуста"
          text="Выберите мясо в каталоге — вес можно указать с точностью до 100 граммов."
          action={<LinkButton to="/">Перейти в каталог</LinkButton>}
        />
      </Page>
    );
  }

  return (
    <Page
      title="Корзина"
      actions={
        <Button variant="ghost" size="sm" onClick={() => void handleClear()}>
          Очистить
        </Button>
      }
    >
      <div className="stack">
        {items.map((item) => (
          <CartRow
            key={item.productId}
            item={item}
            minWeight={minWeight}
            stepWeight={stepWeight}
            onChangeWeight={(weightKg) => updateWeight(item.productId, weightKg)}
            onRemove={() => void handleRemove(item)}
          />
        ))}

        <div className="panel stack stack--tight">
          <div className="summary-row">
            <span className="muted">Позиций</span>
            <span>{items.length}</span>
          </div>
          <div className="summary-row summary-row--total">
            <span>Товары</span>
            <span>{formatPrice(totals.subtotal)}</span>
          </div>
          <p className="field__hint">Стоимость доставки добавится на следующем шаге.</p>
        </div>
      </div>

      <div className="sticky-bar">
        <Button block disabled={items.length === 0} onClick={() => navigate('/checkout')}>
          Оформить заказ · {formatPrice(totals.subtotal)}
        </Button>
      </div>
    </Page>
  );
}
