import asyncio
import time
from datetime import datetime, timezone

from config.settings import Settings
from core import logger, parser
from core.connection import DanmuConnection, NUM_PORTS
from core.protocol import parse_body
from dedup.deduper import Deduper
from services.price_service import PriceService
from storage.database import Database
from storage import repository


class GiftMonitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.room_ids = settings.room_ids
        if not self.room_ids:
            raise ValueError("no rooms configured, set ROOMS in .env or pass --room")
        self.deduper = Deduper(max_size=settings.dedup_max_size)
        self.queue: asyncio.Queue[parser.GiftEvent] = asyncio.Queue(maxsize=50_000)
        self.danmu_deduper = Deduper(max_size=settings.dedup_max_size)
        self.danmu_queue: asyncio.Queue[parser.DanmuMessage] = asyncio.Queue(maxsize=50_000)
        self.database: Database | None = None
        self.price_service: PriceService | None = None
        self.connections: list[DanmuConnection] = []

    async def run(self) -> None:
        self.database = Database(self.settings.db_dsn)
        await self.database.open()
        self.price_service = PriceService(self.database.pool())
        logger.log_system(f"database connected, rooms={self.room_ids}")

        for room_id in self.room_ids:
            for port in range(1, NUM_PORTS + 1):
                self.connections.append(
                    DanmuConnection(
                        room_id,
                        port,
                        self.on_message,
                        heartbeat_interval=self.settings.heartbeat_interval,
                        heartbeat_timeout=self.settings.heartbeat_timeout,
                    )
                )
        tasks = [
            asyncio.create_task(conn.run(), name=f"conn-room{conn.room_id}-p{conn.port}")
            for conn in self.connections
        ]
        tasks.append(asyncio.create_task(self._consumer_loop(), name="consumer"))
        if self.settings.danmu_enabled:
            tasks.append(asyncio.create_task(self._danmu_consumer_loop(), name="danmu-consumer"))
        logger.log_system(f"monitor started, {len(self.connections)} connections, danmu={self.settings.danmu_enabled}")
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.database.close()

    async def on_message(self, room_id: int, port: int, body: str) -> None:
        fields = parse_body(body)
        msg_type = fields.get("type", "")
        logger.log_raw(room_id, port, msg_type, body)
        if self.settings.danmu_enabled and (
            msg_type == "chatmsg" or (msg_type == "comm_chatmsg" and fields.get("btype"))
        ):
            await self._handle_danmu(room_id, port, fields, body)
            return
        if msg_type not in ("dgb", "dfobc", "dfrbc"):
            return
        event = parser.parse_gift(fields, room_id, port, datetime.now(timezone.utc), body)
        if event is None:
            event = parser.parse_subscription(
                fields, room_id, port, datetime.now(timezone.utc), body
            )
        if event is None or not self.deduper.is_new(event.message_id):
            return
        logger.log_gift(room_id, port, event.message_id, {
            "port": port,
            "gift_id": event.gift_id,
            "gift_count": event.gift_count,
            "sender_uid": event.sender_uid,
            "sender_nickname": event.sender_nickname,
        })
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.log_error("gift queue full, dropped", room_id=room_id, port=port)

    async def _handle_danmu(
        self, room_id: int, port: int, fields: dict[str, str], body: str
    ) -> None:
        danmu = parser.parse_danmu(fields, room_id, port, datetime.now(timezone.utc), body)
        if danmu is None or not self.danmu_deduper.is_new(danmu.message_id):
            return
        logger.log_danmu(room_id, port, danmu.message_id, {
            "port": port,
            "sender_uid": danmu.sender_uid,
            "sender_nickname": danmu.sender_nickname,
            "btype": danmu.btype,
            "content": danmu.content[:100],
        })
        try:
            self.danmu_queue.put_nowait(danmu)
        except asyncio.QueueFull:
            logger.log_error("danmu queue full, dropped", room_id=room_id, port=port)

    async def _consumer_loop(self) -> None:
        batch: list[parser.GiftEvent] = []
        flush_interval = self.settings.flush_interval
        batch_size = self.settings.batch_size
        deadline = time.monotonic() + flush_interval
        last_heartbeat = time.monotonic()
        while True:
            now = time.monotonic()
            if now - last_heartbeat >= 15:
                last_heartbeat = now
                logger.log_system(
                    f"consumer heartbeat: queue={self.queue.qsize()} pending={len(batch)}"
                )
            timeout = max(0.0, deadline - now)
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout)
            except asyncio.TimeoutError:
                event = None
                if not batch:
                    deadline = time.monotonic() + flush_interval
            if event is not None and self.price_service is not None:
                await self.price_service.enrich(event)
                batch.append(event)
            if batch and (len(batch) >= batch_size or time.monotonic() >= deadline):
                await self._flush(batch)
                batch = []
                deadline = time.monotonic() + flush_interval

    async def _danmu_consumer_loop(self) -> None:
        batch: list[parser.DanmuMessage] = []
        flush_interval = self.settings.danmu_flush_interval
        batch_size = self.settings.danmu_batch_size
        deadline = time.monotonic() + flush_interval
        while True:
            timeout = max(0.0, deadline - time.monotonic())
            try:
                danmu = await asyncio.wait_for(self.danmu_queue.get(), timeout)
            except asyncio.TimeoutError:
                danmu = None
                if not batch:
                    deadline = time.monotonic() + flush_interval
            if danmu is not None:
                batch.append(danmu)
            if batch and (len(batch) >= batch_size or time.monotonic() >= deadline):
                await self._flush_danmu(batch)
                batch = []
                deadline = time.monotonic() + flush_interval

    async def _flush_danmu(self, batch: list[parser.DanmuMessage]) -> None:
        if self.database is None:
            return
        if self.settings.insert_per_row:
            inserted = await repository.insert_danmu_messages(self.database.pool(), batch, per_row=True)
            if inserted < len(batch):
                logger.log_error(f"danmu per-row insert: {len(batch) - inserted}/{len(batch)} failed and skipped")
            return
        for attempt in range(3):
            try:
                await repository.insert_danmu_messages(self.database.pool(), batch)
                logger.log_system(f"flushed {len(batch)} danmu messages", msg_id=batch[0].message_id)
                return
            except Exception as exc:
                logger.log_error(f"danmu insert failed (attempt {attempt + 1}): {exc}")
                await asyncio.sleep(1.0 * (attempt + 1))
        logger.log_error(f"danmu insert failed after retries, dropped {len(batch)} messages")

    async def _flush(self, batch: list[parser.GiftEvent]) -> None:
        if self.database is None:
            return
        if self.settings.insert_per_row:
            inserted = await repository.insert_gift_events(self.database.pool(), batch, per_row=True)
            if inserted < len(batch):
                logger.log_error(f"per-row insert: {len(batch) - inserted}/{len(batch)} failed and skipped")
            return
        for attempt in range(3):
            try:
                await repository.insert_gift_events(self.database.pool(), batch)
                logger.log_system(f"flushed {len(batch)} gift events", msg_id=batch[0].message_id)
                return
            except Exception as exc:
                logger.log_error(f"insert failed (attempt {attempt + 1}): {exc}")
                await asyncio.sleep(1.0 * (attempt + 1))
        logger.log_error(f"insert failed after retries, dropped {len(batch)} events")
