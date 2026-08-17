"""抓取活动配置中的礼物列表导入 gift_catalog.

用法: python -m scripts.fetch_activity_gifts [--replace]

来源:
1. actqx202608_w.json (wconf 活动配置): gift_setting + valentine_room 秒杀礼物
2. pandora config (japi): ratio 表里的 pid 礼物及价值(单位=角, 0.1 元)

七夕秒杀礼物(4072-4077/4080)无官方价格, 按 0 入库.
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

ACTQX_URL = "https://wconf.douyucdn.cn/resource/common/activity/actqx202608_w.json"
PANDORA_URL = "https://www.douyu.com/japi/interact/comm/pandora/config?rid=12878454"

INSERT_SQL = """
INSERT INTO gift_catalog (id_type, gift_id, gift_name, price_yu, value_rmb)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (id_type, gift_id) DO UPDATE
SET gift_name = EXCLUDED.gift_name,
    price_yu  = EXCLUDED.price_yu,
    value_rmb = EXCLUDED.value_rmb,
    updated_at = now()
"""


def _get(url: str) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_actqx() -> list[tuple[str, int, str, float]]:
    data = _get(ACTQX_URL).get("data", {})
    rows: list[tuple[str, int, str, float]] = []

    gs = data.get("gift_setting") or {}
    if gs.get("giftId"):
        rows.append(("gfid", int(gs["giftId"]), gs.get("giftName", ""),
                     float(gs.get("giftPrice") or 0)))

    fame = (data.get("fameAttributes") or {}).get("halfHourFame") or {}
    if fame.get("giftId"):
        rows.append(("gfid", int(fame["giftId"]), fame.get("giftName", ""),
                     float(fame.get("giftPrice") or 0)))

    vr = data.get("valentine_room") or {}
    seen: set[int] = set()
    for floor_key in ("normalFloorList", "specialFloorList"):
        for floor in vr.get(floor_key) or []:
            task = (floor.get("taskConfig") or {}).get("seckillTask") or {}
            for prop in task.get("propList") or []:
                gid = prop.get("giftId")
                if gid and gid not in seen:
                    seen.add(gid)
                    if gid >= 20000:
                        continue  # 办卡/飞机/火箭等标准礼物已存在
                    rows.append(("pid", int(gid), prop.get("giftName", ""), 0.0))
    if vr.get("freePropId") and int(vr["freePropId"]) not in seen:
        rows.append(("pid", int(vr["freePropId"]), vr.get("freePropName", ""), 0.0))
    return rows


def collect_pandora() -> list[tuple[str, int, str, float]]:
    data = _get(PANDORA_URL).get("data", {})
    rows: list[tuple[str, int, str, float]] = []
    seen: set[int] = set()
    for activity in data.values():
        for ratio in (activity.get("ratio") or {}).values():
            for award in ratio.get("award") or []:
                pid = award.get("pid")
                if pid and pid not in seen:
                    seen.add(pid)
                    rows.append(("pid", int(pid), award.get("name", ""),
                                 float(award.get("value") or 0) / 10.0))
    return rows


async def main() -> None:
    parser = argparse.ArgumentParser(description="抓取活动礼物导入 gift_catalog")
    parser.add_argument("--replace", action="store_true", help="清空 pid 后全量导入")
    args = parser.parse_args()

    rows = collect_actqx() + collect_pandora()
    if not rows:
        print("no gifts fetched")
        sys.exit(1)

    db = Database(Settings().db_dsn)
    await db.open()
    try:
        async with db.pool().connection() as conn:
            if args.replace:
                await conn.execute("DELETE FROM gift_catalog WHERE id_type = 'pid'")
            async with conn.cursor() as cur:
                await cur.executemany(INSERT_SQL, [(t, g, n, p, p) for t, g, n, p in rows])
        by_type = {}
        for t, *_ in rows:
            by_type[t] = by_type.get(t, 0) + 1
        print(f"imported {len(rows)} activity gifts: {by_type}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)