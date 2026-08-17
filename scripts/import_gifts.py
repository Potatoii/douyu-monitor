"""礼物字典导入: 将斗鱼 gift.json 导入 gift_catalog 表.

用法: python -m scripts.import_gifts [--path gift.json] [--replace]
gift.json 结构: {"礼物ID": {"name": "礼物名", "price": 分值}}

斗鱼有三种 ID 命名空间，数字可能重复，分列存储:
- 数字键   -> id_type='gfid'  (dgb 消息中的真实礼物 ID)
- pid_X    -> id_type='pid'
- pgid_X   -> id_type='pgid'

price 单位为"分", 导入时换算为"元"存入 price_yu/value_rmb.
--replace 会先清空 gift_catalog 再全量导入, 默认按 (id_type, gift_id) 幂等 upsert.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from storage.database import Database

INSERT_SQL = """
INSERT INTO gift_catalog (id_type, gift_id, gift_name, price_yu, value_rmb, source)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (id_type, gift_id) DO UPDATE
SET gift_name = EXCLUDED.gift_name,
    price_yu  = EXCLUDED.price_yu,
    value_rmb = EXCLUDED.value_rmb,
    source     = EXCLUDED.source,
    updated_at = now()
"""

SOURCE = "gift.json"


def _split_key(key: str) -> tuple[str, int] | None:
    """把 JSON 键拆成 (id_type, gift_id); 无法识别返回 None."""
    if key.startswith("pid_"):
        return "pid", int(key[4:])
    if key.startswith("pgid_"):
        return "pgid", int(key[5:])
    try:
        return "gfid", int(key)
    except ValueError:
        return None


def load_gifts(path: Path) -> tuple[list[tuple[str, int, str, float, float, str]], int]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows: list[tuple[str, int, str, float, float, str]] = []
    skipped = 0
    for gid, info in data.items():
        split = _split_key(gid)
        if split is None:
            skipped += 1
            continue
        id_type, gid_i = split
        price = int(info.get("price") or 0)
        name = (info.get("name") or "").strip()
        rows.append((id_type, gid_i, name, price / 100.0, price / 100.0, SOURCE))
    return rows, skipped


async def main() -> None:
    parser = argparse.ArgumentParser(description="导入斗鱼礼物字典到 gift_catalog")
    parser.add_argument("--path", default="gift.json", help="gift.json 路径")
    parser.add_argument("--replace", action="store_true", help="清空 gift_catalog 后全量导入")
    args = parser.parse_args()

    rows, skipped = load_gifts(Path(args.path))
    if not rows:
        print(f"no valid gift rows in {args.path} (skipped {skipped})")
        sys.exit(1)

    db = Database(Settings().db_dsn)
    await db.open()
    try:
        async with db.pool().connection() as conn:
            if args.replace:
                await conn.execute("TRUNCATE gift_catalog")
            async with conn.cursor() as cur:
                await cur.executemany(INSERT_SQL, rows)
        by_type = {"gfid": 0, "pid": 0, "pgid": 0}
        for id_type, *_ in rows:
            by_type[id_type] += 1
        print(f"imported: {len(rows)} (skipped {skipped}): {by_type}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
