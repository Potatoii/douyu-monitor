from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    rooms: str = ""
    db_dsn: str = "postgresql://douyu:douyu@localhost:5432/douyu_monitor"
    log_dir: str = "logs"
    log_retention_days: int = 7
    heartbeat_interval: int = 45
    heartbeat_timeout: int = 90
    dedup_max_size: int = 200_000
    batch_size: int = 50
    flush_interval: float = 2.0

    @property
    def room_ids(self) -> list[int]:
        return [int(x.strip()) for x in self.rooms.split(",") if x.strip()]

    def add_rooms(self, room_ids: list[int]) -> None:
        existing = set(self.room_ids)
        merged = existing | {int(r) for r in room_ids}
        self.rooms = ",".join(str(r) for r in sorted(merged))
