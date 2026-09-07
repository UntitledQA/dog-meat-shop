"""Загрузка изображений товаров.

Два правила, из-за которых этот модуль вообще существует:

1. Тип файла определяется по **сигнатуре первых байтов**, а не по `Content-Type`
   и не по расширению — и то и другое присылает клиент, доверять им нельзя.
2. Размер проверяется **потоково**: чтение обрывается сразу, как только
   превышен лимит, чтобы 500-мегабайтный «файл» не оказался в памяти целиком.
"""

from __future__ import annotations

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import BadRequestError, FileTooLargeError, UnsupportedMediaTypeError
from app.core.logging import get_logger
from app.repositories.product_repo import ProductRepository
from app.storage import Storage, get_storage

__all__ = [
    "CHUNK_SIZE",
    "detect_image_extension",
    "read_image_bytes",
    "remove_photo_if_unused",
    "save_image",
]

logger = get_logger(__name__)

#: Размер чанка при потоковом чтении загрузки.
CHUNK_SIZE = 64 * 1024

#: Минимум байтов, по которым можно опознать любой из поддерживаемых форматов.
_SIGNATURE_BYTES = 12

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_RIFF_MAGIC = b"RIFF"
_WEBP_MAGIC = b"WEBP"


def detect_image_extension(data: bytes) -> str:
    """Возвращает расширение по сигнатуре байтов или бросает 415."""
    if data.startswith(_JPEG_MAGIC):
        return ".jpg"
    if data.startswith(_PNG_MAGIC):
        return ".png"
    if len(data) >= _SIGNATURE_BYTES and data[0:4] == _RIFF_MAGIC and data[8:12] == _WEBP_MAGIC:
        return ".webp"
    raise UnsupportedMediaTypeError("Загрузить можно только изображение JPEG, PNG или WebP")


async def read_image_bytes(file: UploadFile) -> tuple[bytes, str]:
    """Читает загрузку чанками, проверяя тип и размер. Возвращает (байты, расширение)."""
    max_bytes = settings.max_upload_size_bytes
    buffer = bytearray()
    extension: str | None = None

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        buffer.extend(chunk)

        # Как только набралось 12 байт — сразу отсекаем неподходящий формат,
        # не дочитывая остаток файла.
        if extension is None and len(buffer) >= _SIGNATURE_BYTES:
            extension = detect_image_extension(bytes(buffer[:_SIGNATURE_BYTES]))

        if len(buffer) > max_bytes:
            raise FileTooLargeError(
                f"Максимальный размер изображения — {settings.max_upload_size_mb} МБ"
            )

    if not buffer:
        raise BadRequestError("Файл пустой")

    if extension is None:
        # Файл короче 12 байт: ни одна валидная картинка столько не весит.
        extension = detect_image_extension(bytes(buffer))

    return bytes(buffer), extension


async def save_image(file: UploadFile, storage: Storage | None = None) -> str:
    """Проверяет и сохраняет изображение, возвращает публичный URL."""
    data, extension = await read_image_bytes(file)
    target = storage or get_storage()
    url = await target.save(data, extension)
    logger.info("photo_uploaded", url=url, size=len(data))
    return url


async def remove_photo_if_unused(
    products: ProductRepository,
    photo_url: str | None,
    storage: Storage | None = None,
) -> bool:
    """Удаляет файл, если на него больше не ссылается ни один товар.

    Вызывать строго ПОСЛЕ того, как новая ссылка сохранена в БД, иначе счётчик
    использований покажет старое значение и файл будет удалён у живого товара.
    """
    if not photo_url:
        return False
    if await products.photo_url_usage_count(photo_url) > 0:
        return False

    target = storage or get_storage()
    await target.delete(photo_url)
    logger.info("photo_removed", url=photo_url)
    return True
