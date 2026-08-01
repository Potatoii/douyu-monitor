import json
from datetime import timezone

from scripts.replay_gifts import _to_event, iter_log_lines


def _log_line(msg: dict, room_id: int = 1, port: int = 3, msg_id: str = "dgb:abc") -> str:
    return json.dumps(
        {
            "record": {
                "extra": {"stream": "gift", "room_id": room_id, "port": port, "msg_id": msg_id},
                "message": repr(msg),
                "time": {"timestamp": 1785513600.0},
            }
        },
        ensure_ascii=False,
    )


def test_to_event_parses_fields():
    line = json.loads(_log_line(
        {"port": 3, "gift_id": 35213, "gift_count": 2, "sender_uid": 42, "sender_nickname": "水友"},
        room_id=9999,
    ))
    event = _to_event(
        line["record"]["extra"],
        line["record"]["message"],
        line["record"]["time"],
    )
    assert event is not None
    assert event.message_id == "dgb:abc"
    assert event.room_id == 9999
    assert event.sender_uid == 42
    assert event.sender_nickname == "水友"
    assert event.gift_id == 35213
    assert event.gift_count == 2
    assert event.port == 3
    assert event.received_at.tzinfo == timezone.utc


def test_to_event_bad_lines_return_none():
    assert _to_event({}, None, {}) is None
    assert _to_event({"msg_id": "x"}, {"gift_id": "abc"}, {"timestamp": 1}) is None


def test_iter_log_lines_filters(tmp_path):
    f = tmp_path / "2026-08-01.jsonl"
    f.write_text(
        _log_line({"gift_id": 1, "gift_count": 1, "sender_uid": 1, "sender_nickname": "a"}, room_id=100, msg_id="m1")
        + "\n"
        + _log_line({"gift_id": 2, "gift_count": 1, "sender_uid": 2, "sender_nickname": "b"}, room_id=200, msg_id="m2")
        + "\n",
        encoding="utf-8",
    )
    all_events = list(iter_log_lines(tmp_path, None, None))
    assert [e.message_id for e in all_events] == ["m1", "m2"]
    room_only = list(iter_log_lines(tmp_path, None, 200))
    assert [e.message_id for e in room_only] == ["m2"]
    dated = list(iter_log_lines(tmp_path, "2026-08-01", None))
    assert len(dated) == 2
