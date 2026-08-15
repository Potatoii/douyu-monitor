"""实时抓取直播间 btype=pandora / fantasyIsland 消息并解析.

用法: python -m scripts.capture_btype <room_id> [duration_seconds]
默认监控 600 秒，Ctrl+C 提前退出。结果追加写入 logs/btype_capture.jsonl (UTF-8)。
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.connection import DanmuConnection
from core.protocol import parse_body

WATCH_TYPES = {"pandora", "fantasyIsland"}
OUT_PATH = Path(__file__).resolve().parents[1] / "logs" / "btype_capture.jsonl"
_seen: dict[str, set] = {t: set() for t in WATCH_TYPES}
_stats: dict[str, int] = {t: 0 for t in WATCH_TYPES}


def unescape(value: str) -> str:
    """反转义: @A= -> @=, @S -> / (斗鱼嵌套消息编码)."""
    return value.replace("@S", "/").replace("@A=", "@=")


def parse_btype_text(text: str) -> dict:
    text = text.rstrip("\x00")
    body = text.split("\n", 1)[0]
    outer = parse_body(body)
    result: dict = {"btype": outer.get("btype", "")}
    if "chatmsg" in outer:
        try:
            result["chatmsg"] = parse_body(unescape(outer["chatmsg"]))
        except Exception:
            result["chatmsg"] = outer["chatmsg"]
    for key in ("type", "uid", "rid", "now", "txt1", "txt2", "txt3", "txt4", "txt5", "txt6",
                "range", "cprice", "cmgType", "gbtemp"):
        if key in outer:
            result[key] = outer[key]
    return result


async def on_message(room_id: int, port: int, text: str) -> None:
    if "btype@=" not in text:
        return
    btype = parse_body(text.rstrip("\x00").split("\n", 1)[0]).get("btype", "")
    if btype not in WATCH_TYPES:
        return
    parsed = parse_btype_text(text)
    sig = json.dumps(parsed.get("chatmsg", ""), ensure_ascii=False, sort_keys=True)
    if sig in _seen[btype]:
        return
    _seen[btype].add(sig)
    _stats[btype] += 1
    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "room_id": room_id,
        "port": port,
        "parsed": parsed,
    }
    with open(OUT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


async def main() -> None:
    room_id = int(sys.argv[1]) if len(sys.argv) > 1 else 12598324
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
    print(f"watching room={room_id} for {duration:.0f}s -> {OUT_PATH}")
    conn = DanmuConnection(room_id=room_id, port=1, on_message=on_message)
    task = asyncio.create_task(conn.run())
    start = time.monotonic()
    try:
        while time.monotonic() - start < duration:
            await asyncio.sleep(30)
            print(f"[{time.strftime('%H:%M:%S')}] pandora={_stats['pandora']} fantasyIsland={_stats['fantasyIsland']}")
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    print(f"-- done: pandora={_stats['pandora']} fantasyIsland={_stats['fantasyIsland']} --")


if __name__ == "__main__":
    asyncio.run(main(), debug=False)