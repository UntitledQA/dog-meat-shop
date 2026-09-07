"""Точка входа Telegram-бота.

Запуск:

    python -m app.bot_main

Режим берётся из `BOT_MODE`:

* ``polling``  — long polling, удобно локально и на маленьком VPS;
* ``webhook``  — регистрирует webhook в Telegram и печатает, что должно принимать
  обновления (сам HTTP-эндпоинт живёт в веб-приложении).
"""

from __future__ import annotations

import asyncio
import sys

from app.bot.bot import get_bot, shutdown
from app.bot.runner import run_polling, setup_webhook, webhook_info, webhook_url
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

_NO_TOKEN_MESSAGE = """
Не задан BOT_TOKEN.

Что сделать:
  1. Получите токен у @BotFather в Telegram.
  2. Впишите его в файл .env рядом с backend/ :
         BOT_TOKEN=123456789:AA...
  3. Запустите снова: python -m app.bot_main

Токен — секрет: не коммитьте .env и не пересылайте токен в переписке.
""".strip()

_WEBHOOK_INSTRUCTIONS = """
Режим webhook.

Telegram будет отправлять обновления на:
    {url}

Проверьте, что выполнено:
  * адрес доступен из интернета по HTTPS с валидным сертификатом;
  * PUBLIC_BASE_URL и WEBHOOK_PATH в .env совпадают с реальным адресом;
  * задан WEBHOOK_SECRET — обработчик обязан сверять заголовок
    X-Telegram-Bot-Api-Secret-Token, иначе обновления сможет подделать кто угодно;
  * веб-приложение (uvicorn) запущено и принимает POST по этому пути.

Вернуться на long polling: BOT_MODE=polling и перезапуск (webhook будет снят автоматически).
""".strip()


async def run_webhook_mode() -> int:
    """Выставляет webhook и печатает инструкцию. Возвращает код выхода."""
    url = webhook_url()
    print(_WEBHOOK_INSTRUCTIONS.format(url=url))

    ok = await setup_webhook(url)
    if not ok:
        logger.error("webhook_setup_failed", url=url)
        print("\nНе удалось установить webhook — подробности в логе выше.")
        return 1

    info = await webhook_info()
    if info:
        print(f"\nWebhook установлен: {info['url']}")
        if info.get("last_error_message"):
            print(f"Последняя ошибка Telegram: {info['last_error_message']}")
    return 0


async def main() -> int:
    configure_logging()

    if get_bot() is None:
        print(_NO_TOKEN_MESSAGE, file=sys.stderr)
        logger.error("bot_token_missing")
        return 1

    mode = settings.bot_mode.strip().lower()
    logger.info("bot_main_start", mode=mode, environment=settings.environment)

    try:
        if mode == "webhook":
            return await run_webhook_mode()

        if mode != "polling":
            logger.warning("bot_mode_unknown", mode=mode, fallback="polling")

        # Long polling; run_polling сам снимает ранее выставленный webhook,
        # иначе Telegram вернёт конфликт «webhook is active».
        await run_polling()
        return 0
    finally:
        await shutdown()


def cli() -> None:
    """Синхронная обёртка для `python -m app.bot_main` и console_scripts."""
    try:
        code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
        code = 0
    sys.exit(code)


if __name__ == "__main__":
    cli()
