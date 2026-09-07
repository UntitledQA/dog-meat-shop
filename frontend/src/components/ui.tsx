/** Мелкие переиспользуемые элементы интерфейса. */

import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { resolveAssetUrl } from '../api/client';
import { statusLabel, statusModifier } from '../lib/orderStatus';
import type { OrderStatus } from '../api/types';

/* --------------------------------- Кнопка --------------------------------- */

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  block?: boolean;
  size?: 'md' | 'sm';
  loading?: boolean;
  children?: ReactNode;
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: '',
  secondary: ' btn--secondary',
  ghost: ' btn--ghost',
  danger: ' btn--danger',
};

export function Button({
  variant = 'primary',
  block = false,
  size = 'md',
  loading = false,
  disabled,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  const classes =
    'btn' +
    VARIANT_CLASS[variant] +
    (block ? ' btn--block' : '') +
    (size === 'sm' ? ' btn--sm' : '') +
    (className ? ' ' + className : '');

  return (
    <button className={classes} disabled={disabled || loading} {...rest}>
      {loading ? <span className="btn__spinner" aria-hidden="true" /> : null}
      {children}
    </button>
  );
}

/* -------------------------------- Скелетоны -------------------------------- */

export function Skeleton({ className = '', style }: { className?: string; style?: CSSProperties }) {
  return <div className={'skeleton ' + className} style={style} aria-hidden="true" />;
}

export function ProductCardSkeleton() {
  return (
    <div className="product-card">
      <Skeleton className="skeleton--media" />
      <div className="product-card__body">
        <Skeleton className="skeleton--text" style={{ width: '80%' }} />
        <Skeleton className="skeleton--text" style={{ width: '55%' }} />
        <Skeleton className="skeleton--text" style={{ width: '40%', height: 18 }} />
      </div>
    </div>
  );
}

export function CatalogSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="catalog-grid">
      {Array.from({ length: count }, (_, index) => (
        <ProductCardSkeleton key={index} />
      ))}
    </div>
  );
}

export function ListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="list">
      {Array.from({ length: count }, (_, index) => (
        <div className="list-row" key={index}>
          <Skeleton className="list-row__thumb" />
          <div className="grow">
            <Skeleton className="skeleton--text" style={{ width: '70%' }} />
            <Skeleton className="skeleton--text" style={{ width: '45%' }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------ Состояния UI ------------------------------- */

export function EmptyState({
  icon = '🐕',
  title,
  text,
  action,
}: {
  icon?: string;
  title: string;
  text?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state">
      <div className="state__icon" aria-hidden="true">
        {icon}
      </div>
      <div className="state__title">{title}</div>
      {text ? <p className="state__text">{text}</p> : null}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state">
      <div className="state__icon" aria-hidden="true">
        ⚠️
      </div>
      <div className="state__title">Не удалось загрузить</div>
      <p className="state__text">{message}</p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          Повторить
        </Button>
      ) : null}
    </div>
  );
}

/* --------------------------------- Бейджи ---------------------------------- */

export function StatusBadge({ status, label }: { status: OrderStatus; label?: string | null }) {
  return <span className={'badge ' + statusModifier(status)}>{statusLabel(status, label)}</span>;
}

/* --------------------------------- Фото ------------------------------------ */

export function Photo({
  url,
  alt,
  className = '',
}: {
  url: string | null | undefined;
  alt: string;
  className?: string;
}) {
  const src = resolveAssetUrl(url);
  if (!src) {
    return (
      <div className={'placeholder-photo ' + className} role="img" aria-label={alt}>
        🥩
      </div>
    );
  }
  return <img className={className} src={src} alt={alt} loading="lazy" />;
}

/* ------------------------------ Ссылка-кнопка ------------------------------ */

export function LinkButton({
  to,
  children,
  variant = 'primary',
  block = false,
}: {
  to: string;
  children: ReactNode;
  variant?: ButtonVariant;
  block?: boolean;
}) {
  const classes =
    'btn' + VARIANT_CLASS[variant] + (block ? ' btn--block' : '');
  return (
    <Link className={classes} to={to}>
      {children}
    </Link>
  );
}
