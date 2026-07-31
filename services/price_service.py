from decimal import Decimal

from core.parser import GiftEvent
from storage import repository

from core import logger
from psycopg_pool import AsyncConnectionPool


class PriceService:
    """礼物价值换算: gift_catalog 有信息则换算, 无信息则留空.

    gift_id 查不到时用 gfn 礼物名兜底（活动礼物 pgid_*/pid_* 的真实 ID 不在
    gift.json 中，但 dgb 消息自带 gfn 名字），并按 ID 记录一次未知礼物日志.
    """

    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool
        self._catalog: dict[int, tuple[str | None, int | None, Decimal | None]] = {}
        self._name_index: dict[str, tuple[str | None, int | None, Decimal | None]] = {}
        self._missing: set[int] = set()
        self._name_miss: set[str] = set()

    async def enrich(self, event: GiftEvent) -> None:
        info = self._catalog.get(event.gift_id)
        if info is None:
            if event.gift_id in self._missing:
                info = self._name_index.get(event.gift_name)
            else:
                info = await self._load(event.gift_id)
                if info is None:
                    self._missing.add(event.gift_id)
                    logger.log_system(
                        f"gift id={event.gift_id} name={event.gift_name!r} not in catalog, trying name lookup"
                    )
                    info = await self._load_by_name(event.gift_name)
        if info is None:
            return
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
        info = name, price_yu, Decimal(str(value)) if value is not None else None
        self._catalog[gift_id] = info
        return info

    async def _load_by_name(self, gift_name: str) -> tuple[str | None, int | None, Decimal | None] | None:
        if not gift_name:
            return None
        cached = self._name_index.get(gift_name)
        if cached is not None:
            return cached
        if gift_name in self._name_miss:
            return None
        row = await repository.query_gift_by_name(self._pool, gift_name)
        if row is None:
            self._name_miss.add(gift_name)
            return None
        _, name, price_yu, value = row
        info = name, price_yu, Decimal(str(value)) if value is not None else None
        self._name_index[gift_name] = info
        return info
