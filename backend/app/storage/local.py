"""Хранилище файлов на локальном диске."""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

from app.core.logging import get_logger
from app.storage.base import Storage, normalize_extension

__all__ = ["DEFAULT_PUBLIC_PREFIX", "LocalStorage"]

logger = get_logger(__name__)

#: Публичный префикс, под которым каталог смонтирован в FastAPI (StaticFiles).
DEFAULT_PUBLIC_PREFIX = "/uploads"


class LocalStorage(Storage):
    """Пишет файлы в каталог `base_dir`, отдаёт относительные URL.

    Имя файла всегда генерируется сервером (`secrets.token_hex(16)`), путь
    никогда не собирается из пользовательских данных: даже если в БД окажется
    подделанный `photo_url`, `_to_path()` вернёт None для всего, что уводит
    за пределы каталога загрузок.
    """

    def __init__(self, base_dir: Path | str, public_prefix: str = DEFAULT_PUBLIC_PREFIX) -> None:
        self._base_dir = Path(base_dir).resolve()
        self._prefix = "/" + public_prefix.strip("/")
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def public_prefix(self) -> str:
        return self._prefix

    def public_url(self, filename: str) -> str:
        return f"{self._prefix}/{filename}"

    def _to_path(self, url: str) -> Path | None:
        """Публичный URL -> путь на диске. None, если URL чужой или небезопасный."""
        if not url or not isinstance(url, str):
            return None

        prefix = f"{self._prefix}/"
        if not url.startswith(prefix):
            return None

        filename = url[len(prefix) :]
        # Ни каталогов, ни «..», ни абсолютных путей, ни NUL-байтов.
        if (
            not filename
            or filename in {".", ".."}
            or "/" in filename
            or "\\" in filename
            or "\x00" in filename
        ):
            return None

        candidate = (self._base_dir / filename).resolve()
        # Двойная проверка: итоговый путь обязан лежать ровно в каталоге загрузок.
        if candidate.parent != self._base_dir:
            return None
        try:
            candidate.relative_to(self._base_dir)
        except ValueError:
            return None
        return candidate

    async def save(self, data: bytes, extension: str) -> str:
        ext = normalize_extension(extension)
        filename = f"{secrets.token_hex(16)}{ext}"
        path = self._base_dir / filename

        def _write() -> None:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)
        logger.info("file_saved", filename=filename, size=len(data))
        return self.public_url(filename)

    async def delete(self, url: str) -> None:
        path = self._to_path(url)
        if path is None:
            logger.warning("file_delete_rejected", url=url)
            return

        def _unlink() -> None:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:  # pragma: no cover - редкая файловая ошибка
                logger.warning("file_delete_failed", filename=path.name, error=str(exc))

        await asyncio.to_thread(_unlink)

    async def exists(self, url: str) -> bool:
        path = self._to_path(url)
        if path is None:
            return False
        return await asyncio.to_thread(path.is_file)
