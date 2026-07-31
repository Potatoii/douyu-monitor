from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.parser import GiftEvent
from services.price_service import PriceService


def _event(gift_id: int, gift_name: str, count: int = 1) -> GiftEvent:
    return GiftEvent(
        message_id=f"dgb:{gift_id}:{gift_name}",
        room_id=1,
        sender_uid=1,
        sender_nickname="u",
        gift_id=gift_id,
        gift_name=gift_name,
        gift_count=count,
        gift_price=None,
        total_price=None,
        gift_value=None,
        total_value=None,
        receive_uid=None,
        hit_score=None,
        sent_at=datetime.now(timezone.utc),
        received_at=datetime.now(timezone.utc),
        port=1,
        raw_msg="",
    )


class FakeCursor:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, sql, params=None):
        self.sql = sql

    async def fetchone(self):
        return self._response

    async def fetchall(self):
        return [self._response] if self._response else []


class FakeConnection:
    def __init__(self, response):
        self._response = response

    def cursor(self, row_factory=None):
        return FakeCursor(self._response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakePool:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.calls = 0

    def connection(self):
        self.calls += 1
        return FakeConnection(self._responses.pop(0) if self._responses else None)


async def test_enrich_by_id():
    pool = FakePool({"gift_name": "火箭", "price_yu": 500.0, "value_rmb": 500.0})
    service = PriceService(pool)
    event = _event(35213, "火箭")
    await service.enrich(event)
    assert event.gift_price == 500
    assert event.gift_value == Decimal("500")
    assert event.total_value == Decimal("500")
    assert pool.calls == 1


async def test_enrich_fallback_by_name_when_id_missing():
    pool = FakePool(
        None,  # id miss
        {"gift_id": 4068, "gift_name": "悠闲假日", "price_yu": 6.0, "value_rmb": 6.0},  # name hit
    )
    service = PriceService(pool)
    event = _event(4068, "悠闲假日", count=3)
    await service.enrich(event)
    assert event.gift_name == "悠闲假日"
    assert event.gift_price == 6
    assert event.total_price == 18
    assert event.total_value == Decimal("18")
    assert pool.calls == 2


async def test_enrich_name_fallback_cached():
    pool = FakePool(
        None,
        {"gift_id": 4068, "gift_name": "悠闲假日", "price_yu": 6.0, "value_rmb": 6.0},
    )
    service = PriceService(pool)
    first = _event(4068, "悠闲假日")
    await service.enrich(first)
    second = _event(4068, "悠闲假日")
    await service.enrich(second)
    assert second.gift_price == 6
    assert pool.calls == 2


async def test_enrich_unknown_leaves_blank_and_queries_once():
    pool = FakePool(None, None)
    service = PriceService(pool)
    first = _event(999999, "未知礼物")
    await service.enrich(first)
    assert first.gift_price is None
    assert first.gift_value is None
    second = _event(999999, "未知礼物")
    await service.enrich(second)
    assert pool.calls == 2
