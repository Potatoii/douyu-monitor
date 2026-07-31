from datetime import datetime, timezone

from core import parser, protocol

SAMPLE = "type@=dgb/rid@=288016/gfid@=324/gfcnt@=3/uid@=12345/nn@=张三/hits@=30/eid@=678"
REAL_SAMPLE = "type@=dgb/rid@=288016/gfid@=824/gs@=0/uid@=43116516/nn@=昵称/ic@=avatar@Sface@S201603@S15ddff30a71287817a73aabf4b36fd88/eid@=0/eic@=20052/level@=42/gfcnt@=1/hits@=1/bcnt@=1/bst@=2/ct@=14/bnn@=主播/bl@=2"
TARGETED_SAMPLE = "type@=dgb/rid@=9999/gfid@=0/gs@=0/uid@=11773621/nn@=送礼物的人/eid@=0/gfcnt@=42/hits@=42/bst@=13/ct@=0/brid@=9999/gpf@=1/pid@=3410/bnid@=1/bnl@=1/receive_uid@=204389/receive_nn@=yyfyyf/from@=2/pfm@=22470/pma@=2164592/mss@=2164532/bcst@=1/ce@=1/gfn@=飞机/fl@=23/bnidv2@=10001/bcstv2@=1/abstv2@=1/wbcstv2@=1/"
NOW = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)


def test_parse_gift():
    event = parser.parse_gift(protocol.parse_body(SAMPLE), 288016, 3, NOW, SAMPLE)
    assert event is not None
    assert event.gift_id == 324
    assert event.gift_count == 3
    assert event.sender_uid == 12345
    assert event.sender_nickname == "张三"
    assert event.hit_score == 30
    assert event.receive_uid == 678
    assert event.port == 3
    assert event.room_id == 288016
    assert event.message_id.startswith("dgb:")


def test_parse_real_dgb_sample():
    event = parser.parse_gift(protocol.parse_body(REAL_SAMPLE), 288016, 2, NOW, REAL_SAMPLE)
    assert event is not None
    assert event.gift_id == 824
    assert event.gift_count == 1
    assert event.sender_uid == 43116516
    assert event.hit_score == 1
    assert event.receive_uid == 0
    assert event.sent_at is None
    assert event.gift_name == ""


def test_parse_gift_gid_fallback():
    body = "type@=dgb/rid@=288016/gid@=324/gfcnt@=2"
    event = parser.parse_gift(protocol.parse_body(body), 288016, 0, NOW, body)
    assert event is not None
    assert event.gift_id == 324
    assert event.gift_count == 2


def test_parse_targeted_gift():
    event = parser.parse_gift(protocol.parse_body(TARGETED_SAMPLE), 9999, 1, NOW, TARGETED_SAMPLE)
    assert event is not None
    assert event.receive_uid == 204389
    assert event.gift_name == "飞机"


def test_parse_gift_defaults():
    body = "type@=dgb/rid@=288016/gid@=324"
    event = parser.parse_gift(protocol.parse_body(body), 288016, 0, NOW, body)
    assert event is not None
    assert event.gift_count == 1
    assert event.sender_uid == 0
    assert event.sender_nickname == ""
    assert event.gift_value is None
    assert event.total_value is None
    assert event.gift_name == ""


def test_parse_non_gift():
    assert parser.parse_gift({"type": "chatmsg"}, 1, 0, NOW, "x") is None


def test_parse_gift_missing_gid():
    body = "type@=dgb/rid@=288016"
    assert parser.parse_gift(protocol.parse_body(body), 288016, 0, NOW, body) is None


def test_message_id_stable_for_same_body():
    a = parser.parse_gift(protocol.parse_body(SAMPLE), 288016, 0, NOW, SAMPLE)
    b = parser.parse_gift(protocol.parse_body(SAMPLE), 288016, 5, NOW, SAMPLE)
    assert a.message_id == b.message_id


def test_to_db_row_naive_utc():
    event = parser.parse_gift(protocol.parse_body(SAMPLE), 288016, 1, NOW, SAMPLE)
    row = event.to_db_row()
    assert row[0].startswith("dgb:")
    assert row[1] == 288016
    assert row[13].tzinfo is None
