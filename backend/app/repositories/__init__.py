"""Репозитории: только доступ к данным."""

from app.repositories.base import BaseRepository
from app.repositories.order_repo import OrderRepository
from app.repositories.product_repo import ProductRepository

__all__ = ["BaseRepository", "OrderRepository", "ProductRepository"]
