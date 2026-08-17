"""导出 gift_catalog 表为 JSON 文件.

用法: python -m scripts.export_gifts [--output gift_catalog.json]
格式: {"gfid": {"192": {"name": "赞", "price_yu": 0, "value_rmb": 0}, ...}, "pid": {...}, "pgid": {...}}
price 单位为"元", 与数据库 price_yu/value_rmb 一致. 每组内按 gift_id 数字升序排列.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from storage.database import Database


async def main() -> None:
    parser = argparse.ArgumentParser(description="导出 gift_catalog 为 JSON")
    parser.add_argument("--output", default="gift_catalog.json", help="输出文件路径")
    args = parser.parse_args()

    db = Database(Settings().db_dsn)
    await db.open()
    try:
        async with db.pool().connection() as conn:
            rows = await (await conn.execute(
                "SELECT id_type, gift_id, gift_name, price_yu, value_rmb, source "
                "FROM gift_catalog ORDER BY id_type, gift_id"
            )).fetchall()
    finally:
        await db.close()

    data: dict[str, dict[str, dict]] = {"gfid": {}, "pid": {}, "pgid": {}}
    for id_type, gift_id, name, price_yu, value_rmb, source in rows:
        data[id_type][str(gift_id)] = {
            "name": name,
            "price_yu": float(price_yu or 0),
            "value_rmb": float(value_rmb or 0),
            "source": source or "",
        }

    out = Path(args.output)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = {k: len(v) for k, v in data.items()}
    print(f"exported {sum(counts.values())} gifts -> {out}: {counts}")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)