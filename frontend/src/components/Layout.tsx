import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { BottomNav } from './BottomNav';
import { showBackButton } from '../telegram/webapp';

export interface PageProps {
  title?: string;
  /** Показать кнопку «Назад» (и системную кнопку Telegram). */
  back?: boolean;
  /** Куда вести кнопкой «Назад». По умолчанию — history.back(). */
  backTo?: string;
  actions?: ReactNode;
  children: ReactNode;
}

/** Шапка страницы + основной контент. Нижняя навигация — в AppShell. */
export function Page({ title, back = false, backTo, actions, children }: PageProps) {
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!back) return undefined;
    return showBackButton(() => {
      if (backTo) navigate(backTo);
      else navigate(-1);
    });
  }, [back, backTo, navigate, location.pathname]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <>
      {title || back ? (
        <header className="app-header">
          {back ? (
            <button
              type="button"
              className="app-header__back"
              aria-label="Назад"
              onClick={() => (backTo ? navigate(backTo) : navigate(-1))}
            >
              ←
            </button>
          ) : null}
          <div className="app-header__title">{title}</div>
          {actions}
        </header>
      ) : null}
      <main className="app-main">{children}</main>
    </>
  );
}

/** Каркас приложения: контент + нижняя навигация. */
export function AppShell({ isAdmin, children }: { isAdmin: boolean; children: ReactNode }) {
  return (
    <div className="app-shell">
      {children}
      <BottomNav isAdmin={isAdmin} />
    </div>
  );
}
