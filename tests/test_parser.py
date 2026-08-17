from datetime import datetime, timezone
from decimal import Decimal

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


def test_to_db_row_naive_cst():
    event = parser.parse_gift(protocol.parse_body(SAMPLE), 288016, 1, NOW, SAMPLE)
    row = event.to_db_row()
    assert row[0].startswith("dgb:")
    assert row[1] == 288016
    assert row[13].tzinfo is None
    assert row[13] == datetime(2026, 7, 31, 20, 0, 0)
    assert row[14] == datetime(2026, 7, 31, 20, 0, 0)


CHATMSG = ("type@=chatmsg/rid@=12598324/ct@=1/uid@=2566587/nn@=Archy木昜/"
           "txt@=糯糯不敢玩龚建？/cid@=c1deae55076248455eaa130000000000/"
           "ic@=avatar@S002@S56@S65@S87_avatar/level@=33/sahf@=0/cst@=1785509178266/"
           "bnn@=/bl@=0/brid@=0/hc@=/lk@=/dms@=4/pdg@=41/pdk@=88/ext@=/if@=1/")
PANDORA = ("btype@=pandora/chatmsg@=nn@A=打死不吃西红柿A@Sbnn@A=冬瓜强@Slevel@A=41@Sbrid@A=63136"
           "@Sdiaf@A=1@Sbl@A=28@Stype@A=chatmsg@Srid@A=12598324@Sgag@A=0@Suid@A=339634851/"
           "range@=2/cprice@=0/cmgType@=0/type@=comm_chatmsg/rid@=12598324/txt6@=4066/gbtemp@=15/"
           "uid@=339634851/txt4@=盛夏草帽/txt5@=，并送给了主播/crealPrice@=0/cet@=0/"
           "txt2@=https:@S@Sgfs-op.douyucdn.cn@Sdygift@S2026@S07@S24@Sd8d33b04c8aa5cd909766978582f4921.png@Srs144/"
           "txt3@=，开出/now@=1785509711867/txt1@=赠送主播/csuperScreen@=0/danmucr@=0/")


def test_parse_danmu():
    danmu = parser.parse_danmu(protocol.parse_body(CHATMSG), 12598324, 3, NOW, CHATMSG)
    assert danmu is not None
    assert danmu.message_id == "danmu:c1deae55076248455eaa130000000000"
    assert danmu.sender_uid == 2566587
    assert danmu.sender_nickname == "Archy木昜"
    assert danmu.content == "糯糯不敢玩龚建？"
    assert danmu.level == 33
    assert danmu.btype is None
    assert danmu.port == 3
    assert danmu.room_id == 12598324
    assert danmu.sent_at is not None
    assert danmu.sent_at.tzinfo is not None


def test_parse_danmu_pandora():
    danmu = parser.parse_danmu(protocol.parse_body(PANDORA), 12598324, 5, NOW, PANDORA)
    assert danmu is not None
    assert danmu.btype == "pandora"
    assert danmu.sender_uid == 339634851
    assert danmu.sender_nickname == "冬瓜强"
    assert danmu.level == 41
    assert "盛夏草帽" in danmu.content
    assert danmu.sent_at is not None
    assert danmu.message_id.startswith("dgb:")
    row = danmu.to_db_row()
    assert row[9] == "pandora"
    assert row[6].tzinfo is None


def test_parse_danmu_non_chat():
    assert parser.parse_danmu({"type": "dgb"}, 1, 0, NOW, "x") is None
    assert parser.parse_danmu({"type": "chatmsg", "uid": ""}, 1, 0, NOW, "x") is not None


def test_danmu_cid_fallback():
    body = "type@=chatmsg/uid@=1/nn@=x/txt@=hello/"
    danmu = parser.parse_danmu(protocol.parse_body(body), 1, 0, NOW, body)
    assert danmu is not None
    assert danmu.message_id.startswith("dgb:")

    danmu2 = parser.parse_danmu(protocol.parse_body(body), 1, 5, NOW, body)
    assert danmu2.message_id == danmu.message_id


def test_danmu_row_values():
    danmu = parser.parse_danmu(protocol.parse_body(CHATMSG), 12598324, 2, NOW, CHATMSG)
    row = danmu.to_db_row()
    assert row[0] == "danmu:c1deae55076248455eaa130000000000"
    assert row[1] == 12598324
    assert row[2] == 2566587
    assert row[3] == "Archy木昜"
    assert row[4] == "糯糯不敢玩龚建？"
    assert row[5] == 33
    assert row[6].tzinfo is None
    assert row[6] == datetime(2026, 7, 31, 22, 46, 18, 266000)
    assert row[7] == datetime(2026, 7, 31, 20, 0, 0)
    assert row[9] is None


DFOBC = ("type@=dfobc/uid@=2319772/rid@=12598324/nick@=巴蒂batigoal/level@=25/pg@=1/fl@=12/"
         "bn@=偏心p/mn@=3/cdays@=1/price@=47400/rrid@=12598324/rnick@=糯糯p/eid@=3768/"
         "bet@=1786555574/dfgm@=3/")
DFRBC = ("type@=dfrbc/uid@=26960719/rid@=12598324/nick@=假牙糯/level@=40/fl@=20/"
         "bn@=偏心p/mn@=1/cdays@=47/price@=13800/rrid@=12598324/rnick@=糯糯p/eid@=5755/"
         "al@=3871@S2.8@S/bet@=1785510609/dfgm@=3/")


def test_parse_subscription_dfobc():
    event = parser.parse_subscription(protocol.parse_body(DFOBC), 12598324, 4, NOW, DFOBC)
    assert event is not None
    assert event.msg_type == "dfobc"
    assert event.gift_name == "钻粉开通"
    assert event.gift_id == 3768
    assert event.gift_count == 3
    assert event.total_price == 474
    assert event.gift_price == 158
    assert event.sender_uid == 2319772
    assert event.sender_nickname == "巴蒂batigoal"
    assert event.receive_uid is None
    assert event.gift_value == Decimal("158.00")
    assert event.total_value == Decimal("474.00")
    row = event.to_db_row()
    assert row[13].tzinfo is None
    assert row[13] == datetime(2026, 8, 13, 1, 26, 14)


def test_parse_subscription_dfrbc():
    event = parser.parse_subscription(protocol.parse_body(DFRBC), 12598324, 3, NOW, DFRBC)
    assert event is not None
    assert event.msg_type == "dfrbc"
    assert event.gift_name == "钻粉续费"
    assert event.gift_id == 5755
    assert event.gift_count == 1
    assert event.total_price == 138
    assert event.gift_price == 138
    assert event.sender_nickname == "假牙糯"


def test_parse_subscription_rejects_others():
    assert parser.parse_subscription({"type": "dgb"}, 1, 0, NOW, "x") is None
    assert parser.parse_subscription({"type": "dfobc", "eid": ""}, 1, 0, NOW, "x") is None
