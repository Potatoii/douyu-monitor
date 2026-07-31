import sys
from pathlib import Path

from loguru import logger

STREAM_RAW = "raw"
STREAM_GIFT = "gift"
STREAM_SYSTEM = "system"
STREAM_ERROR = "error"

_FILES = {
    STREAM_RAW: "raw",
    STREAM_GIFT: "gift",
    STREAM_SYSTEM: "system",
    STREAM_ERROR: "error",
}


def setup_logging(log_dir: str = "logs", retention_days: int = 7) -> None:
    """初始化日志: raw/gift/system/error 四个按天轮转的 JSONL 文件 + 控制台输出.

    serialize=True 时每行输出 loguru 内置 JSON（含 time/level/message/extra），
    extra 中携带 room_id/port/msg_type/msg_id 等字段，可直接用 jq/grep 查询.
    """
    logger.remove()
    base = Path(log_dir)
    for stream, sub in _FILES.items():
        dir_path = base / sub
        dir_path.mkdir(parents=True, exist_ok=True)
        logger.add(
            dir_path / "{time:YYYY-MM-DD}.jsonl",
            filter=lambda record, s=stream: record["extra"].get("stream") == s,
            serialize=True,
            rotation="00:00",
            retention=retention_days,
            encoding="utf-8",
            enqueue=True,
        )
    logger.add(
        sys.stderr,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {message}",
        enqueue=True,
    )


def log_raw(room_id: int, port: int, msg_type: str, body: str) -> None:
    logger.bind(stream=STREAM_RAW, room_id=room_id, port=port, msg_type=msg_type).info(body)


def log_gift(room_id: int, port: int, msg_id: str, gift: dict) -> None:
    logger.bind(stream=STREAM_GIFT, room_id=room_id, port=port, msg_id=msg_id).info(gift)


def log_system(message: str, **extra) -> None:
    logger.bind(stream=STREAM_SYSTEM, **extra).info(message)


def log_error(message: str, **extra) -> None:
    logger.bind(stream=STREAM_ERROR, **extra).error(message)
