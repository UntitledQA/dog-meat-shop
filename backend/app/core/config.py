"""Конфигурация приложения. Все секреты приходят только из окружения."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", BASE_DIR.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- окружение ---
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_prefix: str = "/api/v1"

    # --- Telegram ---
    bot_token: str = Field(default="", alias="BOT_TOKEN")
    bot_username: str = Field(default="", alias="BOT_USERNAME")
    bot_mode: str = Field(default="polling", alias="BOT_MODE")
    webapp_url: str = Field(default="http://localhost:5173", alias="WEBAPP_URL")
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")
    webhook_path: str = Field(default="/telegram/webhook", alias="WEBHOOK_PATH")
    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")

    # --- база данных ---
    database_url: str = Field(
        default="postgresql+asyncpg://meat:meat@localhost:5432/meat",
        alias="DATABASE_URL",
    )

    # --- доступ ---
    admin_telegram_ids: str = Field(default="", alias="ADMIN_TELEGRAM_IDS")
    init_data_ttl_seconds: int = Field(default=86400, alias="INIT_DATA_TTL_SECONDS")
    dev_auth_enabled: bool = Field(default=False, alias="DEV_AUTH_ENABLED")
    dev_telegram_id: int = Field(default=0, alias="DEV_TELEGRAM_ID")

    # --- магазин ---
    delivery_price: Decimal = Field(default=Decimal("300.00"), alias="DELIVERY_PRICE")
    pickup_address: str = Field(
        default="г. Москва, ул. Примерная, 1", alias="PICKUP_ADDRESS"
    )
    currency: str = "RUB"

    # --- CORS ---
    allowed_origins: str = Field(default="http://localhost:5173", alias="ALLOWED_ORIGINS")

    # --- загрузка файлов ---
    upload_dir: str = Field(default="uploads", alias="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=5, alias="MAX_UPLOAD_SIZE_MB")

    # --- rate limiting: "запросов/секунд" ---
    rate_limit_auth: str = Field(default="30/60", alias="RATE_LIMIT_AUTH")
    rate_limit_orders: str = Field(default="10/60", alias="RATE_LIMIT_ORDERS")
    rate_limit_uploads: str = Field(default="20/60", alias="RATE_LIMIT_UPLOADS")

    @field_validator("delivery_price", mode="before")
    @classmethod
    def _parse_delivery_price(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return Decimal("0")
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def admin_ids(self) -> set[int]:
        result: set[int] = set()
        for chunk in self.admin_telegram_ids.replace(";", ",").split(","):
            chunk = chunk.strip()
            if chunk.isdigit() or (chunk.startswith("-") and chunk[1:].isdigit()):
                result.add(int(chunk))
        return result

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        if not path.is_absolute():
            path = BASE_DIR.parent / path
        return path

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def dev_auth_allowed(self) -> bool:
        """Dev-авторизация запрещена в production при любых значениях переменных."""
        return self.dev_auth_enabled and not self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
