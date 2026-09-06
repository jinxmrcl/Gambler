import json
import logging

import asyncpg

log = logging.getLogger("gambler")


class SupabaseBackup:
    """Best-effort off-site backup of every guild's SQLite data.

    Stores each guild's full table dump as one JSONB blob rather than trying to
    mirror the relational schema into Postgres — this is a disaster-recovery
    copy, never queried live, so a generic blob is far less risky to keep
    correct than hand-porting ~20 tables' worth of DDL/upserts to a second
    dialect.
    """

    def __init__(self, dsn: str):
        self._dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self, *, retries: int = 2, retry_delay: float = 3.0) -> None:
        import asyncio

        for attempt in range(1, retries + 1):
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=self._dsn, min_size=1, max_size=5, command_timeout=15, statement_cache_size=0
                )
                break
            except Exception:
                if attempt == retries:
                    log.exception("[supabase-backup] could not connect after %d attempts", retries)
                    raise
                await asyncio.sleep(retry_delay)
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_backups (
                    guild_id BIGINT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS global_backup (
                    id SMALLINT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_daily_backups (
                    guild_id BIGINT NOT NULL,
                    backup_date DATE NOT NULL,
                    data JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (guild_id, backup_date)
                )
                """
            )

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    async def push_guild_snapshot(self, guild_id: int, tables: dict[str, list[dict]]) -> None:
        payload = json.dumps(tables, default=str)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO guild_backups (guild_id, data, updated_at) VALUES ($1, $2::jsonb, now()) "
                "ON CONFLICT (guild_id) DO UPDATE SET data = EXCLUDED.data, updated_at = EXCLUDED.updated_at",
                guild_id,
                payload,
            )

    async def pull_guild_snapshot(self, guild_id: int) -> dict[str, list[dict]] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT data FROM guild_backups WHERE guild_id = $1", guild_id)
        if row is None:
            return None
        data = row[0]
        return data if isinstance(data, dict) else json.loads(data)

    async def known_guild_ids(self) -> list[int]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT guild_id FROM guild_backups")
        return [r[0] for r in rows]

    async def push_global_snapshot(self, data: dict[str, dict]) -> None:
        """Stores one combined blob covering every guild — a convenient single
        "everything, as of this run" copy, separate from the per-guild rows above."""
        payload = json.dumps(data, default=str)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO global_backup (id, data, updated_at) VALUES (1, $1::jsonb, now()) "
                "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, updated_at = EXCLUDED.updated_at",
                payload,
            )

    async def pull_global_snapshot(self) -> dict[str, dict] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT data FROM global_backup WHERE id = 1")
        if row is None:
            return None
        data = row[0]
        return data if isinstance(data, dict) else json.loads(data)

    async def pull_guild_from_global(self, guild_id: int) -> dict[str, list[dict]] | None:
        global_data = await self.pull_global_snapshot()
        if global_data is None:
            return None
        return global_data.get(str(guild_id))

    async def push_guild_daily_snapshot(self, guild_id: int, day: str, tables: dict[str, list[dict]]) -> None:
        payload = json.dumps(tables, default=str)
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO guild_daily_backups (guild_id, backup_date, data, created_at) "
                "VALUES ($1, $2::date, $3::jsonb, now()) "
                "ON CONFLICT (guild_id, backup_date) DO UPDATE SET data = EXCLUDED.data, created_at = EXCLUDED.created_at",
                guild_id,
                day,
                payload,
            )

    async def pull_guild_daily_snapshot(self, guild_id: int, day: str) -> dict[str, list[dict]] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT data FROM guild_daily_backups WHERE guild_id = $1 AND backup_date = $2::date",
                guild_id,
                day,
            )
        if row is None:
            return None
        data = row[0]
        return data if isinstance(data, dict) else json.loads(data)

    async def prune_daily_backups(self, keep_days: int = 30) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM guild_daily_backups WHERE backup_date < (now() - ($1 || ' days')::interval)::date",
                keep_days,
            )
