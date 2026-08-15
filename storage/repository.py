from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from core.parser import DanmuMessage, GiftEvent

_INSERT_SQL = """
INSERT INTO gift_events
(message_id, room_id, sender_uid, sender_nickname, gift_id, gift_name,
 gift_count, gift_price, total_price, gift_value, total_value,
 receive_uid, hit_score, sent_at, received_at, port)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (message_id) DO NOTHING
"""

_DANMU_INSERT_SQL = """
INSERT INTO danmu_messages
(message_id, room_id, sender_uid, sender_nickname, content, level,
 sent_at, received_at, port, btype)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (message_id) DO NOTHING
"""


async def insert_gift_events(
    pool: AsyncConnectionPool, events: list[GiftEvent], per_row: bool = False
) -> int:
    """批量插入礼物事件; per_row=True 时逐条插入, 单条失败跳过不影响其他行.

    返回尝试插入的条数（ON CONFLICT 冲突的行不计入失败，重复行会被静默跳过）.
    """
    if not events:
        return 0
    rows = [event.to_db_row() for event in events]
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            if not per_row:
                await cur.executemany(_INSERT_SQL, rows)
                return len(events)
            inserted = 0
            for row in rows:
                try:
                    await cur.execute(_INSERT_SQL, row)
                    inserted += 1
                except Exception:
                    try:
                        await conn.rollback()
                    except Exception:
                        pass
            return inserted

async def insert_danmu_messages(
    pool: AsyncConnectionPool, messages: list[DanmuMessage], per_row: bool = False
) -> int:
    """批量插入弹幕消息; per_row=True 时逐条插入, 单条失败跳过不影响其他行.

    返回尝试插入的条数（ON CONFLICT 冲突的行不计入失败，重复行会被静默跳过）.
    """
    if not messages:
        return 0
    rows = [m.to_db_row() for m in messages]
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            if not per_row:
                await cur.executemany(_DANMU_INSERT_SQL, rows)
                return len(messages)
            inserted = 0
            for row in rows:
                try:
                    await cur.execute(_DANMU_INSERT_SQL, row)
                    inserted += 1
                except Exception:
                    try:
                        await conn.rollback()
                    except Exception:
                        pass
            return inserted


async def load_gift_catalog(pool: AsyncConnectionPool) -> dict[int, tuple[str | None, int | None]]:
    """加载全部礼物信息: gift_id -> (名称, 人民币价值)."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT gift_id, gift_name, value_rmb FROM gift_catalog WHERE id_type = 'gfid'"
            )
            rows = await cur.fetchall()
    catalog: dict[int, tuple[str | None, int | None]] = {}
    for row in rows:
        value = row["value_rmb"]
        catalog[row["gift_id"]] = (row["gift_name"], float(value) if value is not None else None)
    return catalog


async def query_gift_value(pool: AsyncConnectionPool, gift_id: int) -> tuple[str | None, int | None, int | None] | None:
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT gift_name, price_yu, value_rmb FROM gift_catalog "
                "WHERE id_type = 'gfid' AND gift_id = %s",
                (gift_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    price_yu = row["price_yu"]
    value_rmb = row["value_rmb"]
    return (
        row["gift_name"],
        int(price_yu) if price_yu is not None else None,
        float(value_rmb) if value_rmb is not None else None,
    )


async def query_gift_by_name(pool: AsyncConnectionPool, gift_name: str) -> tuple[int, str | None, int | None, int | None] | None:
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT gift_id, gift_name, price_yu, value_rmb FROM gift_catalog "
                "WHERE gift_name = %s "
                "ORDER BY (id_type = 'gfid') DESC, price_yu DESC NULLS LAST LIMIT 1",
                (gift_name,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    price_yu = row["price_yu"]
    value_rmb = row["value_rmb"]
    return (
        row["gift_id"],
        row["gift_name"],
        int(price_yu) if price_yu is not None else None,
        float(value_rmb) if value_rmb is not None else None,
    )
