import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# 数据库统一存北京时间（+08:00, naive）
CST = timezone(timedelta(hours=8))


@dataclass(slots=True)
class GiftEvent:
    message_id: str
    room_id: int
    sender_uid: int
    sender_nickname: str
    gift_id: int
    gift_name: str
    gift_count: int
    gift_price: int | None
    total_price: int | None
    gift_value: Decimal | None
    total_value: Decimal | None
    receive_uid: int | None
    hit_score: int | None
    sent_at: datetime | None
    received_at: datetime
    port: int
    raw_msg: str
    msg_type: str = "dgb"
    _utc: bool = field(default=False, init=False, repr=False)

    def to_db_row(self) -> tuple:
        sent_at = self.sent_at
        if sent_at is None:
            sent_at = self.received_at
        if not self._utc:
            sent_at = sent_at.astimezone(CST).replace(tzinfo=None)
            self._utc = True
        return (
            self.message_id,
            self.room_id,
            self.sender_uid,
            self.sender_nickname,
            self.gift_id,
            self.gift_name,
            self.gift_count,
            self.gift_price,
            self.total_price,
            self.gift_value,
            self.total_value,
            self.receive_uid,
            self.hit_score,
            sent_at,
            self.received_at.astimezone(CST).replace(tzinfo=None),
            self.port,
        )


def make_message_id(body: str) -> str:
    """dgb 消息无唯一 ID，以原始消息体 MD5 作为去重键（6 端口内容一致）."""
    return "dgb:" + hashlib.md5(body.encode("utf-8")).hexdigest()


def _to_int(value: str | None, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_gift(
    fields: dict[str, str],
    room_id: int,
    port: int,
    received_at: datetime,
    raw_msg: str,
) -> GiftEvent | None:
    if fields.get("type") != "dgb":
        return None
    gift_id = _to_int(fields.get("gfid"))
    if gift_id is None:
        gift_id = _to_int(fields.get("gid"))
    if gift_id is None:
        return None
    nickname = fields.get("nn") or ""
    return GiftEvent(
        message_id=make_message_id(raw_msg),
        room_id=room_id,
        sender_uid=_to_int(fields.get("uid"), 0) or 0,
        sender_nickname=nickname,
        gift_id=gift_id,
        gift_name=fields.get("gfn") or "",
        gift_count=_to_int(fields.get("gfcnt"), 1) or 1,
        gift_price=None,
        total_price=None,
        gift_value=None,
        total_value=None,
        receive_uid=_to_int(
            fields.get("receive_uid")
            if fields.get("receive_uid") is not None
            else (fields.get("eid") if fields.get("eid") is not None else fields.get("dst"))
        ),
        hit_score=_to_int(fields.get("hits")),
        sent_at=None,
        received_at=received_at,
        port=port,
        raw_msg=raw_msg,
    )
