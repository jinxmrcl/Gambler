import asyncio
import contextlib
import datetime
import json
import logging
from pathlib import Path

import aiosqlite

from .errors import InsufficientFunds

log = logging.getLogger("gambler")


def _e(dt: datetime.datetime | None) -> str | None:
    """Encode a datetime for storage."""
    return dt.isoformat() if dt is not None else None


def _p(s) -> datetime.datetime | None:
    """Parse a stored value back into a datetime."""
    if s is None:
        return None
    if isinstance(s, datetime.datetime):
        return s
    return datetime.datetime.fromisoformat(s)


def _coerce(value):
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    return value


_UNSET = object()


class GuildDatabase:
    """A single guild's isolated SQLite-backed database (one file per guild)."""

    def __init__(self, guild_id: int, path: Path):
        self.guild_id = guild_id
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

        self._gamble_channel_cache = _UNSET
        self._guild_settings_cache = _UNSET
        self._updates_channel_cache = _UNSET
        self._level_boost_cache = _UNSET
        self._cooldown_bypass_cache: dict[int, bool] = {}

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._path), isolation_level=None)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=OFF")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA temp_store=MEMORY")
        await self._conn.execute("PRAGMA cache_size=-8000")
        await self._create_tables()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _execute(self, query: str, args: tuple = ()) -> int:
        cur = await self._conn.execute(query, args)
        rowcount = cur.rowcount
        await cur.close()
        return rowcount

    async def _fetchone(self, query: str, args: tuple = ()):
        cur = await self._conn.execute(query, args)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def _fetchall(self, query: str, args: tuple = ()):
        cur = await self._conn.execute(query, args)
        rows = await cur.fetchall()
        await cur.close()
        return rows

    @contextlib.asynccontextmanager
    async def _transaction(self):
        async with self._lock:
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except Exception:
                await self._conn.execute("ROLLBACK")
                raise
            else:
                await self._conn.execute("COMMIT")

    async def bulk_insert(self, table: str, rows: list[dict]) -> None:
        """Generic best-effort seed/restore helper used by migration/backup tooling."""
        if not rows:
            return
        cols = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in cols)
        col_list = ", ".join(f'"{c}"' for c in cols)
        query = f'INSERT OR IGNORE INTO "{table}" ({col_list}) VALUES ({placeholders})'
        values = [tuple(_coerce(r.get(c)) for c in cols) for r in rows]
        async with self._lock:
            await self._conn.executemany(query, values)

    async def dump_all_tables(self) -> dict[str, list[dict]]:
        cur = await self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [r[0] for r in await cur.fetchall()]
        await cur.close()
        result: dict[str, list[dict]] = {}
        for table in tables:
            cur = await self._conn.execute(f'SELECT * FROM "{table}"')
            cols = [d[0] for d in cur.description]
            rows = await cur.fetchall()
            await cur.close()
            result[table] = [dict(zip(cols, row)) for row in rows]
        return result

    async def _create_tables(self) -> None:
        conn = self._conn
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                bank_balance INTEGER NOT NULL DEFAULT 0,
                last_daily TEXT NULL,
                daily_streak INTEGER NOT NULL DEFAULT 0,
                protected_until TEXT NULL,
                cooldown_bypass INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_key)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stats (
                user_id INTEGER PRIMARY KEY,
                games_played INTEGER NOT NULL DEFAULT 0,
                total_wagered INTEGER NOT NULL DEFAULT 0,
                total_won INTEGER NOT NULL DEFAULT 0,
                biggest_win INTEGER NOT NULL DEFAULT 0,
                robs_attempted INTEGER NOT NULL DEFAULT 0,
                robs_succeeded INTEGER NOT NULL DEFAULT 0,
                times_robbed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                disabled_games TEXT NOT NULL DEFAULT '',
                allowed_channels TEXT NOT NULL DEFAULT ''
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gamble_channels (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                channel_id INTEGER NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS updates_channels (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                channel_id INTEGER NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS marriages (
                user_id INTEGER PRIMARY KEY,
                partner_id INTEGER NOT NULL,
                married_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS marriage_bank (
                user_id_a INTEGER NOT NULL,
                user_id_b INTEGER NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id_a, user_id_b)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lottery_tickets (
                user_id INTEGER PRIMARY KEY,
                quantity INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lottery_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                pot INTEGER NOT NULL DEFAULT 0,
                next_draw TEXT NOT NULL,
                channel_id INTEGER NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idle_tracker_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                message_id INTEGER NULL,
                posted_at TEXT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payday_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                next_payday TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idle_sessions (
                user_id INTEGER PRIMARY KEY,
                dungeon_key TEXT NOT NULL,
                display_name TEXT NOT NULL,
                deadline TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                stats_json TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS level_xp (
                user_id INTEGER PRIMARY KEY,
                xp INTEGER NOT NULL DEFAULT 0,
                message_xp INTEGER NOT NULL DEFAULT 0,
                voice_xp INTEGER NOT NULL DEFAULT 0,
                vc_seconds INTEGER NOT NULL DEFAULT 0,
                last_xp_at TEXT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS level_boost (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                multiplier REAL NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cooldowns (
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                PRIMARY KEY (user_id, action)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS item_use_limits (
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                use_count INTEGER NOT NULL DEFAULT 0,
                window_started_at TEXT NOT NULL,
                PRIMARY KEY (user_id, item_key)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS achievements (
                user_id INTEGER NOT NULL,
                achievement_key TEXT NOT NULL,
                unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, achievement_key)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vote_claims (
                user_id INTEGER PRIMARY KEY,
                last_claimed_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                user_id INTEGER PRIMARY KEY,
                class_key TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                xp INTEGER NOT NULL DEFAULT 0,
                equipped_weapon TEXT NULL,
                equipped_armor TEXT NULL,
                equipped_accessory TEXT NULL,
                equipped_shield TEXT NULL,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                current_hp INTEGER NULL,
                hp_updated_at TEXT NULL,
                weapon_enchant INTEGER NOT NULL DEFAULT 0,
                armor_enchant INTEGER NOT NULL DEFAULT 0,
                accessory_enchant INTEGER NOT NULL DEFAULT 0,
                shield_enchant INTEGER NOT NULL DEFAULT 0,
                equipped_primordial_weapon_id INTEGER NULL,
                equipped_primordial_armor_id INTEGER NULL,
                equipped_primordial_accessory_id INTEGER NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rpg_equipment (
                user_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_key)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS boss_kills (
                user_id INTEGER NOT NULL,
                dungeon_key TEXT NOT NULL,
                kills INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, dungeon_key)
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS primordial_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slot TEXT NOT NULL,
                affixes TEXT NOT NULL,
                dropped_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS character_backup (
                user_id INTEGER PRIMARY KEY,
                class_key TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                xp INTEGER NOT NULL DEFAULT 0,
                equipped_weapon TEXT NULL,
                equipped_armor TEXT NULL,
                equipped_accessory TEXT NULL,
                equipped_shield TEXT NULL,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                current_hp INTEGER NULL,
                hp_updated_at TEXT NULL,
                weapon_enchant INTEGER NOT NULL DEFAULT 0,
                armor_enchant INTEGER NOT NULL DEFAULT 0,
                accessory_enchant INTEGER NOT NULL DEFAULT 0,
                shield_enchant INTEGER NOT NULL DEFAULT 0,
                equipped_primordial_weapon_id INTEGER NULL,
                equipped_primordial_armor_id INTEGER NULL,
                equipped_primordial_accessory_id INTEGER NULL
            )
            """
        )
        await conn.execute(
            "INSERT OR IGNORE INTO lottery_state (id, pot, next_draw) VALUES (1, 0, ?)",
            (_e(datetime.datetime.utcnow() + datetime.timedelta(days=7)),),
        )


    async def ensure_user(self, user_id: int, starting_balance: int) -> None:
        await self._execute(
            "INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)",
            (user_id, starting_balance),
        )

    async def get_balance(self, user_id: int) -> int:
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        return row[0] if row else 0

    async def update_balance(self, user_id: int, delta: int) -> int:
        rowcount = await self._execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ? AND balance + ? >= 0",
            (delta, user_id, delta),
        )
        if rowcount == 0:
            raise InsufficientFunds(f"User {user_id} cannot afford a change of {delta}")
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        return row[0]

    async def debit_both(self, user_a_id: int, user_b_id: int, amount: int) -> None:
        async with self._transaction() as conn:
            for user_id in (user_a_id, user_b_id):
                cur = await conn.execute(
                    "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                    (amount, user_id, amount),
                )
                if cur.rowcount == 0:
                    exc = InsufficientFunds(f"User {user_id} cannot afford {amount}")
                    exc.user_id = user_id
                    raise exc

    async def transfer_balance(self, sender_id: int, recipient_id: int, amount: int) -> int:
        async with self._transaction() as conn:
            cur = await conn.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                (amount, sender_id, amount),
            )
            if cur.rowcount == 0:
                raise InsufficientFunds(f"User {sender_id} cannot afford a transfer of {amount}")
            await conn.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, recipient_id)
            )
            cur = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (sender_id,))
            row = await cur.fetchone()
            return row[0]

    async def set_balance(self, user_id: int, amount: int) -> None:
        await self._execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))

    async def claim_daily(
        self,
        user_id: int,
        base_amount: int,
        period: datetime.timedelta,
        now: datetime.datetime,
        *,
        bonus_per_day: float = 0.1,
        max_bonus_days: int = 10,
    ) -> tuple[int, int, int] | None:
        cutoff = now - period
        row = await self._fetchone(
            "SELECT last_daily, daily_streak FROM users WHERE user_id = ?", (user_id,)
        )
        last_daily, streak = (_p(row[0]), row[1]) if row else (None, 0)
        continues = last_daily is not None and (now - last_daily) <= period * 2
        new_streak = streak + 1 if continues else 1
        multiplier = 1 + bonus_per_day * min(new_streak - 1, max_bonus_days)
        payout = int(base_amount * multiplier)

        rowcount = await self._execute(
            "UPDATE users SET balance = balance + ?, last_daily = ?, daily_streak = ? "
            "WHERE user_id = ? AND (last_daily IS NULL OR last_daily <= ?)",
            (payout, _e(now), new_streak, user_id, _e(cutoff)),
        )
        if rowcount == 0:
            return None
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        return row[0], payout, new_streak

    async def get_last_daily(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
        return _p(row[0]) if row else None

    async def get_daily_streak(self, user_id: int) -> int:
        row = await self._fetchone("SELECT daily_streak FROM users WHERE user_id = ?", (user_id,))
        return row[0] if row else 0

    async def claim_vote_reward(
        self, user_id: int, amount: int, now: datetime.datetime, cooldown: datetime.timedelta
    ) -> int | None:
        cutoff = now - cooldown
        async with self._transaction() as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO vote_claims (user_id, last_claimed_at) VALUES (?, ?)",
                (user_id, _e(datetime.datetime.min)),
            )
            cur = await conn.execute(
                "UPDATE vote_claims SET last_claimed_at = ? "
                "WHERE user_id = ? AND last_claimed_at <= ?",
                (_e(now), user_id, _e(cutoff)),
            )
            if cur.rowcount == 0:
                return None
            await conn.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id)
            )
            cur = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            return row[0]

    async def get_last_vote_claim(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT last_claimed_at FROM vote_claims WHERE user_id = ?", (user_id,)
        )
        if not row or row[0] is None:
            return None
        claimed = _p(row[0])
        return claimed if claimed != datetime.datetime.min else None

    async def get_unlocked_achievements(self, user_id: int) -> set[str]:
        rows = await self._fetchall(
            "SELECT achievement_key FROM achievements WHERE user_id = ?", (user_id,)
        )
        return {row[0] for row in rows}

    async def unlock_achievement(self, user_id: int, key: str, now: datetime.datetime) -> bool:
        rowcount = await self._execute(
            "INSERT OR IGNORE INTO achievements (user_id, achievement_key, unlocked_at) VALUES (?, ?, ?)",
            (user_id, key, _e(now)),
        )
        return rowcount > 0

    async def top_balances(self, limit: int = 10) -> list[tuple[int, int]]:
        return await self._fetchall(
            "SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)
        )

    async def give_all_users(self, amount: int) -> int:
        return await self._execute("UPDATE users SET balance = MAX(balance + ?, 0)", (amount,))

    async def get_bank_balance(self, user_id: int) -> int:
        row = await self._fetchone("SELECT bank_balance FROM users WHERE user_id = ?", (user_id,))
        return row[0] if row else 0

    async def deposit_to_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        async with self._transaction() as conn:
            cur = await conn.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                (amount, user_id, amount),
            )
            if cur.rowcount == 0:
                raise InsufficientFunds(f"User {user_id} cannot deposit {amount}")
            await conn.execute(
                "UPDATE users SET bank_balance = bank_balance + ? WHERE user_id = ?", (amount, user_id)
            )
            cur = await conn.execute(
                "SELECT balance, bank_balance FROM users WHERE user_id = ?", (user_id,)
            )
            return await cur.fetchone()

    async def withdraw_from_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        async with self._transaction() as conn:
            cur = await conn.execute(
                "UPDATE users SET bank_balance = bank_balance - ? WHERE user_id = ? AND bank_balance >= ?",
                (amount, user_id, amount),
            )
            if cur.rowcount == 0:
                raise InsufficientFunds(f"User {user_id} cannot withdraw {amount}")
            await conn.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id)
            )
            cur = await conn.execute(
                "SELECT balance, bank_balance FROM users WHERE user_id = ?", (user_id,)
            )
            return await cur.fetchone()

    async def get_protected_until(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT protected_until FROM users WHERE user_id = ?", (user_id,)
        )
        return _p(row[0]) if row else None

    async def set_protected_until(self, user_id: int, when: datetime.datetime | None) -> None:
        await self._execute(
            "UPDATE users SET protected_until = ? WHERE user_id = ?", (_e(when), user_id)
        )

    async def has_cooldown_bypass(self, user_id: int) -> bool:
        cached = self._cooldown_bypass_cache.get(user_id)
        if cached is not None:
            return cached
        row = await self._fetchone(
            "SELECT cooldown_bypass FROM users WHERE user_id = ?", (user_id,)
        )
        value = bool(row[0]) if row else False
        self._cooldown_bypass_cache[user_id] = value
        return value

    async def set_cooldown_bypass(self, user_id: int, enabled: bool) -> None:
        await self._execute(
            "UPDATE users SET cooldown_bypass = ? WHERE user_id = ?", (int(enabled), user_id)
        )
        self._cooldown_bypass_cache[user_id] = enabled


    async def get_cooldown(self, user_id: int, action: str) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT expires_at FROM cooldowns WHERE user_id = ? AND action = ?", (user_id, action)
        )
        return _p(row[0]) if row else None

    async def set_cooldown(self, user_id: int, action: str, expires_at: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO cooldowns (user_id, action, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, action) DO UPDATE SET expires_at = excluded.expires_at",
            (user_id, action, _e(expires_at)),
        )

    async def try_consume_cooldown(
        self, user_id: int, action: str, period: datetime.timedelta, now: datetime.datetime
    ) -> bool:
        if await self.has_cooldown_bypass(user_id):
            return True
        new_expiry = _e(now + period)
        cur = await self._conn.execute(
            "INSERT INTO cooldowns (user_id, action, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, action) DO UPDATE SET "
            "expires_at = CASE WHEN cooldowns.expires_at <= ? THEN excluded.expires_at ELSE cooldowns.expires_at END "
            "RETURNING expires_at",
            (user_id, action, new_expiry, _e(now)),
        )
        row = await cur.fetchone()
        await cur.close()
        return row is not None and row[0] == new_expiry

    async def clear_cooldowns(self, user_id: int, actions: tuple[str, ...]) -> None:
        if not actions:
            return
        placeholders = ", ".join("?" * len(actions))
        await self._execute(
            f"DELETE FROM cooldowns WHERE user_id = ? AND action IN ({placeholders})",
            (user_id, *actions),
        )

    async def try_record_item_use(
        self, user_id: int, item_key: str, limit: int, window: datetime.timedelta, now: datetime.datetime
    ) -> bool:
        window_cutoff = _e(now - window)
        rowcount = await self._execute(
            "INSERT INTO item_use_limits (user_id, item_key, use_count, window_started_at) "
            "VALUES (?, ?, 1, ?) "
            "ON CONFLICT (user_id, item_key) DO UPDATE SET "
            "use_count = CASE WHEN item_use_limits.window_started_at <= ? THEN 1 "
            "ELSE item_use_limits.use_count + 1 END, "
            "window_started_at = CASE WHEN item_use_limits.window_started_at <= ? THEN excluded.window_started_at "
            "ELSE item_use_limits.window_started_at END "
            "WHERE item_use_limits.window_started_at <= ? OR item_use_limits.use_count < ?",
            (user_id, item_key, _e(now), window_cutoff, window_cutoff, window_cutoff, limit),
        )
        return rowcount > 0

    async def get_item_use_reset(
        self, user_id: int, item_key: str, window: datetime.timedelta
    ) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT window_started_at FROM item_use_limits WHERE user_id = ? AND item_key = ?",
            (user_id, item_key),
        )
        if not row:
            return None
        return _p(row[0]) + window

    async def get_random_user_id(self) -> int | None:
        row = await self._fetchone("SELECT user_id FROM users ORDER BY RANDOM() LIMIT 1")
        return row[0] if row else None

    async def get_payday_next(self) -> datetime.datetime | None:
        row = await self._fetchone("SELECT next_payday FROM payday_state WHERE id = 1")
        return _p(row[0]) if row else None

    async def set_payday_next(self, next_payday: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO payday_state (id, next_payday) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET next_payday = excluded.next_payday",
            (_e(next_payday),),
        )


    async def get_inventory(self, user_id: int) -> list[tuple[str, int]]:
        return await self._fetchall(
            "SELECT item_key, quantity FROM inventory WHERE user_id = ? AND quantity > 0", (user_id,)
        )

    async def execute_trade(
        self,
        give_user_id: int, give_asset: str, give_qty: int,
        want_user_id: int, want_asset: str, want_qty: int,
    ) -> None:
        async with self._transaction() as conn:
            await self._trade_deduct(conn, give_user_id, give_asset, give_qty)
            await self._trade_deduct(conn, want_user_id, want_asset, want_qty)
            await self._trade_credit(conn, want_user_id, give_asset, give_qty)
            await self._trade_credit(conn, give_user_id, want_asset, want_qty)

    async def _trade_deduct(self, conn, user_id: int, asset: str, quantity: int) -> None:
        if asset == "money":
            cur = await conn.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                (quantity, user_id, quantity),
            )
        else:
            cur = await conn.execute(
                "UPDATE inventory SET quantity = quantity - ? "
                "WHERE user_id = ? AND item_key = ? AND quantity >= ?",
                (quantity, user_id, asset, quantity),
            )
        if cur.rowcount == 0:
            exc = InsufficientFunds(f"User {user_id} cannot afford {quantity}x {asset}")
            exc.user_id = user_id
            raise exc

    async def _trade_credit(self, conn, user_id: int, asset: str, quantity: int) -> None:
        if asset == "money":
            await conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (quantity, user_id))
        else:
            await conn.execute(
                "INSERT INTO inventory (user_id, item_key, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT (user_id, item_key) DO UPDATE SET quantity = inventory.quantity + excluded.quantity",
                (user_id, asset, quantity),
            )

    async def get_item_quantity(self, user_id: int, item_key: str) -> int:
        row = await self._fetchone(
            "SELECT quantity FROM inventory WHERE user_id = ? AND item_key = ?", (user_id, item_key)
        )
        return row[0] if row else 0

    async def add_item(self, user_id: int, item_key: str, quantity: int) -> None:
        await self._execute(
            "INSERT INTO inventory (user_id, item_key, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, item_key) DO UPDATE SET quantity = inventory.quantity + excluded.quantity",
            (user_id, item_key, quantity),
        )

    async def remove_item(self, user_id: int, item_key: str, quantity: int) -> None:
        rowcount = await self._execute(
            "UPDATE inventory SET quantity = quantity - ? "
            "WHERE user_id = ? AND item_key = ? AND quantity >= ?",
            (quantity, user_id, item_key, quantity),
        )
        if rowcount == 0:
            raise InsufficientFunds(f"User {user_id} does not have {quantity}x {item_key}")


    async def record_game_result(self, user_id: int, wagered: int, payout: int) -> None:
        net = payout - wagered
        await self._execute(
            "INSERT INTO stats (user_id, games_played, total_wagered, total_won, biggest_win) "
            "VALUES (?, 1, ?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "games_played = stats.games_played + 1, "
            "total_wagered = stats.total_wagered + excluded.total_wagered, "
            "total_won = stats.total_won + excluded.total_won, "
            "biggest_win = MAX(stats.biggest_win, excluded.biggest_win)",
            (user_id, wagered, payout, max(net, 0)),
        )

    async def record_rob_attempt(self, user_id: int, success: bool) -> None:
        await self._execute(
            "INSERT INTO stats (user_id, robs_attempted, robs_succeeded) VALUES (?, 1, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "robs_attempted = stats.robs_attempted + 1, "
            "robs_succeeded = stats.robs_succeeded + excluded.robs_succeeded",
            (user_id, 1 if success else 0),
        )

    async def record_robbed(self, user_id: int) -> None:
        await self._execute(
            "INSERT INTO stats (user_id, times_robbed) VALUES (?, 1) "
            "ON CONFLICT (user_id) DO UPDATE SET times_robbed = stats.times_robbed + 1",
            (user_id,),
        )

    async def get_stats(self, user_id: int) -> dict:
        row = await self._fetchone(
            "SELECT games_played, total_wagered, total_won, biggest_win, "
            "robs_attempted, robs_succeeded, times_robbed FROM stats WHERE user_id = ?",
            (user_id,),
        )
        keys = (
            "games_played", "total_wagered", "total_won", "biggest_win",
            "robs_attempted", "robs_succeeded", "times_robbed",
        )
        return dict(zip(keys, row)) if row else dict.fromkeys(keys, 0)

    STAT_COLUMNS = {
        "games_played": "games_played",
        "total_wagered": "total_wagered",
        "biggest_win": "biggest_win",
        "robs_succeeded": "robs_succeeded",
    }

    async def top_stat(self, stat: str, limit: int = 10) -> list[tuple[int, int]]:
        column = self.STAT_COLUMNS[stat]
        return await self._fetchall(
            f"SELECT user_id, {column} FROM stats ORDER BY {column} DESC LIMIT ?", (limit,)
        )


    async def get_guild_settings(self) -> tuple[set[str], set[int]]:
        if self._guild_settings_cache is _UNSET:
            row = await self._fetchone(
                "SELECT disabled_games, allowed_channels FROM guild_settings WHERE id = 1"
            )
            if not row:
                self._guild_settings_cache = (set(), set())
            else:
                disabled = {g for g in row[0].split(",") if g}
                channels = {int(c) for c in row[1].split(",") if c}
                self._guild_settings_cache = (disabled, channels)
        disabled, channels = self._guild_settings_cache
        return set(disabled), set(channels)

    async def set_game_disabled(self, game: str, disabled: bool) -> None:
        current_disabled, current_allowed = await self.get_guild_settings()
        if disabled:
            current_disabled.add(game)
        else:
            current_disabled.discard(game)
        await self._execute(
            "INSERT INTO guild_settings (id, disabled_games) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET disabled_games = excluded.disabled_games",
            (",".join(sorted(current_disabled)),),
        )
        self._guild_settings_cache = (current_disabled, current_allowed)

    async def set_allowed_channels(self, channels: set[int]) -> None:
        current_disabled, _ = await self.get_guild_settings()
        await self._execute(
            "INSERT INTO guild_settings (id, allowed_channels) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET allowed_channels = excluded.allowed_channels",
            (",".join(str(c) for c in sorted(channels)),),
        )
        self._guild_settings_cache = (current_disabled, set(channels))

    async def get_gamble_channel(self) -> int | None:
        if self._gamble_channel_cache is _UNSET:
            row = await self._fetchone("SELECT channel_id FROM gamble_channels WHERE id = 1")
            self._gamble_channel_cache = row[0] if row else None
        return self._gamble_channel_cache

    async def set_gamble_channel(self, channel_id: int) -> None:
        await self._execute(
            "INSERT INTO gamble_channels (id, channel_id) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET channel_id = excluded.channel_id",
            (channel_id,),
        )
        self._gamble_channel_cache = channel_id

    async def clear_gamble_channel(self) -> None:
        await self._execute("DELETE FROM gamble_channels WHERE id = 1")
        self._gamble_channel_cache = None

    async def get_idle_tracker_message(self) -> tuple[int, datetime.datetime | None] | None:
        row = await self._fetchone("SELECT message_id, posted_at FROM idle_tracker_state WHERE id = 1")
        return (row[0], _p(row[1])) if row and row[0] else None

    async def set_idle_tracker_message(self, message_id: int, posted_at: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO idle_tracker_state (id, message_id, posted_at) VALUES (1, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET message_id = excluded.message_id, posted_at = excluded.posted_at",
            (message_id, _e(posted_at)),
        )

    async def save_idle_session(
        self,
        user_id: int, dungeon_key: str, display_name: str, deadline: datetime.datetime,
        channel_id: int, message_id: int, stats_json: str,
    ) -> None:
        await self._execute(
            "INSERT INTO idle_sessions "
            "(user_id, dungeon_key, display_name, deadline, channel_id, message_id, stats_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET deadline = excluded.deadline, stats_json = excluded.stats_json",
            (user_id, dungeon_key, display_name, _e(deadline), channel_id, message_id, stats_json),
        )

    async def get_all_idle_sessions(self) -> list[dict]:
        rows = await self._fetchall(
            "SELECT user_id, dungeon_key, display_name, deadline, channel_id, message_id, stats_json "
            "FROM idle_sessions"
        )
        return [
            {
                "user_id": r[0], "dungeon_key": r[1], "display_name": r[2], "deadline": _p(r[3]),
                "channel_id": r[4], "message_id": r[5], "stats_json": r[6],
            }
            for r in rows
        ]

    async def delete_idle_session(self, user_id: int) -> None:
        await self._execute("DELETE FROM idle_sessions WHERE user_id = ?", (user_id,))

    async def get_updates_channel(self) -> int | None:
        if self._updates_channel_cache is _UNSET:
            row = await self._fetchone("SELECT channel_id FROM updates_channels WHERE id = 1")
            self._updates_channel_cache = row[0] if row else None
        return self._updates_channel_cache

    async def set_updates_channel(self, channel_id: int) -> None:
        await self._execute(
            "INSERT INTO updates_channels (id, channel_id) VALUES (1, ?) "
            "ON CONFLICT (id) DO UPDATE SET channel_id = excluded.channel_id",
            (channel_id,),
        )
        self._updates_channel_cache = channel_id

    async def clear_updates_channel(self) -> None:
        await self._execute("DELETE FROM updates_channels WHERE id = 1")
        self._updates_channel_cache = None


    async def get_marriage(self, user_id: int) -> int | None:
        row = await self._fetchone("SELECT partner_id FROM marriages WHERE user_id = ?", (user_id,))
        return row[0] if row else None

    async def marry(self, user_id: int, partner_id: int) -> None:
        now = _e(datetime.datetime.utcnow())
        async with self._transaction() as conn:
            await conn.execute(
                "INSERT INTO marriages (user_id, partner_id, married_at) VALUES (?, ?, ?)",
                (user_id, partner_id, now),
            )
            await conn.execute(
                "INSERT INTO marriages (user_id, partner_id, married_at) VALUES (?, ?, ?)",
                (partner_id, user_id, now),
            )

    async def divorce(self, user_id: int) -> int | None:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            return None
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
        async with self._transaction() as conn:
            await conn.execute("DELETE FROM marriages WHERE user_id IN (?, ?)", (user_id, partner_id))
            cur = await conn.execute(
                "SELECT balance FROM marriage_bank WHERE user_id_a = ? AND user_id_b = ?", (a, b)
            )
            row = await cur.fetchone()
            if row and row[0] > 0:
                pot = row[0]
                half = pot // 2
                await conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (half, user_id))
                await conn.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id = ?", (pot - half, partner_id)
                )
            await conn.execute("DELETE FROM marriage_bank WHERE user_id_a = ? AND user_id_b = ?", (a, b))
        return partner_id

    async def get_marriage_bank(self, user_id: int) -> int | None:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            return None
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
        row = await self._fetchone(
            "SELECT balance FROM marriage_bank WHERE user_id_a = ? AND user_id_b = ?", (a, b)
        )
        return row[0] if row else 0

    async def deposit_marriage_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        async with self._transaction() as conn:
            cur = await conn.execute("SELECT partner_id FROM marriages WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            if row is None:
                raise InsufficientFunds(f"User {user_id} is not married")
            partner_id = row[0]
            a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)

            cur = await conn.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                (amount, user_id, amount),
            )
            if cur.rowcount == 0:
                raise InsufficientFunds(f"User {user_id} cannot deposit {amount}")
            await conn.execute(
                "INSERT INTO marriage_bank (user_id_a, user_id_b, balance) VALUES (?, ?, ?) "
                "ON CONFLICT (user_id_a, user_id_b) DO UPDATE SET balance = marriage_bank.balance + excluded.balance",
                (a, b, amount),
            )
            cur = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            wallet = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT balance FROM marriage_bank WHERE user_id_a = ? AND user_id_b = ?", (a, b)
            )
            bank = (await cur.fetchone())[0]
            return wallet, bank

    async def withdraw_marriage_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            raise InsufficientFunds(f"User {user_id} is not married")
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
        async with self._transaction() as conn:
            cur = await conn.execute(
                "UPDATE marriage_bank SET balance = balance - ? "
                "WHERE user_id_a = ? AND user_id_b = ? AND balance >= ?",
                (amount, a, b, amount),
            )
            if cur.rowcount == 0:
                raise InsufficientFunds(f"Marriage bank for {user_id} cannot afford {amount}")
            await conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            cur = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            wallet = (await cur.fetchone())[0]
            cur = await conn.execute(
                "SELECT balance FROM marriage_bank WHERE user_id_a = ? AND user_id_b = ?", (a, b)
            )
            bank = (await cur.fetchone())[0]
            return wallet, bank


    async def get_lottery_state(self) -> dict:
        row = await self._fetchone("SELECT pot, next_draw, channel_id FROM lottery_state WHERE id = 1")
        return {"pot": row[0], "next_draw": _p(row[1]), "channel_id": row[2]}

    async def set_lottery_channel(self, channel_id: int) -> None:
        await self._execute("UPDATE lottery_state SET channel_id = ? WHERE id = 1", (channel_id,))

    async def get_lottery_tickets(self, user_id: int) -> int:
        row = await self._fetchone("SELECT quantity FROM lottery_tickets WHERE user_id = ?", (user_id,))
        return row[0] if row else 0

    async def buy_lottery_tickets(self, user_id: int, quantity: int, cost: int) -> None:
        async with self._transaction() as conn:
            cur = await conn.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                (cost, user_id, cost),
            )
            if cur.rowcount == 0:
                raise InsufficientFunds(f"User {user_id} cannot afford {cost}")
            await conn.execute(
                "INSERT INTO lottery_tickets (user_id, quantity) VALUES (?, ?) "
                "ON CONFLICT (user_id) DO UPDATE SET quantity = lottery_tickets.quantity + excluded.quantity",
                (user_id, quantity),
            )
            await conn.execute("UPDATE lottery_state SET pot = pot + ? WHERE id = 1", (cost,))

    async def all_lottery_tickets(self) -> list[tuple[int, int]]:
        return await self._fetchall("SELECT user_id, quantity FROM lottery_tickets WHERE quantity > 0")

    async def reset_lottery(self, next_draw: datetime.datetime) -> None:
        async with self._transaction() as conn:
            await conn.execute("DELETE FROM lottery_tickets")
            await conn.execute("UPDATE lottery_state SET pot = 0, next_draw = ? WHERE id = 1", (_e(next_draw),))


    async def create_character(self, user_id: int, class_key: str, starting_hp: int) -> None:
        now = _e(datetime.datetime.utcnow())
        await self._execute(
            "INSERT INTO characters (user_id, class_key, current_hp, hp_updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (user_id) DO NOTHING",
            (user_id, class_key, starting_hp, now),
        )

    async def get_character(self, user_id: int) -> dict | None:
        row = await self._fetchone(
            "SELECT c.class_key, c.level, c.xp, c.equipped_weapon, c.equipped_armor, c.equipped_accessory, "
            "c.equipped_shield, "
            "c.wins, c.losses, c.current_hp, c.hp_updated_at, "
            "c.weapon_enchant, c.armor_enchant, c.accessory_enchant, c.shield_enchant, "
            "c.equipped_primordial_weapon_id, c.equipped_primordial_armor_id, c.equipped_primordial_accessory_id, "
            "pw.affixes, pa.affixes, pacc.affixes "
            "FROM characters c "
            "LEFT JOIN primordial_items pw ON pw.id = c.equipped_primordial_weapon_id "
            "LEFT JOIN primordial_items pa ON pa.id = c.equipped_primordial_armor_id "
            "LEFT JOIN primordial_items pacc ON pacc.id = c.equipped_primordial_accessory_id "
            "WHERE c.user_id = ?",
            (user_id,),
        )
        if not row:
            return None
        keys = (
            "class_key", "level", "xp", "equipped_weapon", "equipped_armor", "equipped_accessory",
            "equipped_shield",
            "wins", "losses", "current_hp", "hp_updated_at",
            "weapon_enchant", "armor_enchant", "accessory_enchant", "shield_enchant",
            "equipped_primordial_weapon_id", "equipped_primordial_armor_id", "equipped_primordial_accessory_id",
        )
        character = dict(zip(keys, row[:18]))
        character["hp_updated_at"] = _p(character["hp_updated_at"])
        weapon_affixes, armor_affixes, accessory_affixes = row[18], row[19], row[20]
        character["primordial_weapon"] = {"affixes": json.loads(weapon_affixes)} if weapon_affixes else None
        character["primordial_armor"] = {"affixes": json.loads(armor_affixes)} if armor_affixes else None
        character["primordial_accessory"] = {"affixes": json.loads(accessory_affixes)} if accessory_affixes else None
        return character

    _CHARACTER_SWAP_COLUMNS = (
        "class_key", "level", "xp", "equipped_weapon", "equipped_armor", "equipped_accessory", "equipped_shield",
        "wins", "losses", "current_hp", "hp_updated_at",
        "weapon_enchant", "armor_enchant", "accessory_enchant", "shield_enchant",
        "equipped_primordial_weapon_id", "equipped_primordial_armor_id", "equipped_primordial_accessory_id",
    )

    async def get_character_backup(self, user_id: int) -> dict | None:
        cols = self._CHARACTER_SWAP_COLUMNS
        row = await self._fetchone(
            f"SELECT {', '.join(cols)} FROM character_backup WHERE user_id = ?", (user_id,)
        )
        if not row:
            return None
        return dict(zip(cols, row))

    async def swap_character_slot(self, user_id: int, new_class_key: str, starting_hp: int) -> None:
        cols = self._CHARACTER_SWAP_COLUMNS
        now = _e(datetime.datetime.utcnow())
        async with self._transaction() as conn:
            cur = await conn.execute(
                f"SELECT {', '.join(cols)} FROM characters WHERE user_id = ?", (user_id,)
            )
            current = await cur.fetchone()
            if not current:
                raise ValueError(f"User {user_id} has no active character")

            cur = await conn.execute(
                f"SELECT {', '.join(cols)} FROM character_backup WHERE user_id = ?", (user_id,)
            )
            backup = await cur.fetchone()

            col_list = ", ".join(cols)
            placeholders = ", ".join(["?"] * len(cols))
            update_list = ", ".join(f"{c} = excluded.{c}" for c in cols)
            await conn.execute(
                f"INSERT INTO character_backup (user_id, {col_list}) VALUES (?, {placeholders}) "
                f"ON CONFLICT (user_id) DO UPDATE SET {update_list}",
                (user_id, *current),
            )

            if backup and backup[0] == new_class_key:
                set_clause = ", ".join(f"{c} = ?" for c in cols)
                await conn.execute(
                    f"UPDATE characters SET {set_clause} WHERE user_id = ?", (*backup, user_id)
                )
            else:
                await conn.execute(
                    "UPDATE characters SET class_key = ?, level = 1, xp = 0, "
                    "equipped_weapon = NULL, equipped_armor = NULL, equipped_accessory = NULL, "
                    "equipped_shield = NULL, "
                    "wins = 0, losses = 0, current_hp = ?, hp_updated_at = ?, "
                    "weapon_enchant = 0, armor_enchant = 0, accessory_enchant = 0, shield_enchant = 0, "
                    "equipped_primordial_weapon_id = NULL, equipped_primordial_armor_id = NULL, "
                    "equipped_primordial_accessory_id = NULL "
                    "WHERE user_id = ?",
                    (new_class_key, starting_hp, now, user_id),
                )

    async def set_character_level(self, user_id: int, level: int, xp: int) -> None:
        await self._execute(
            "UPDATE characters SET level = ?, xp = ? WHERE user_id = ?", (level, xp, user_id)
        )

    async def set_character_hp(self, user_id: int, hp: int, when: datetime.datetime) -> None:
        await self._execute(
            "UPDATE characters SET current_hp = ?, hp_updated_at = ? WHERE user_id = ?",
            (hp, _e(when), user_id),
        )

    _EQUIP_COLUMNS = {
        "weapon": "equipped_weapon",
        "armor": "equipped_armor",
        "accessory": "equipped_accessory",
        "shield": "equipped_shield",
    }

    async def set_equipped(self, user_id: int, slot: str, item_key: str) -> None:
        column = self._EQUIP_COLUMNS[slot]
        await self._execute(f"UPDATE characters SET {column} = ? WHERE user_id = ?", (item_key, user_id))

    _ENCHANT_COLUMNS = {
        "weapon": "weapon_enchant",
        "armor": "armor_enchant",
        "accessory": "accessory_enchant",
        "shield": "shield_enchant",
    }

    async def set_enchant_level(self, user_id: int, slot: str, level: int) -> None:
        column = self._ENCHANT_COLUMNS[slot]
        await self._execute(f"UPDATE characters SET {column} = ? WHERE user_id = ?", (level, user_id))

    async def upgrade_enchant(self, user_id: int, slot: str, cost: int, new_level: int) -> int:
        column = self._ENCHANT_COLUMNS[slot]
        async with self._transaction() as conn:
            cur = await conn.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                (cost, user_id, cost),
            )
            if cur.rowcount == 0:
                raise InsufficientFunds(f"User {user_id} cannot afford an upgrade costing {cost}")
            await conn.execute(f"UPDATE characters SET {column} = ? WHERE user_id = ?", (new_level, user_id))
            cur = await conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            return row[0]

    _PRIMORDIAL_EQUIP_COLUMNS = {
        "weapon": "equipped_primordial_weapon_id",
        "armor": "equipped_primordial_armor_id",
        "accessory": "equipped_primordial_accessory_id",
    }

    async def add_primordial_item(self, user_id: int, slot: str, affixes_json: str) -> int:
        cur = await self._conn.execute(
            "INSERT INTO primordial_items (user_id, slot, affixes) VALUES (?, ?, ?)",
            (user_id, slot, affixes_json),
        )
        await cur.close()
        return cur.lastrowid

    async def get_primordial_items(self, user_id: int) -> list[dict]:
        rows = await self._fetchall(
            "SELECT id, slot, affixes FROM primordial_items WHERE user_id = ? ORDER BY id", (user_id,)
        )
        return [{"id": r[0], "slot": r[1], "affixes": json.loads(r[2])} for r in rows]

    async def equip_primordial(self, user_id: int, slot: str, item_id: int) -> None:
        column = self._PRIMORDIAL_EQUIP_COLUMNS[slot]
        await self._execute(f"UPDATE characters SET {column} = ? WHERE user_id = ?", (item_id, user_id))

    async def unequip_primordial(self, user_id: int, slot: str) -> None:
        column = self._PRIMORDIAL_EQUIP_COLUMNS[slot]
        await self._execute(f"UPDATE characters SET {column} = NULL WHERE user_id = ?", (user_id,))

    async def get_boss_kills(self, user_id: int, dungeon_key: str) -> int:
        row = await self._fetchone(
            "SELECT kills FROM boss_kills WHERE user_id = ? AND dungeon_key = ?", (user_id, dungeon_key)
        )
        return row[0] if row else 0

    async def record_boss_kill(self, user_id: int, dungeon_key: str) -> None:
        await self._execute(
            "INSERT INTO boss_kills (user_id, dungeon_key, kills) VALUES (?, ?, 1) "
            "ON CONFLICT (user_id, dungeon_key) DO UPDATE SET kills = boss_kills.kills + 1",
            (user_id, dungeon_key),
        )

    async def total_boss_kills(self, user_id: int) -> int:
        row = await self._fetchone(
            "SELECT COALESCE(SUM(kills), 0) FROM boss_kills WHERE user_id = ?", (user_id,)
        )
        return row[0] if row else 0

    async def record_duel_result(self, winner_id: int, loser_id: int) -> None:
        await self._execute("UPDATE characters SET wins = wins + 1 WHERE user_id = ?", (winner_id,))
        await self._execute("UPDATE characters SET losses = losses + 1 WHERE user_id = ?", (loser_id,))

    async def top_arena(self, limit: int = 10) -> list[tuple[int, int, int]]:
        return await self._fetchall(
            "SELECT user_id, wins, losses FROM characters ORDER BY wins DESC LIMIT ?", (limit,)
        )

    async def get_rpg_inventory(self, user_id: int) -> list[tuple[str, int]]:
        return await self._fetchall(
            "SELECT item_key, quantity FROM rpg_equipment WHERE user_id = ? AND quantity > 0", (user_id,)
        )

    async def get_rpg_item_quantity(self, user_id: int, item_key: str) -> int:
        row = await self._fetchone(
            "SELECT quantity FROM rpg_equipment WHERE user_id = ? AND item_key = ?", (user_id, item_key)
        )
        return row[0] if row else 0

    async def add_rpg_item(self, user_id: int, item_key: str, quantity: int) -> None:
        await self._execute(
            "INSERT INTO rpg_equipment (user_id, item_key, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT (user_id, item_key) DO UPDATE SET quantity = rpg_equipment.quantity + excluded.quantity",
            (user_id, item_key, quantity),
        )

    async def remove_rpg_item(self, user_id: int, item_key: str, quantity: int) -> None:
        rowcount = await self._execute(
            "UPDATE rpg_equipment SET quantity = quantity - ? "
            "WHERE user_id = ? AND item_key = ? AND quantity >= ?",
            (quantity, user_id, item_key, quantity),
        )
        if rowcount == 0:
            raise InsufficientFunds(f"User {user_id} does not have {quantity}x {item_key}")


    async def reset_user(self, user_id: int, starting_balance: int) -> None:
        async with self._transaction() as conn:
            await conn.execute(
                "UPDATE users SET balance = ?, bank_balance = 0, last_daily = NULL, "
                "daily_streak = 0, protected_until = NULL, cooldown_bypass = 0 "
                "WHERE user_id = ?",
                (starting_balance, user_id),
            )
            await conn.execute("DELETE FROM inventory WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM stats WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM lottery_tickets WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM cooldowns WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM rpg_equipment WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM boss_kills WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM primordial_items WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM item_use_limits WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM achievements WHERE user_id = ?", (user_id,))
            await conn.execute("DELETE FROM vote_claims WHERE user_id = ?", (user_id,))
        self._cooldown_bypass_cache[user_id] = False
        await self.divorce(user_id)


    async def get_level_xp(self, user_id: int) -> int:
        row = await self._fetchone("SELECT xp FROM level_xp WHERE user_id = ?", (user_id,))
        return row[0] if row else 0

    async def get_level_last_xp_at(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone("SELECT last_xp_at FROM level_xp WHERE user_id = ?", (user_id,))
        return _p(row[0]) if row and row[0] else None

    async def add_level_xp(self, user_id: int, amount: int, now: datetime.datetime) -> int:
        await self._execute(
            "INSERT INTO level_xp (user_id, xp, message_xp, last_xp_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "xp = level_xp.xp + excluded.xp, message_xp = level_xp.message_xp + excluded.message_xp, "
            "last_xp_at = excluded.last_xp_at",
            (user_id, amount, amount, _e(now)),
        )
        row = await self._fetchone("SELECT xp FROM level_xp WHERE user_id = ?", (user_id,))
        return row[0]

    async def add_level_admin_xp(self, user_id: int, amount: int) -> int:
        await self._execute(
            "INSERT INTO level_xp (user_id, xp) VALUES (?, MAX(?, 0)) "
            "ON CONFLICT (user_id) DO UPDATE SET xp = MAX(level_xp.xp + ?, 0)",
            (user_id, amount, amount),
        )
        row = await self._fetchone("SELECT xp FROM level_xp WHERE user_id = ?", (user_id,))
        return row[0]

    async def add_level_voice(self, user_id: int, amount: int, seconds: int) -> int:
        await self._execute(
            "INSERT INTO level_xp (user_id, xp, voice_xp, vc_seconds) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "xp = level_xp.xp + excluded.xp, voice_xp = level_xp.voice_xp + excluded.voice_xp, "
            "vc_seconds = level_xp.vc_seconds + excluded.vc_seconds",
            (user_id, amount, amount, seconds),
        )
        row = await self._fetchone("SELECT xp FROM level_xp WHERE user_id = ?", (user_id,))
        return row[0]

    async def get_level_stats(self, user_id: int) -> dict:
        row = await self._fetchone(
            "SELECT xp, message_xp, voice_xp, vc_seconds FROM level_xp WHERE user_id = ?", (user_id,)
        )
        if not row:
            return {"xp": 0, "message_xp": 0, "voice_xp": 0, "vc_seconds": 0}
        return {"xp": row[0], "message_xp": row[1], "voice_xp": row[2], "vc_seconds": row[3]}

    async def get_level_leaderboard(self, limit: int = 10) -> list[tuple[int, int]]:
        rows = await self._fetchall(
            "SELECT user_id, xp FROM level_xp ORDER BY xp DESC LIMIT ?", (limit,)
        )
        return [(r[0], r[1]) for r in rows]

    async def set_level_boost(self, multiplier: float, expires_at: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO level_boost (id, multiplier, expires_at) VALUES (1, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET multiplier = excluded.multiplier, expires_at = excluded.expires_at",
            (multiplier, _e(expires_at)),
        )
        self._level_boost_cache = (multiplier, expires_at)

    async def get_level_boost(self) -> tuple[float, datetime.datetime] | None:
        if self._level_boost_cache is _UNSET:
            row = await self._fetchone("SELECT multiplier, expires_at FROM level_boost WHERE id = 1")
            self._level_boost_cache = (row[0], _p(row[1])) if row else None
        return self._level_boost_cache

    async def clear_level_boost(self) -> bool:
        rowcount = await self._execute("DELETE FROM level_boost WHERE id = 1")
        self._level_boost_cache = None
        return rowcount > 0
