import asyncio
import ssl
import time
from collections.abc import Awaitable, Callable

import websockets

from core import logger, protocol

MessageHandler = Callable[[int, int, str], Awaitable[None]]

CDN_HOST = "danmuproxy.douyu.com"
NUM_PORTS = 6

# 斗鱼 CDN 仅支持非 ECDHE 的 TLS1.2 套件，默认 ClientHello 会被拒绝
DOUYU_CIPHERS = "AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA:AES256-SHA"


def make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers(DOUYU_CIPHERS)
    return ctx


class DanmuConnection:
    def __init__(
        self,
        room_id: int,
        port: int,
        on_message: MessageHandler,
        heartbeat_interval: float = 45.0,
        heartbeat_timeout: float = 90.0,
        max_retry_delay: float = 60.0,
    ):
        self.room_id = room_id
        self.port = port
        self._on_message = on_message
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._max_retry_delay = max_retry_delay
        self.url = f"wss://{CDN_HOST}:850{port}"
        self._last_packet_ts = 0.0

    async def run(self) -> None:
        retry_delay = 1.0
        while True:
            try:
                await self._connect_once()
                retry_delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.log_error(
                    f"connection {self.url} failed: {exc}",
                    room_id=self.room_id,
                    port=self.port,
                )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, self._max_retry_delay)

    async def _connect_once(self) -> None:
        async with websockets.connect(
            self.url,
            ssl=make_ssl_context(),
            origin="https://www.douyu.com",
            ping_interval=None,
            ping_timeout=None,
            max_size=2**24,
            open_timeout=15,
        ) as ws:
            self._last_packet_ts = time.monotonic()
            await ws.send(protocol.pack_message(protocol.build_login_request(self.room_id)))
            await ws.send(protocol.pack_message(protocol.build_join_group(self.room_id)))
            logger.log_system(
                f"connected {self.url} room={self.room_id}",
                room_id=self.room_id,
                port=self.port,
            )
            heartbeat = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                await self._recv_loop(ws)
            finally:
                heartbeat.cancel()

    async def _heartbeat_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        while True:
            await asyncio.sleep(self._heartbeat_interval)
            idle = time.monotonic() - self._last_packet_ts
            if idle > self._heartbeat_timeout:
                logger.log_error(
                    f"heartbeat timeout ({idle:.0f}s idle)",
                    room_id=self.room_id,
                    port=self.port,
                )
                await ws.close()
                return
            try:
                await ws.send(protocol.pack_message(protocol.build_heartbeat()))
            except Exception as exc:
                logger.log_error(
                    f"heartbeat send failed: {exc}",
                    room_id=self.room_id,
                    port=self.port,
                )
                raise

    async def _recv_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        buffer = bytearray()
        async for message in ws:
            if not isinstance(message, bytes):
                message = bytes(message)
            buffer.extend(message)
            while len(buffer) >= protocol.HEADER_SIZE:
                try:
                    body_len, msg_type, encrypt = protocol.unpack_header(bytes(buffer[: protocol.HEADER_SIZE]))
                except protocol.ProtocolError as exc:
                    logger.log_error(f"bad header: {exc}", room_id=self.room_id, port=self.port)
                    del buffer[: protocol.HEADER_SIZE]
                    continue
                if len(buffer) < protocol.HEADER_SIZE + body_len:
                    break
                body = bytes(buffer[protocol.HEADER_SIZE : protocol.HEADER_SIZE + body_len])
                del buffer[: protocol.HEADER_SIZE + body_len]
                if encrypt == 2:
                    body = protocol.decrypt_body(body)
                self._last_packet_ts = time.monotonic()
                if msg_type == protocol.TYPE_SERVER:
                    try:
                        text = body.decode("utf-8", errors="replace")
                    except UnicodeDecodeError:
                        logger.log_error("undecodable body", room_id=self.room_id, port=self.port)
                        continue
                    await self._on_message(self.room_id, self.port, text)
