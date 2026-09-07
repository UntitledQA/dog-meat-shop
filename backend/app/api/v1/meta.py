"""Профиль пользователя и публичные настройки магазина."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.config import settings
from app.core.money import MIN_WEIGHT, WEIGHT_STEP
from app.schemas.common import AppSettingsOut
from app.schemas.user import UserOut

router = APIRouter(tags=["Профиль"])


@router.get(
    "/me",
    response_model=UserOut,
    summary="Текущий пользователь",
    description="Профиль по проверенным данным Telegram. При первом входе создаётся автоматически.",
)
async def read_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get(
    "/settings",
    response_model=AppSettingsOut,
    summary="Настройки магазина",
    description="Стоимость доставки, адрес самовывоза и правила выбора веса.",
)
async def read_settings(_user: CurrentUser) -> AppSettingsOut:
    return AppSettingsOut(
        delivery_price=settings.delivery_price,
        pickup_address=settings.pickup_address,
        min_weight_kg=MIN_WEIGHT,
        weight_step_kg=WEIGHT_STEP,
        currency=settings.currency,
        payment_note="Оплата при получении",
    )
