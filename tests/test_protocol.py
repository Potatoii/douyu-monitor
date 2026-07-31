from core import protocol


def test_pack_unpack_roundtrip():
    msg = "type@=mrkl/"
    packet = protocol.pack_message(msg)
    assert len(packet) == protocol.HEADER_SIZE + len(msg) + 1
    body_len, msg_type, encrypt = protocol.unpack_header(packet[: protocol.HEADER_SIZE])
    assert body_len == len(msg) + 1
    assert msg_type == protocol.TYPE_CLIENT
    assert encrypt == 0
    assert packet[protocol.HEADER_SIZE :] == msg.encode("utf-8") + b"\x00"


def test_pack_client_type_default():
    packet = protocol.pack_message("x")
    _, msg_type, _ = protocol.unpack_header(packet[:12])
    assert msg_type == 689


def test_unpack_invalid_header():
    try:
        protocol.unpack_header(b"short")
        raise AssertionError("should raise")
    except protocol.ProtocolError:
        pass


def test_decrypt_body():
    plain = b"type@=dgb/gid@=324"
    encrypted = bytes(b ^ protocol.ENCRYPT_XOR_KEY for b in reversed(plain))
    assert protocol.decrypt_body(encrypted) == plain


def test_parse_body():
    fields = protocol.parse_body("type@=dgb/uid@=1/nn@=a b/c@=x/y@=1")
    assert fields == {"type": "dgb", "uid": "1", "nn": "a b", "c": "x", "y": "1"}


def test_build_messages():
    assert protocol.build_heartbeat() == "type@=mrkl/"
    assert protocol.build_login_request(288016) == "type@=loginreq/roomid@=288016/"
    assert protocol.build_join_group(288016) == "type@=joingroup/rid@=288016/gid@=-9999"
