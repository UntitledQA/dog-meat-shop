"""Единый формат ошибок API.

Ответ всегда:
    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Базовая ошибка приложения с машиночитаемым кодом."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Некорректный запрос"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        super().__init__(self.message)

    def to_response(self) -> JSONResponse:
        return error_response(self.status_code, self.code, self.message, self.details)


class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"
    message = "Некорректный запрос"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    message = "Требуется авторизация Telegram"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "Недостаточно прав"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "Не найдено"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "Конфликт состояния"


class InsufficientStockError(ConflictError):
    code = "insufficient_stock"
    message = "Недостаточно товара на складе"


class ProductUnavailableError(ConflictError):
    code = "product_unavailable"
    message = "Товар недоступен для заказа"


class InvalidStatusTransitionError(ConflictError):
    code = "invalid_status_transition"
    message = "Недопустимое изменение статуса заказа"


class FileTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "file_too_large"
    message = "Файл слишком большой"


class UnsupportedMediaTypeError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media_type"
    message = "Поддерживаются только JPEG, PNG и WebP"


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"
    message = "Ошибка валидации данных"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Слишком много запросов, попробуйте позже"

    def __init__(self, message: str | None = None, *, retry_after: int = 60, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after

    def to_response(self) -> JSONResponse:
        response = error_response(self.status_code, self.code, self.message, self.details)
        response.headers["Retry-After"] = str(self.retry_after)
        return response


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


_HTTP_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "file_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
}

_HTTP_MESSAGE_BY_STATUS = {
    401: "Требуется авторизация Telegram",
    403: "Недостаточно прав",
    404: "Не найдено",
    405: "Метод не поддерживается",
    413: "Файл слишком большой",
    429: "Слишком много запросов, попробуйте позже",
    500: "Внутренняя ошибка сервера",
}


def register_exception_handlers(app: FastAPI) -> None:
    """Подключает обработчики так, чтобы наружу уходил только единый формат."""

    from app.core.logging import get_logger

    logger = get_logger(__name__)

    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
                "message": err.get("msg", "Некорректное значение"),
            }
            for err in exc.errors()
        ]
        return error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_error",
            "Проверьте правильность заполнения полей",
            {"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODE_BY_STATUS.get(exc.status_code, "http_error")
        message = _HTTP_MESSAGE_BY_STATUS.get(exc.status_code)
        if message is None:
            message = exc.detail if isinstance(exc.detail, str) else "Ошибка запроса"
        response = error_response(exc.status_code, code, message)
        for key, value in (exc.headers or {}).items():
            response.headers[key] = value
        return response

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_error",
            path=request.url.path,
            method=request.method,
            error=type(exc).__name__,
        )
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "Внутренняя ошибка сервера",
        )
