"""抓取 giftPhotos_w.json 图鉴礼物列表导入 gift_catalog.

用法: python -m scripts.fetch_gift_photos [--replace]

来源: https://wconf.douyucdn.cn/resource/common/giftPhotos_w.json
data.pgInfos: [{pgId, name, price(分), intimacy, lv, tab1, tab2, time}]
导入为 id_type='pgid', price ÷100 存元. --replace 先清空 pgid 再全量导入.
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

URL = "https://wconf.douyucdn.cn/resource/common/giftPhotos_w.json"

INSERT_SQL = """
INSERT INTO gift_catalog (id_type, gift_id, gift_name, price_yu, value_rmb, source)
VALUES ('pgid', %s, %s, %s, %s, %s)
ON CONFLICT (id_type, gift_id) DO UPDATE
SET gift_name = EXCLUDED.gift_name,
    price_yu  = EXCLUDED.price_yu,
    value_rmb = EXCLUDED.value_rmb,
    source     = EXCLUDED.source,
    updated_at = now()
"""


def fetch_photos() -> list[tuple[int, str, float]]:
    req = urllib.request.Request(
        URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    rows: list[tuple[int, str, float, str]] = []
    for p in data.get("data", {}).get("pgInfos", []):
        pgid = p.get("pgId")
        if pgid is None:
            continue
        rows.append((int(pgid), (p.get("name") or "").strip(),
                     float(p.get("price") or 0) / 100.0, URL))
    return rows


async def main() -> None:
    parser = argparse.ArgumentParser(description="抓取礼物图鉴导入 gift_catalog")
    parser.add_argument("--replace", action="store_true", help="清空 pgid 后全量导入")
    args = parser.parse_args()

    rows = fetch_photos()
    if not rows:
        print("no gifts fetched")
        sys.exit(1)
    print(f"fetched {len(rows)} pgid gifts")

    db = Database(Settings().db_dsn)
    await db.open()
    try:
        async with db.pool().connection() as conn:
            if args.replace:
                await conn.execute("DELETE FROM gift_catalog WHERE id_type = 'pgid'")
            async with conn.cursor() as cur:
                await cur.executemany(INSERT_SQL, [(g, n, p, p, s) for g, n, p, s in rows])
        print(f"imported {len(rows)} pgid gifts into gift_catalog")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)