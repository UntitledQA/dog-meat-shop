"""Схемы пользователя."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["UserOut"]


class UserOut(BaseModel):
    """Профиль покупателя. Данные приходят только из проверенного initData."""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Внутренний идентификатор")
    telegram_id: int = Field(description="Идентификатор пользователя в Telegram")
    username: str | None = Field(default=None, description="Логин в Telegram")
    first_name: str | None = Field(default=None, description="Имя")
    last_name: str | None = Field(default=None, description="Фамилия")
    phone: str | None = Field(default=None, description="Телефон из последнего заказа")
    is_admin: bool = Field(default=False, description="Признак администратора")
    created_at: datetime = Field(description="Дата регистрации")
