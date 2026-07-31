import json

from loguru import logger

from core import logger as core_logger


def test_raw_log_json(tmp_path):
    core_logger.setup_logging(str(tmp_path), retention_days=7)
    core_logger.log_raw(288016, 1, "dgb", "type@=dgb/gid@=324")
    logger.complete()
    files = list((tmp_path / "raw").glob("*.jsonl"))
    assert files
    line = json.loads(files[0].read_text(encoding="utf-8").strip().splitlines()[-1])
    extra = line["record"]["extra"]
    assert extra["stream"] == "raw"
    assert extra["room_id"] == 288016
    assert extra["port"] == 1
    assert extra["msg_type"] == "dgb"
    assert line["record"]["message"] == "type@=dgb/gid@=324"


def test_gift_log_json(tmp_path):
    core_logger.setup_logging(str(tmp_path), retention_days=7)
    core_logger.log_gift(288016, 2, "dgb:abc", {"gift_id": 324, "gift_count": 1})
    logger.complete()
    files = list((tmp_path / "gift").glob("*.jsonl"))
    assert files
    line = json.loads(files[0].read_text(encoding="utf-8").strip().splitlines()[-1])
    extra = line["record"]["extra"]
    assert extra["stream"] == "gift"
    assert extra["msg_id"] == "dgb:abc"
