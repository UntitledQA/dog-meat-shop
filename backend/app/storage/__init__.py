"""Хранилище изображений товаров."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.storage.base import ALLOWED_EXTENSIONS, Storage, normalize_extension
from app.storage.local import DEFAULT_PUBLIC_PREFIX, LocalStorage

__all__ = [
    "ALLOWED_EXTENSIONS",
    "DEFAULT_PUBLIC_PREFIX",
    "LocalStorage",
    "Storage",
    "get_storage",
    "normalize_extension",
]


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    """Фабрика хранилища.

    Сейчас доступна только локальная реализация; когда появится S3, здесь
    добавится ветка по настройке, а вызывающий код не изменится.
    """
    return LocalStorage(settings.upload_path, DEFAULT_PUBLIC_PREFIX)
