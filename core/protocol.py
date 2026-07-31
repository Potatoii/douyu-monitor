import struct

HEADER_SIZE = 12
TYPE_CLIENT = 689
TYPE_SERVER = 690
ENCRYPT_XOR_KEY = 0x66

_HEADER_STRUCT = struct.Struct("<2IH2B")


class ProtocolError(Exception):
    pass


def pack_message(message: str, msg_type: int = TYPE_CLIENT) -> bytes:
    """封包: 4字节包长 + 4字节包长(重复) + 2字节类型 + 1字节加密位 + 1字节保留 + 数据体.

    包长字段 = 数据体长度 + 8（按 8 字节头计算），两个长度字段必须相等；
    数据体以 \\x00 结尾.
    """
    body = message.encode("utf-8") + b"\x00"
    length = 8 + len(body)
    return _HEADER_STRUCT.pack(length, length, msg_type, 0, 0) + body


def unpack_header(header: bytes) -> tuple[int, int, int]:
    """解包头: 返回 (数据体长度, 消息类型, 加密位).

    数据体长度 = 包长字段 - 8；两个长度字段不一致视为非法包.
    """
    if len(header) != HEADER_SIZE:
        raise ProtocolError(f"invalid header size: {len(header)}")
    length, length_dup, msg_type, encrypt, _reserved = _HEADER_STRUCT.unpack(header)
    if length != length_dup:
        raise ProtocolError(f"length mismatch: {length} != {length_dup}")
    if length < 8:
        raise ProtocolError(f"invalid packet length: {length}")
    return length - 8, msg_type, encrypt


def decrypt_body(body: bytes) -> bytes:
    """解密服务器消息: 字节倒序后逐字节 XOR 0x66."""
    return bytes(b ^ ENCRYPT_XOR_KEY for b in reversed(body))


def build_login_request(room_id: int) -> str:
    return f"type@=loginreq/roomid@={room_id}/"


def build_join_group(room_id: int) -> str:
    return f"type@=joingroup/rid@={room_id}/gid@=-9999"


def build_heartbeat() -> str:
    return "type@=mrkl/"


def parse_body(body: str) -> dict[str, str]:
    """解析 key@=value/ 格式的消息体为字典."""
    fields: dict[str, str] = {}
    for part in body.split("/"):
        if "@=" in part:
            key, _, value = part.partition("@=")
            fields[key] = value
    return fields
