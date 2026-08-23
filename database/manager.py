import asyncio
from pathlib import Path

from .guild_db import GuildDatabase


class GuildDatabaseManager:
    """Owns one isolated GuildDatabase (SQLite file) per Discord guild, created lazily."""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._instances: dict[int, GuildDatabase] = {}
        self._create_lock = asyncio.Lock()

    def _path_for(self, guild_id: int) -> Path:
        return self._base_dir / f"{guild_id}.db"

    async def get(self, guild_id: int) -> GuildDatabase:
        db = self._instances.get(guild_id)
        if db is not None:
            return db
        async with self._create_lock:
            db = self._instances.get(guild_id)
            if db is not None:
                return db
            db = GuildDatabase(guild_id, self._path_for(guild_id))
            await db.connect()
            self._instances[guild_id] = db
            return db

    def loaded_guild_ids(self) -> list[int]:
        return list(self._instances.keys())

    def known_guild_ids(self) -> list[int]:
        """Guild ids with an existing database file on disk, even if not yet loaded."""
        if not self._base_dir.exists():
            return []
        ids = []
        for f in self._base_dir.glob("*.db"):
            try:
                ids.append(int(f.stem))
            except ValueError:
                continue
        return ids

    async def close_all(self) -> None:
        for db in self._instances.values():
            await db.close()
        self._instances.clear()
