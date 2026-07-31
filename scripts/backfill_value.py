"""存量数据价值刷新: 根据 gift_catalog 回填空白的 gift_name/gift_price/gift_value.

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

_NAME_LOOKUP_SQL = """
SELECT gift_name, price_yu, value_rmb FROM gift_catalog
WHERE gift_name = %s
ORDER BY (id_type = 'gfid') DESC, price_yu DESC NULLS LAST
LIMIT 1
"""


async def backfill(db: Database) -> int:
    pool = db.pool()
    updated = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            while True:
                await cur.execute(
                    """
                    SELECT ge.id, ge.gift_id, ge.gift_name, ge.gift_count,
                           gc.gift_name, gc.price_yu, gc.value_rmb
                    FROM gift_events ge
                    LEFT JOIN gift_catalog gc
                           ON gc.id_type = 'gfid' AND gc.gift_id = ge.gift_id
                    WHERE (ge.gift_value IS NULL AND gc.value_rmb IS NOT NULL)
                       OR (ge.gift_price IS NULL AND gc.price_yu IS NOT NULL)
                       OR (ge.gift_name IS NULL OR ge.gift_name = '')
                       OR (gc.gift_id IS NULL AND ge.gift_name <> ''
                           AND (ge.gift_price IS NULL OR ge.gift_value IS NULL)
                           AND EXISTS (
                               SELECT 1 FROM gift_catalog n
                               WHERE n.gift_name = ge.gift_name
                                 AND (n.price_yu IS NOT NULL OR n.value_rmb IS NOT NULL)
                           ))
                    ORDER BY ge.id
                    LIMIT %s
                    """,
                    (PAGE_SIZE,),
                )
                rows = await cur.fetchall()
                if not rows:
                    break
                for row_id, gift_id, gift_name, gift_count, gc_name, price_yu, value_rmb in rows:
                    if (price_yu is None and value_rmb is None) and gift_name:
                        await cur.execute(_NAME_LOOKUP_SQL, (gift_name,))
                        row = await cur.fetchone()
                        if row and row[1] is not None:
                            gc_name = row[0] or gc_name
                            price_yu = row[1]
                            value_rmb = row[2]
                    updates: list[str] = []
                    params: list = []
                    if gc_name:
                        updates.append("gift_name = %s")
                        params.append(gc_name)
                    if price_yu is not None:
                        updates.append("gift_price = %s")
                        params.append(price_yu)
                        updates.append("total_price = %s")
                        params.append(price_yu * gift_count)
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
