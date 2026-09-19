"""Сборка всех роутов версии v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.addresses import router as addresses_router
from app.api.v1.admin_orders import router as admin_orders_router
from app.api.v1.admin_products import router as admin_products_router
from app.api.v1.auth import router as auth_router
from app.api.v1.catalog import router as catalog_router
from app.api.v1.meta import router as meta_router
from app.api.v1.orders import router as orders_router

__all__ = ["api_router"]

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(meta_router)
api_router.include_router(catalog_router)
api_router.include_router(orders_router)
api_router.include_router(addresses_router)
api_router.include_router(admin_products_router)
api_router.include_router(admin_orders_router)
