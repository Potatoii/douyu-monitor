"""从 raw 日志恢复钻粉开通(dfobc)/续费(dfrbc)消息入库.

用法: python -m scripts.replay_subscriptions [--dir logs/raw] [--date 2026-08-13] [--room 12598324] [--dry-run]

读取 logs/raw/*.jsonl 中 type@=dfobc / type@=dfrbc 消息，用 parse_subscription
解析为 GiftEvent 后批量补写 gift_events（gift_name=钻粉开通/钻粉续费）。
6 端口重复消息按 md5(message_id) 自动去重，INSERT 用 ON CONFLICT 幂等，可重复执行。
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from core import parser, protocol
from storage.database import Database
from storage import repository

BATCH = 50


def iter_log_lines(log_dir: Path, date: str | None, room: int | None):
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
                if record.get("extra", {}).get("stream") != "raw":
                    continue
                msg = record.get("message") or ""
                if "type@=dfobc" not in msg and "type@=dfrbc" not in msg:
                    continue
                if room is not None and record.get("extra", {}).get("room_id") != room:
                    continue
                fields = protocol.parse_body(msg.rstrip("\x00"))
                if fields.get("type") not in ("dfobc", "dfrbc"):
                    continue
                received_at = datetime.fromtimestamp(
                    record["time"]["timestamp"], tz=timezone.utc
                )
                event = parser.parse_subscription(
                    fields,
                    int(fields.get("rid") or 0),
                    int(record.get("extra", {}).get("port") or 0),
                    received_at,
                    msg,
                )
                if event is not None:
                    yield event


async def main() -> None:
    parser_ = argparse.ArgumentParser(description="从 raw 日志恢复钻粉开通/续费入库")
    parser_.add_argument("--dir", default="logs/raw", help="raw 日志目录")
    parser_.add_argument("--date", default=None, help="只处理指定日期的文件, 如 2026-08-13")
    parser_.add_argument("--room", type=int, default=None, help="只处理指定房间")
    parser_.add_argument("--dry-run", action="store_true", help="只统计不写库")
    parser_.add_argument("--verify", action="store_true", help="写完后对账 message_id 与库中实际命中数")
    parser_.add_argument("--per-row", action="store_true", help="逐条插入, 单条失败跳过")
    args = parser_.parse_args()

    events = list(iter_log_lines(Path(args.dir), args.date, args.room))
    if not events:
        print(f"no dfobc/dfrbc events found in {args.dir} (date={args.date})")
        return

    unique: dict[str, object] = {}
    for e in events:
        unique.setdefault(e.message_id, e)
    events = list(unique.values())
    print(f"raw lines deduped to {len(events)} unique events")

    db = Database(Settings().db_dsn)
    await db.open()
    try:
        batch = []
        processed = 0
        for event in events:
            batch.append(event)
            if len(batch) >= BATCH:
                if not args.dry_run:
                    await repository.insert_gift_events(db.pool(), batch, per_row=args.per_row)
                processed += len(batch)
                batch = []
                print(f"processed {processed}/{len(events)}")
        if batch:
            if not args.dry_run:
                await repository.insert_gift_events(db.pool(), batch, per_row=args.per_row)
            processed += len(batch)
        print(
            f"done: {processed} events"
            + (" (dry run)" if args.dry_run else ", duplicates skipped via ON CONFLICT")
        )
        if args.verify:
            ids = [e.message_id for e in events]
            async with db.pool().connection() as conn:
                cur = await conn.execute(
                    "SELECT COUNT(*) FROM gift_events WHERE message_id = ANY(%s)",
                    (ids,),
                )
                hit = (await cur.fetchone())[0]
            print(f"verify: {hit}/{len(ids)} message_ids found in db, missing={len(ids) - hit}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)