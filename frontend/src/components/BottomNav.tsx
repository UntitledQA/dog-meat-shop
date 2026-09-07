import { NavLink } from 'react-router-dom';
import { useCartCount } from '../store/cart';
import { haptic } from '../telegram/webapp';

interface NavItem {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
}

const BASE_ITEMS: NavItem[] = [
  { to: '/', label: 'Каталог', icon: '🥩', end: true },
  { to: '/cart', label: 'Корзина', icon: '🛒' },
  { to: '/orders', label: 'Заказы', icon: '📋' },
];

const ADMIN_ITEM: NavItem = { to: '/admin', label: 'Админ', icon: '⚙️' };

/** Нижняя навигация с бейджем количества позиций в корзине. */
export function BottomNav({ isAdmin }: { isAdmin: boolean }) {
  const cartCount = useCartCount();
  const items = isAdmin ? [...BASE_ITEMS, ADMIN_ITEM] : BASE_ITEMS;

  return (
    <nav className="bottom-nav" aria-label="Основная навигация">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={() => haptic.selection()}
          className={({ isActive }) => 'bottom-nav__item' + (isActive ? ' is-active' : '')}
        >
          <span className="bottom-nav__icon" aria-hidden="true">
            {item.icon}
          </span>
          <span>{item.label}</span>
          {item.to === '/cart' && cartCount > 0 ? (
            <span className="bottom-nav__badge" aria-label={'позиций в корзине: ' + cartCount}>
              {cartCount > 99 ? '99+' : cartCount}
            </span>
          ) : null}
        </NavLink>
      ))}
    </nav>
  );
}
