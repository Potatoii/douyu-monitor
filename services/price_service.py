from decimal import Decimal

from psycopg_pool import AsyncConnectionPool

from core.parser import GiftEvent
from storage import repository


class PriceService:
    """礼物价值换算: gift_catalog 有信息则换算, 无信息则留空."""

    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool
        self._catalog: dict[int, tuple[str | None, int | None, Decimal | None]] = {}
        self._missing: set[int] = set()

    async def enrich(self, event: GiftEvent) -> None:
        if event.gift_id in self._missing:
            return
        info = self._catalog.get(event.gift_id)
        if info is None:
            info = await self._load(event.gift_id)
            if info is None:
                self._missing.add(event.gift_id)
                return
            self._catalog[event.gift_id] = info
        name, price_yu, value_rmb = info
        if name:
            event.gift_name = name
        if price_yu is not None:
            event.gift_price = price_yu
            event.total_price = price_yu * event.gift_count
        if value_rmb is not None:
            event.gift_value = value_rmb
            event.total_value = value_rmb * event.gift_count

    async def _load(self, gift_id: int) -> tuple[str | None, int | None, Decimal | None] | None:
        row = await repository.query_gift_value(self._pool, gift_id)
        if row is None:
            return None
        name, price_yu, value = row
        return name, price_yu, Decimal(str(value)) if value is not None else None
