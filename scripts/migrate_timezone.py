"""存量时间迁移: 将 gift_events 的 UTC 时间戳转为北京时间（+8h）.

2026-08-02 之前版本以 UTC 存储 received_at/sent_at/created_at，
本脚本将存量数据统一 +8 小时转为北京时间（naive）。
幂等: 若 max(received_at) 已是北京时间（> now_utc + 7h）则跳过，可重复执行。
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from storage.database import Database


async def main() -> None:
    db = Database(Settings().db_dsn)
    await db.open()
    try:
        async with db.pool().connection() as conn:
            cur = await conn.execute("SELECT COUNT(*), MAX(received_at) FROM gift_events")
            total, max_ts = await cur.fetchone()
            print(f"rows={total} max_received_at={max_ts!r}")
            if not total:
                print("no rows, skip")
                return
            now_utc = datetime.now(timezone.utc)
            if max_ts > now_utc.replace(tzinfo=None) + timedelta(hours=7):
                print("already migrated (times look like CST), skip")
                return
            await conn.execute(
                "UPDATE gift_events SET received_at = received_at + interval '8 hours', "
                "sent_at = sent_at + interval '8 hours' WHERE sent_at IS NOT NULL"
            )
            await conn.execute(
                "UPDATE gift_events SET received_at = received_at + interval '8 hours' "
                "WHERE sent_at IS NULL"
            )
            await conn.execute("UPDATE gift_events SET created_at = created_at + interval '8 hours'")
            cur = await conn.execute(
                "SELECT MAX(received_at), MAX(created_at) FROM gift_events"
            )
            max_ts, max_ct = await cur.fetchone()
            print(f"migrated: new max_received_at={max_ts!r} max_created_at={max_ct!r}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
