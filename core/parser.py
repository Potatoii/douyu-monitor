import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.protocol import parse_body

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
    if not gift_id:
        gift_id = _to_int(fields.get("pid"))  # gfid=0 的活动礼物, pid@ 是真实 ID
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


def parse_subscription(
    fields: dict[str, str],
    room_id: int,
    port: int,
    received_at: datetime,
    raw_msg: str,
) -> GiftEvent | None:
    """解析钻粉开通(dfobc)/续费(dfrbc)消息为 GiftEvent.

    price 单位为分(总价), 月价 = price / 100 / mn.
    """
    msg_type = fields.get("type", "")
    if msg_type not in ("dfobc", "dfrbc"):
        return None
    eid = _to_int(fields.get("eid"))
    if eid is None:
        return None
    mn = _to_int(fields.get("mn"), 1) or 1
    price = _to_int(fields.get("price"))
    total_price = price // 100 if price is not None else None
    gift_price = total_price // mn if total_price is not None else None
    gift_value = Decimal(gift_price) if gift_price is not None else None
    total_value = Decimal(total_price) if total_price is not None else None
    sent_at = None
    if fields.get("bet"):
        try:
            sent_at = datetime.fromtimestamp(int(fields["bet"]), tz=timezone.utc)
        except (ValueError, OverflowError):
            sent_at = None
    return GiftEvent(
        message_id=make_message_id(raw_msg),
        room_id=room_id,
        sender_uid=_to_int(fields.get("uid"), 0) or 0,
        sender_nickname=fields.get("nick") or "",
        gift_id=eid,
        gift_name="钻粉开通" if msg_type == "dfobc" else "钻粉续费",
        gift_count=mn,
        gift_price=gift_price,
        total_price=total_price,
        gift_value=gift_value,
        total_value=total_value,
        receive_uid=None,
        hit_score=None,
        sent_at=sent_at,
        received_at=received_at,
        port=port,
        raw_msg=raw_msg,
        msg_type=msg_type,
    )


def unescape(value: str) -> str:
    """反转义: @A= -> @=, @S -> / (斗鱼嵌套消息编码)."""
    return value.replace("@S", "/").replace("@A=", "@=")


@dataclass(slots=True)
class DanmuMessage:
    message_id: str
    room_id: int
    sender_uid: int
    sender_nickname: str
    content: str
    level: int | None
    btype: str | None
    sent_at: datetime | None
    received_at: datetime
    port: int
    raw_msg: str
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
            self.content,
            self.level,
            sent_at,
            self.received_at.astimezone(CST).replace(tzinfo=None),
            self.port,
            self.btype,
        )


def parse_danmu(
    fields: dict[str, str],
    room_id: int,
    port: int,
    received_at: datetime,
    raw_msg: str,
) -> DanmuMessage | None:
    """解析 chatmsg 弹幕；btype 特殊播报（pandora 等嵌套消息）也在此处理."""
    msg_type = fields.get("type", "")
    btype = fields.get("btype") or None
    if msg_type == "chatmsg":
        message_id = f"danmu:{fields.get('cid')}" if fields.get("cid") else make_message_id(raw_msg)
        return DanmuMessage(
            message_id=message_id,
            room_id=room_id,
            sender_uid=_to_int(fields.get("uid"), 0) or 0,
            sender_nickname=fields.get("nn") or "",
            content=fields.get("txt") or "",
            level=_to_int(fields.get("level")),
            btype=None,
            sent_at=_ms_to_cst(fields.get("cst")),
            received_at=received_at,
            port=port,
            raw_msg=raw_msg,
        )
    if msg_type == "comm_chatmsg" and btype:
        inner = parse_body(unescape(fields.get("chatmsg") or ""))
        content = "".join(
            fields.get(k, "") for k in ("txt1", "txt4", "txt5", "txt3")
        )
        return DanmuMessage(
            message_id=make_message_id(raw_msg),
            room_id=room_id,
            sender_uid=_to_int(inner.get("uid"), 0) or 0,
            sender_nickname=inner.get("bnn") or fields.get("uid", ""),
            content=content,
            level=_to_int(inner.get("level")),
            btype=btype,
            sent_at=_ms_to_cst(fields.get("now")),
            received_at=received_at,
            port=port,
            raw_msg=raw_msg,
        )
    return None


def _ms_to_cst(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (ValueError, OverflowError):
        return None
