"""Конфигурация приложения. Все секреты приходят только из окружения."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationInfo, field_validator
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

    # --- подсказки адресов (внешний сервис) ---
    #: none — подсказки выключены (по умолчанию), поле адреса работает как
    #:        обычный текстовый ввод;
    #: photon — бесплатный OpenStreetMap-провайдер без ключа;
    #: dadata — лучшее качество по РФ, но требует DADATA_API_KEY.
    #:
    #: Выключено по умолчанию сознательно: включение отправляет то, что
    #: покупатель набирает в поле адреса, стороннему сервису. Это осознанный
    #: выбор владельца магазина, а не то, что должно включаться само.
    address_suggest_provider: str = Field(default="none", alias="ADDRESS_SUGGEST_PROVIDER")
    #: Ключ DaData. Живёт ТОЛЬКО на сервере и никогда не уходит в браузер —
    #: ради этого подсказки и сделаны прокси-эндпоинтом, а не прямым запросом
    #: из Mini App. По умолчанию пуст: без ключа подсказки просто выключены.
    dadata_api_key: str = Field(default="", alias="DADATA_API_KEY")
    address_suggest_timeout_seconds: int = Field(
        default=3, alias="ADDRESS_SUGGEST_TIMEOUT_SECONDS"
    )
    #: Правила Photon требуют осмысленный User-Agent с названием приложения.
    address_suggest_user_agent: str = Field(
        default="MeatForDogsShop/1.0 (Telegram Mini App)",
        alias="ADDRESS_SUGGEST_USER_AGENT",
    )

    # --- rate limiting: "запросов/секунд" ---
    rate_limit_auth: str = Field(default="30/60", alias="RATE_LIMIT_AUTH")
    rate_limit_orders: str = Field(default="10/60", alias="RATE_LIMIT_ORDERS")
    rate_limit_uploads: str = Field(default="20/60", alias="RATE_LIMIT_UPLOADS")
    #: Автодополнение адреса — это запрос почти на каждую букву (на фронте
    #: стоит debounce 300 мс), поэтому лимит заметно свободнее остальных.
    rate_limit_addresses: str = Field(default="60/60", alias="RATE_LIMIT_ADDRESSES")

    @field_validator("delivery_price", mode="before")
    @classmethod
    def _parse_delivery_price(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return Decimal("0")
        return value

    @field_validator(
        "dev_telegram_id",
        "init_data_ttl_seconds",
        "max_upload_size_mb",
        "address_suggest_timeout_seconds",
        mode="before",
    )
    @classmethod
    def _empty_int_means_default(cls, value: object, info: ValidationInfo) -> object:
        """Пустая переменная в .env не должна ронять приложение.

        `DEV_TELEGRAM_ID=` (оператор стёр значение) раньше приводил к падению на
        импорте с сырым трейсбеком pydantic. Пустая строка = «значение не задано»,
        то есть берётся значение по умолчанию.
        """
        if isinstance(value, str) and not value.strip() and info.field_name:
            return cls.model_fields[info.field_name].default
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

    @property
    def address_suggest_provider_name(self) -> str:
        """Провайдер, который реально может ответить: photon, dadata или none.

        dadata без ключа — это не ошибка запуска, а выключенные подсказки:
        приложение обязано подниматься с пустым .env.
        """
        provider = self.address_suggest_provider.strip().lower()
        if provider == "photon":
            return "photon"
        if provider == "dadata" and self.dadata_api_key.strip():
            return "dadata"
        return "none"

    @property
    def address_suggest_enabled(self) -> bool:
        """Подсказки адресов включены: провайдер выбран и полностью настроен."""
        return self.address_suggest_provider_name != "none"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
