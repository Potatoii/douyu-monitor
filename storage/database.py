from psycopg_pool import AsyncConnectionPool


class Database:
    def __init__(self, dsn: str):
        self._pool = AsyncConnectionPool(
            dsn,
            min_size=1,
            max_size=5,
            open=False,
            kwargs={"connect_timeout": 10, "options": "-c timezone=Asia/Shanghai -c statement_timeout=15000"},
        )

    async def open(self) -> None:
        await self._pool.open()

    async def close(self) -> None:
        await self._pool.close()

    def pool(self) -> AsyncConnectionPool:
        return self._pool
