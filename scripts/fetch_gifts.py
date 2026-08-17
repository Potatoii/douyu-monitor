"""抓取斗鱼礼物列表 (gift v5 web list) 导入 gift_catalog.

用法: python -m scripts.fetch_gifts --rid 12878454 [--replace]

来源: https://gift.douyucdn.cn/api/gift/v5/web/list?rid=<rid>
priceInfo.price 单位为分(=0.01元), 与 gift.json 一致, 导入时 ÷100 存元.

默认按 (id_type='gfid', gift_id) 幂等 upsert; --replace 先清空 gfid 再全量导入.
"""

import argparse
import asyncio
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import Settings
from storage.database import Database

API = "https://gift.douyucdn.cn/api/gift/v5/web/list?rid={rid}"

INSERT_SQL = """
INSERT INTO gift_catalog (id_type, gift_id, gift_name, price_yu, value_rmb, source)
VALUES ('gfid', %s, %s, %s, %s, %s)
ON CONFLICT (id_type, gift_id) DO UPDATE
SET gift_name = EXCLUDED.gift_name,
    price_yu  = EXCLUDED.price_yu,
    value_rmb = EXCLUDED.value_rmb,
    source     = EXCLUDED.source,
    updated_at = now()
"""


def fetch_gifts(rid: int) -> list[tuple[int, str, float]]:
    req = urllib.request.Request(
        API.format(rid=rid),
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": f"https://www.douyu.com/{rid}",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    rows: list[tuple[int, str, float, str]] = []
    for gift in data.get("data", {}).get("giftList", []):
        gid = gift.get("id")
        name = (gift.get("name") or "").strip()
        price_info = gift.get("priceInfo") or {}
        price = price_info.get("price") or 0
        if gid is not None:
            rows.append((int(gid), name, float(price) / 100.0, API.format(rid=rid)))
    return rows


async def main() -> None:
    parser = argparse.ArgumentParser(description="抓取斗鱼礼物列表导入 gift_catalog")
    parser.add_argument("--rid", type=int, required=True, help="直播间 ID")
    parser.add_argument("--replace", action="store_true", help="清空 gfid 后全量导入")
    parser.add_argument("--dump", default=None, help="先把抓取结果写入 JSON 文件不写库")
    args = parser.parse_args()

    rows = fetch_gifts(args.rid)
    if not rows:
        print(f"no gifts fetched for rid={args.rid}")
        sys.exit(1)
    print(f"fetched {len(rows)} gifts from rid={args.rid}")
    if args.dump:
        Path(args.dump).write_text(
            json.dumps([{"gift_id": r[0], "name": r[1], "price": r[2], "source": r[3]} for r in rows],
                       ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"dumped to {args.dump}, not writing db")
        return

    db = Database(Settings().db_dsn)
    await db.open()
    try:
        async with db.pool().connection() as conn:
            if args.replace:
                await conn.execute("DELETE FROM gift_catalog WHERE id_type = 'gfid'")
            async with conn.cursor() as cur:
                await cur.executemany(INSERT_SQL, [(g, n, p, p, src) for g, n, p, src in rows])
        print(f"imported {len(rows)} gifts into gift_catalog (gfid)")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)