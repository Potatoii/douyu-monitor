"""存量数据价值刷新: 根据 gift_catalog 回填空白的 gift_value/total_value/gift_name.

用法: python -m scripts.backfill_value
可重复执行（幂等）.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from core.logger import setup_logging, log_system, log_error
from storage.database import Database

PAGE_SIZE = 500


async def backfill(db: Database) -> int:
    pool = db.pool()
    updated = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            while True:
                await cur.execute(
                    """
                    SELECT ge.id, ge.gift_id, ge.gift_count,
                           gc.gift_name, gc.value_rmb
                    FROM gift_events ge
                    LEFT JOIN gift_catalog gc ON gc.gift_id = ge.gift_id
                    WHERE (ge.gift_value IS NULL AND gc.value_rmb IS NOT NULL)
                       OR (ge.gift_name IS NULL OR ge.gift_name = '')
                    ORDER BY ge.id
                    LIMIT %s
                    """,
                    (PAGE_SIZE,),
                )
                rows = await cur.fetchall()
                if not rows:
                    break
                for row_id, gift_id, gift_count, gift_name, value_rmb in rows:
                    updates: list[str] = []
                    params: list = []
                    if gift_name:
                        updates.append("gift_name = %s")
                        params.append(gift_name)
                    if value_rmb is not None:
                        updates.append("gift_value = %s")
                        params.append(value_rmb)
                        updates.append("total_value = %s")
                        params.append(value_rmb * gift_count)
                    if not updates:
                        continue
                    params.append(row_id)
                    sql = f"UPDATE gift_events SET {', '.join(updates)} WHERE id = %s"
                    try:
                        await cur.execute(sql, params)
                        updated += 1
                    except Exception as exc:
                        log_error(f"update row {row_id} failed: {exc}")
                log_system(f"processed {len(rows)} rows, updated so far {updated}")
    return updated


async def main() -> None:
    settings = Settings()
    setup_logging(settings.log_dir, settings.log_retention_days)
    db = Database(settings.db_dsn)
    await db.open()
    try:
        count = await backfill(db)
        log_system(f"backfill done, {count} rows updated")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
