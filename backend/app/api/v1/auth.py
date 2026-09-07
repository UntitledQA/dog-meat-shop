"""Авторизация Telegram Mini App.

Вся проверка подписи `initData` живёт в `app/core/security.py` и вызывается зависимостью
`app/api/deps.py::get_current_user`. Здесь её НЕ дублируем: один алгоритм — одно место.

Клиент присылает сырой `initData` в заголовке `X-Telegram-Init-Data`, сервер проверяет
подпись, при первом входе создаёт пользователя и возвращает профиль.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser
from app.core.logging import get_logger
from app.models import User
from app.schemas import UserOut

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Авторизация"])

_UNAUTHORIZED_EXAMPLE = {
    "description": "Подпись Telegram отсутствует, повреждена или устарела",
    "content": {
        "application/json": {
            "example": {
                "error": {
                    "code": "unauthorized",
                    "message": "Неверная подпись данных Telegram",
                    "details": {},
                }
            }
        }
    },
}


@router.post(
    "/telegram",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    summary="Вход через Telegram",
    description=(
        "Проверяет подпись `initData` из заголовка `X-Telegram-Init-Data` и возвращает "
        "профиль пользователя. При первом входе профиль создаётся автоматически. "
        "Идентификатор пользователя берётся только из проверенных данных Telegram — "
        "любые `user_id` из тела или query игнорируются."
    ),
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED_EXAMPLE},
)
async def login_telegram(user: CurrentUser) -> User:
    """Возвращает профиль текущего пользователя Telegram."""
    logger.info("auth_telegram_login", user_id=user.id, is_admin=user.is_admin)
    return user
