"""Абстракция хранилища файлов.

Приложение работает только через этот интерфейс: сегодня файлы лежат на диске,
завтра их можно перенести в S3, не трогая сервисы и роуты.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.core.errors import UnsupportedMediaTypeError

__all__ = ["ALLOWED_EXTENSIONS", "Storage", "normalize_extension"]

#: Расширения, которые разрешено сохранять. Тип определяется по сигнатуре байтов,
#: расширение — производное от него, а не от имени присланного файла.
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def normalize_extension(extension: str) -> str:
    """Приводит расширение к безопасному виду `.jpg` / `.png` / `.webp`."""
    ext = (extension or "").strip().lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    if ext == ".jpeg":
        ext = ".jpg"
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedMediaTypeError("Поддерживаются только JPEG, PNG и WebP")
    return ext


class Storage(ABC):
    """Контракт хранилища изображений."""

    @abstractmethod
    async def save(self, data: bytes, extension: str) -> str:
        """Сохраняет байты и возвращает публичный URL вида `/uploads/xxx.jpg`."""

    @abstractmethod
    async def delete(self, url: str) -> None:
        """Удаляет файл по публичному URL. Отсутствие файла — не ошибка."""

    @abstractmethod
    async def exists(self, url: str) -> bool:
        """Есть ли файл по публичному URL."""
