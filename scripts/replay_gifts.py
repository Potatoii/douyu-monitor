"""从 gift 日志恢复礼物事件入库.

用法: python -m scripts.replay_gifts [--dir logs/gift] [--date 2026-08-01] [--room 12598324] [--dry-run]

读取 logs/gift/*.jsonl（loguru JSONL）中记录的礼物事件，复用 PriceService
换算礼物名/价格后批量补写 gift_events。
INSERT 使用 ON CONFLICT (message_id) DO NOTHING，可重复执行（幂等）。
"""

import argparse
import asyncio
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from core.parser import GiftEvent
from services.price_service import PriceService
from storage.database import Database
from storage import repository

BATCH = 50


def iter_log_lines(log_dir: Path, date: str | None, room: int | None):
    """逐行读取 gift 日志, 产出 GiftEvent（不包含价格字段, 待 enrich 填充）."""
    files = sorted(log_dir.glob("*.jsonl"))
    if date:
        files = [f for f in files if f.stem == date]
    for path in files:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                record = rec.get("record", {})
                extra = record.get("extra", {})
                if extra.get("stream") != "gift":
                    continue
                if room is not None and extra.get("room_id") != room:
                    continue
                event = _to_event(extra, record.get("message"), record.get("time"))
                if event is not None:
                    yield event


def _to_event(extra: dict, message, time_info) -> GiftEvent | None:
    try:
        if isinstance(message, str):
            data = ast.literal_eval(message)
        else:
            data = message
        if not isinstance(data, dict):
            return None
        received_at = datetime.fromtimestamp(time_info["timestamp"], tz=timezone.utc)
        return GiftEvent(
            message_id=str(extra["msg_id"]),
            room_id=int(extra["room_id"]),
            sender_uid=int(data["sender_uid"]),
            sender_nickname=str(data["sender_nickname"]),
            gift_id=int(data["gift_id"]),
            gift_name="",
            gift_count=int(data["gift_count"]),
            gift_price=None,
            total_price=None,
            gift_value=None,
            total_value=None,
            receive_uid=None,
            hit_score=None,
            sent_at=None,
            received_at=received_at,
            port=int(extra.get("port") or data.get("port") or 0),
            raw_msg=json.dumps(data, ensure_ascii=False),
        )
    except (KeyError, TypeError, ValueError):
        return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="从 gift 日志恢复礼物入库")
    parser.add_argument("--dir", default="logs/gift", help="gift 日志目录")
    parser.add_argument("--date", default=None, help="只处理指定日期的文件, 如 2026-08-01")
    parser.add_argument("--room", type=int, default=None, help="只处理指定房间")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = parser.parse_args()

    events = list(iter_log_lines(Path(args.dir), args.date, args.room))
    if not events:
        print(f"no gift events found in {args.dir} (date={args.date})")
        return

    db = Database(Settings().db_dsn)
    await db.open()
    try:
        service = PriceService(db.pool())
        priced = 0
        batch: list[GiftEvent] = []
        processed = 0
        async def flush(batch: list[GiftEvent]) -> None:
            nonlocal priced
            priced += sum(1 for e in batch if e.gift_value is not None)
            if args.dry_run:
                return
            await repository.insert_gift_events(db.pool(), batch)

        for event in events:
            await service.enrich(event)
            batch.append(event)
            if len(batch) >= BATCH:
                await flush(batch)
                processed += len(batch)
                batch = []
                print(f"processed {processed}/{len(events)}")
        if batch:
            await flush(batch)
            processed += len(batch)
        print(
            f"done: {processed} events, {priced} priced"
            + (" (dry run)" if args.dry_run else ", duplicates skipped via ON CONFLICT")
        )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
