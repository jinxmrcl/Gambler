import asyncio
import datetime
import json
import logging

import asyncpg

from .db import InsufficientFunds

log = logging.getLogger("gambler")


def _rowcount(status: str) -> int:
    parts = status.split()
    return int(parts[-1]) if parts and parts[-1].lstrip("-").isdigit() else 0


class PostgresDatabase:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self, *, retries: int = 3, retry_delay: float = 3.0) -> None:
        for attempt in range(1, retries + 1):
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=self._dsn,
                    min_size=1,
                    max_size=10,
                    command_timeout=10,
                    statement_cache_size=0,
                )
                break
            except Exception:
                if attempt == retries:
                    log.exception(
                        "Could not connect to the Supabase/Postgres fallback after %d attempts.",
                        retries,
                    )
                    raise
                log.warning(
                    "Supabase/Postgres connection attempt %d/%d failed, retrying in %.0fs...",
                    attempt,
                    retries,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
        await self._init_tables()

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    async def _execute(self, query: str, *args) -> int:
        async with self.pool.acquire() as conn:
            status = await conn.execute(query, *args)
            return _rowcount(status)

    async def _fetchone(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def _fetchall(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def _init_tables(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    balance BIGINT NOT NULL DEFAULT 0,
                    bank_balance BIGINT NOT NULL DEFAULT 0,
                    last_daily TIMESTAMP NULL,
                    daily_streak INTEGER NOT NULL DEFAULT 0,
                    protected_until TIMESTAMP NULL,
                    cooldown_bypass BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_streak INTEGER NOT NULL DEFAULT 0")
            await conn.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS cooldown_bypass BOOLEAN NOT NULL DEFAULT FALSE"
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory (
                    user_id BIGINT NOT NULL,
                    item_key VARCHAR(32) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, item_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stats (
                    user_id BIGINT PRIMARY KEY,
                    games_played INTEGER NOT NULL DEFAULT 0,
                    total_wagered BIGINT NOT NULL DEFAULT 0,
                    total_won BIGINT NOT NULL DEFAULT 0,
                    biggest_win BIGINT NOT NULL DEFAULT 0,
                    robs_attempted INTEGER NOT NULL DEFAULT 0,
                    robs_succeeded INTEGER NOT NULL DEFAULT 0,
                    times_robbed INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id BIGINT PRIMARY KEY,
                    disabled_games VARCHAR(255) NOT NULL DEFAULT '',
                    allowed_channels VARCHAR(255) NOT NULL DEFAULT ''
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gamble_channels (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS updates_channels (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS marriages (
                    user_id BIGINT PRIMARY KEY,
                    partner_id BIGINT NOT NULL,
                    married_at TIMESTAMP NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS marriage_bank (
                    user_id_a BIGINT NOT NULL,
                    user_id_b BIGINT NOT NULL,
                    balance BIGINT NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id_a, user_id_b)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lottery_tickets (
                    user_id BIGINT PRIMARY KEY,
                    quantity INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lottery_state (
                    id SMALLINT PRIMARY KEY,
                    pot BIGINT NOT NULL DEFAULT 0,
                    next_draw TIMESTAMP NOT NULL,
                    channel_id BIGINT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idle_tracker_state (
                    id SMALLINT PRIMARY KEY,
                    message_id BIGINT NULL,
                    posted_at TIMESTAMP NULL
                )
                """
            )
            await conn.execute("ALTER TABLE idle_tracker_state ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP NULL")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payday_state (
                    id SMALLINT PRIMARY KEY,
                    next_payday TIMESTAMP NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idle_sessions (
                    user_id BIGINT PRIMARY KEY,
                    dungeon_key VARCHAR(32) NOT NULL,
                    display_name VARCHAR(128) NOT NULL,
                    deadline TIMESTAMP NOT NULL,
                    channel_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    stats_json TEXT NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS level_xp (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    xp BIGINT NOT NULL DEFAULT 0,
                    message_xp BIGINT NOT NULL DEFAULT 0,
                    voice_xp BIGINT NOT NULL DEFAULT 0,
                    vc_seconds BIGINT NOT NULL DEFAULT 0,
                    last_xp_at TIMESTAMP NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS level_boost (
                    guild_id BIGINT PRIMARY KEY,
                    multiplier REAL NOT NULL,
                    expires_at TIMESTAMP NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cooldowns (
                    user_id BIGINT NOT NULL,
                    action VARCHAR(32) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, action)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS item_use_limits (
                    user_id BIGINT NOT NULL,
                    item_key VARCHAR(32) NOT NULL,
                    use_count INTEGER NOT NULL DEFAULT 0,
                    window_started_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, item_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS achievements (
                    user_id BIGINT NOT NULL,
                    achievement_key VARCHAR(64) NOT NULL,
                    unlocked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, achievement_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS characters (
                    user_id BIGINT PRIMARY KEY,
                    class_key VARCHAR(16) NOT NULL,
                    level INTEGER NOT NULL DEFAULT 1,
                    xp INTEGER NOT NULL DEFAULT 0,
                    equipped_weapon VARCHAR(32) NULL,
                    equipped_armor VARCHAR(32) NULL,
                    equipped_accessory VARCHAR(32) NULL,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    current_hp INTEGER NULL,
                    hp_updated_at TIMESTAMP NULL,
                    weapon_enchant INTEGER NOT NULL DEFAULT 0,
                    armor_enchant INTEGER NOT NULL DEFAULT 0,
                    accessory_enchant INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.execute("ALTER TABLE characters ADD COLUMN IF NOT EXISTS equipped_primordial_weapon_id INTEGER NULL")
            await conn.execute("ALTER TABLE characters ADD COLUMN IF NOT EXISTS equipped_primordial_armor_id INTEGER NULL")
            await conn.execute("ALTER TABLE characters ADD COLUMN IF NOT EXISTS equipped_primordial_accessory_id INTEGER NULL")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rpg_equipment (
                    user_id BIGINT NOT NULL,
                    item_key VARCHAR(32) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, item_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS boss_kills (
                    user_id BIGINT NOT NULL,
                    dungeon_key VARCHAR(32) NOT NULL,
                    kills INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, dungeon_key)
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS primordial_items (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    slot VARCHAR(16) NOT NULL,
                    affixes TEXT NOT NULL,
                    dropped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS character_backup (
                    user_id BIGINT PRIMARY KEY,
                    class_key VARCHAR(16) NOT NULL,
                    level INTEGER NOT NULL DEFAULT 1,
                    xp INTEGER NOT NULL DEFAULT 0,
                    equipped_weapon VARCHAR(32) NULL,
                    equipped_armor VARCHAR(32) NULL,
                    equipped_accessory VARCHAR(32) NULL,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    current_hp INTEGER NULL,
                    hp_updated_at TIMESTAMP NULL,
                    weapon_enchant INTEGER NOT NULL DEFAULT 0,
                    armor_enchant INTEGER NOT NULL DEFAULT 0,
                    accessory_enchant INTEGER NOT NULL DEFAULT 0,
                    equipped_primordial_weapon_id INTEGER NULL,
                    equipped_primordial_armor_id INTEGER NULL,
                    equipped_primordial_accessory_id INTEGER NULL
                )
                """
            )
            await conn.execute(
                "INSERT INTO lottery_state (id, pot, next_draw) VALUES (1, 0, $1) "
                "ON CONFLICT (id) DO NOTHING",
                datetime.datetime.utcnow() + datetime.timedelta(days=7),
            )


    async def ensure_user(self, user_id: int, starting_balance: int) -> None:
        await self._execute(
            "INSERT INTO users (user_id, balance) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO NOTHING",
            user_id,
            starting_balance,
        )

    async def get_balance(self, user_id: int) -> int:
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = $1", user_id)
        return row[0] if row else 0

    async def update_balance(self, user_id: int, delta: int) -> int:
        rowcount = await self._execute(
            "UPDATE users SET balance = balance + $1 WHERE user_id = $2 AND balance + $1 >= 0",
            delta,
            user_id,
        )
        if rowcount == 0:
            raise InsufficientFunds(f"User {user_id} cannot afford a change of {delta}")
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = $1", user_id)
        return row[0]

    async def debit_both(self, user_a_id: int, user_b_id: int, amount: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for user_id in (user_a_id, user_b_id):
                    status = await conn.execute(
                        "UPDATE users SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1",
                        amount,
                        user_id,
                    )
                    if _rowcount(status) == 0:
                        exc = InsufficientFunds(f"User {user_id} cannot afford {amount}")
                        exc.user_id = user_id
                        raise exc

    async def transfer_balance(self, sender_id: int, recipient_id: int, amount: int) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                status = await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1",
                    amount,
                    sender_id,
                )
                if _rowcount(status) == 0:
                    raise InsufficientFunds(f"User {sender_id} cannot afford a transfer of {amount}")
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, recipient_id
                )
                row = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", sender_id)
                return row[0]

    async def set_balance(self, user_id: int, amount: int) -> None:
        await self._execute("UPDATE users SET balance = $1 WHERE user_id = $2", amount, user_id)

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
        """Returns (new_balance, payout, streak) or None if not yet eligible."""
        cutoff = now - period
        row = await self._fetchone("SELECT last_daily, daily_streak FROM users WHERE user_id = $1", user_id)
        last_daily, streak = (row[0], row[1]) if row else (None, 0)
        continues = last_daily is not None and (now - last_daily) <= period * 2
        new_streak = streak + 1 if continues else 1
        multiplier = 1 + bonus_per_day * min(new_streak - 1, max_bonus_days)
        payout = int(base_amount * multiplier)

        rowcount = await self._execute(
            "UPDATE users SET balance = balance + $1, last_daily = $2, daily_streak = $3 "
            "WHERE user_id = $4 AND (last_daily IS NULL OR last_daily <= $5)",
            payout,
            now,
            new_streak,
            user_id,
            cutoff,
        )
        if rowcount == 0:
            return None
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = $1", user_id)
        return row[0], payout, new_streak

    async def get_last_daily(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone("SELECT last_daily FROM users WHERE user_id = $1", user_id)
        return row[0] if row else None

    async def get_daily_streak(self, user_id: int) -> int:
        row = await self._fetchone("SELECT daily_streak FROM users WHERE user_id = $1", user_id)
        return row[0] if row else 0

    async def get_unlocked_achievements(self, user_id: int) -> set[str]:
        rows = await self._fetchall(
            "SELECT achievement_key FROM achievements WHERE user_id = $1", user_id
        )
        return {row[0] for row in rows}

    async def unlock_achievement(self, user_id: int, key: str, now: datetime.datetime) -> bool:
        rowcount = await self._execute(
            "INSERT INTO achievements (user_id, achievement_key, unlocked_at) VALUES ($1, $2, $3) "
            "ON CONFLICT (user_id, achievement_key) DO NOTHING",
            user_id,
            key,
            now,
        )
        return rowcount > 0

    async def top_balances(self, limit: int = 10) -> list[tuple[int, int]]:
        rows = await self._fetchall(
            "SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT $1", limit
        )
        return [(r[0], r[1]) for r in rows]

    async def give_all_users(self, amount: int) -> int:
        return await self._execute("UPDATE users SET balance = GREATEST(balance + $1, 0)", amount)

    async def get_bank_balance(self, user_id: int) -> int:
        row = await self._fetchone("SELECT bank_balance FROM users WHERE user_id = $1", user_id)
        return row[0] if row else 0

    async def deposit_to_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                status = await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1",
                    amount,
                    user_id,
                )
                if _rowcount(status) == 0:
                    raise InsufficientFunds(f"User {user_id} cannot deposit {amount}")
                await conn.execute(
                    "UPDATE users SET bank_balance = bank_balance + $1 WHERE user_id = $2",
                    amount,
                    user_id,
                )
                row = await conn.fetchrow(
                    "SELECT balance, bank_balance FROM users WHERE user_id = $1", user_id
                )
                return row[0], row[1]

    async def withdraw_from_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                status = await conn.execute(
                    "UPDATE users SET bank_balance = bank_balance - $1 "
                    "WHERE user_id = $2 AND bank_balance >= $1",
                    amount,
                    user_id,
                )
                if _rowcount(status) == 0:
                    raise InsufficientFunds(f"User {user_id} cannot withdraw {amount}")
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, user_id
                )
                row = await conn.fetchrow(
                    "SELECT balance, bank_balance FROM users WHERE user_id = $1", user_id
                )
                return row[0], row[1]

    async def get_protected_until(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone("SELECT protected_until FROM users WHERE user_id = $1", user_id)
        return row[0] if row else None

    async def set_protected_until(self, user_id: int, when: datetime.datetime | None) -> None:
        await self._execute("UPDATE users SET protected_until = $1 WHERE user_id = $2", when, user_id)

    async def has_cooldown_bypass(self, user_id: int) -> bool:
        row = await self._fetchone("SELECT cooldown_bypass FROM users WHERE user_id = $1", user_id)
        return bool(row[0]) if row else False

    async def set_cooldown_bypass(self, user_id: int, enabled: bool) -> None:
        await self._execute("UPDATE users SET cooldown_bypass = $1 WHERE user_id = $2", enabled, user_id)


    async def get_cooldown(self, user_id: int, action: str) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT expires_at FROM cooldowns WHERE user_id = $1 AND action = $2", user_id, action
        )
        return row[0] if row else None

    async def set_cooldown(self, user_id: int, action: str, expires_at: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO cooldowns (user_id, action, expires_at) VALUES ($1, $2, $3) "
            "ON CONFLICT (user_id, action) DO UPDATE SET expires_at = EXCLUDED.expires_at",
            user_id,
            action,
            expires_at,
        )

    async def try_consume_cooldown(
        self, user_id: int, action: str, period: datetime.timedelta, now: datetime.datetime
    ) -> bool:
        if await self.has_cooldown_bypass(user_id):
            return True
        new_expiry = now + period
        row = await self._fetchone(
            "INSERT INTO cooldowns (user_id, action, expires_at) VALUES ($1, $2, $3) "
            "ON CONFLICT (user_id, action) DO UPDATE SET "
            "expires_at = CASE WHEN cooldowns.expires_at <= $4 THEN $3 ELSE cooldowns.expires_at END "
            "RETURNING expires_at",
            user_id,
            action,
            new_expiry,
            now,
        )
        return row is not None and row[0] == new_expiry

    async def clear_cooldowns(self, user_id: int, actions: tuple[str, ...]) -> None:
        if not actions:
            return
        await self._execute(
            "DELETE FROM cooldowns WHERE user_id = $1 AND action = ANY($2::text[])",
            user_id,
            list(actions),
        )

    async def try_record_item_use(
        self, user_id: int, item_key: str, limit: int, window: datetime.timedelta, now: datetime.datetime
    ) -> bool:
        window_cutoff = now - window
        status = await self._execute(
            "INSERT INTO item_use_limits (user_id, item_key, use_count, window_started_at) "
            "VALUES ($1, $2, 1, $3) "
            "ON CONFLICT (user_id, item_key) DO UPDATE SET "
            "use_count = CASE "
            "  WHEN item_use_limits.window_started_at <= $4 THEN 1 "
            "  ELSE item_use_limits.use_count + 1 "
            "END, "
            "window_started_at = CASE "
            "  WHEN item_use_limits.window_started_at <= $4 THEN $3 "
            "  ELSE item_use_limits.window_started_at "
            "END "
            "WHERE item_use_limits.window_started_at <= $4 OR item_use_limits.use_count < $5",
            user_id,
            item_key,
            now,
            window_cutoff,
            limit,
        )
        return status > 0

    async def get_item_use_reset(
        self, user_id: int, item_key: str, window: datetime.timedelta
    ) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT window_started_at FROM item_use_limits WHERE user_id = $1 AND item_key = $2",
            user_id,
            item_key,
        )
        if not row:
            return None
        return row[0] + window

    async def get_random_user_id(self) -> int | None:
        row = await self._fetchone("SELECT user_id FROM users ORDER BY RANDOM() LIMIT 1")
        return row[0] if row else None

    async def get_payday_next(self) -> datetime.datetime | None:
        row = await self._fetchone("SELECT next_payday FROM payday_state WHERE id = 1")
        return row[0] if row else None

    async def set_payday_next(self, next_payday: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO payday_state (id, next_payday) VALUES (1, $1) "
            "ON CONFLICT (id) DO UPDATE SET next_payday = $1",
            next_payday,
        )


    async def get_inventory(self, user_id: int) -> list[tuple[str, int]]:
        rows = await self._fetchall(
            "SELECT item_key, quantity FROM inventory WHERE user_id = $1 AND quantity > 0", user_id
        )
        return [(r[0], r[1]) for r in rows]

    async def execute_trade(
        self,
        give_user_id: int, give_asset: str, give_qty: int,
        want_user_id: int, want_asset: str, want_qty: int,
    ) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._trade_deduct(conn, give_user_id, give_asset, give_qty)
                await self._trade_deduct(conn, want_user_id, want_asset, want_qty)
                await self._trade_credit(conn, want_user_id, give_asset, give_qty)
                await self._trade_credit(conn, give_user_id, want_asset, want_qty)

    async def _trade_deduct(self, conn, user_id: int, asset: str, quantity: int) -> None:
        if asset == "money":
            status = await conn.execute(
                "UPDATE users SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1",
                quantity,
                user_id,
            )
        else:
            status = await conn.execute(
                "UPDATE inventory SET quantity = quantity - $1 "
                "WHERE user_id = $2 AND item_key = $3 AND quantity >= $1",
                quantity,
                user_id,
                asset,
            )
        if _rowcount(status) == 0:
            exc = InsufficientFunds(f"User {user_id} cannot afford {quantity}x {asset}")
            exc.user_id = user_id
            raise exc

    async def _trade_credit(self, conn, user_id: int, asset: str, quantity: int) -> None:
        if asset == "money":
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", quantity, user_id)
        else:
            await conn.execute(
                "INSERT INTO inventory (user_id, item_key, quantity) VALUES ($1, $2, $3) "
                "ON CONFLICT (user_id, item_key) DO UPDATE SET "
                "quantity = inventory.quantity + EXCLUDED.quantity",
                user_id,
                asset,
                quantity,
            )

    async def get_item_quantity(self, user_id: int, item_key: str) -> int:
        row = await self._fetchone(
            "SELECT quantity FROM inventory WHERE user_id = $1 AND item_key = $2", user_id, item_key
        )
        return row[0] if row else 0

    async def add_item(self, user_id: int, item_key: str, quantity: int) -> None:
        await self._execute(
            "INSERT INTO inventory (user_id, item_key, quantity) VALUES ($1, $2, $3) "
            "ON CONFLICT (user_id, item_key) DO UPDATE SET "
            "quantity = inventory.quantity + EXCLUDED.quantity",
            user_id,
            item_key,
            quantity,
        )

    async def remove_item(self, user_id: int, item_key: str, quantity: int) -> None:
        rowcount = await self._execute(
            "UPDATE inventory SET quantity = quantity - $1 "
            "WHERE user_id = $2 AND item_key = $3 AND quantity >= $1",
            quantity,
            user_id,
            item_key,
        )
        if rowcount == 0:
            raise InsufficientFunds(f"User {user_id} does not have {quantity}x {item_key}")


    async def record_game_result(self, user_id: int, wagered: int, payout: int) -> None:
        net = payout - wagered
        await self._execute(
            "INSERT INTO stats (user_id, games_played, total_wagered, total_won, biggest_win) "
            "VALUES ($1, 1, $2, $3, $4) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "games_played = stats.games_played + 1, "
            "total_wagered = stats.total_wagered + EXCLUDED.total_wagered, "
            "total_won = stats.total_won + EXCLUDED.total_won, "
            "biggest_win = GREATEST(stats.biggest_win, EXCLUDED.biggest_win)",
            user_id,
            wagered,
            payout,
            max(net, 0),
        )

    async def record_rob_attempt(self, user_id: int, success: bool) -> None:
        await self._execute(
            "INSERT INTO stats (user_id, robs_attempted, robs_succeeded) VALUES ($1, 1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET "
            "robs_attempted = stats.robs_attempted + 1, "
            "robs_succeeded = stats.robs_succeeded + EXCLUDED.robs_succeeded",
            user_id,
            1 if success else 0,
        )

    async def record_robbed(self, user_id: int) -> None:
        await self._execute(
            "INSERT INTO stats (user_id, times_robbed) VALUES ($1, 1) "
            "ON CONFLICT (user_id) DO UPDATE SET times_robbed = stats.times_robbed + 1",
            user_id,
        )

    async def get_stats(self, user_id: int) -> dict:
        row = await self._fetchone(
            "SELECT games_played, total_wagered, total_won, biggest_win, "
            "robs_attempted, robs_succeeded, times_robbed FROM stats WHERE user_id = $1",
            user_id,
        )
        keys = (
            "games_played",
            "total_wagered",
            "total_won",
            "biggest_win",
            "robs_attempted",
            "robs_succeeded",
            "times_robbed",
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
        rows = await self._fetchall(
            f"SELECT user_id, {column} FROM stats ORDER BY {column} DESC LIMIT $1", limit
        )
        return [(r[0], r[1]) for r in rows]


    async def get_guild_settings(self, guild_id: int) -> tuple[set[str], set[int]]:
        row = await self._fetchone(
            "SELECT disabled_games, allowed_channels FROM guild_settings WHERE guild_id = $1",
            guild_id,
        )
        if not row:
            return set(), set()
        disabled = {g for g in row[0].split(",") if g}
        channels = {int(c) for c in row[1].split(",") if c}
        return disabled, channels

    async def set_game_disabled(self, guild_id: int, game: str, disabled: bool) -> None:
        current_disabled, _ = await self.get_guild_settings(guild_id)
        if disabled:
            current_disabled.add(game)
        else:
            current_disabled.discard(game)
        await self._execute(
            "INSERT INTO guild_settings (guild_id, disabled_games) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET disabled_games = EXCLUDED.disabled_games",
            guild_id,
            ",".join(sorted(current_disabled)),
        )

    async def set_allowed_channels(self, guild_id: int, channels: set[int]) -> None:
        await self._execute(
            "INSERT INTO guild_settings (guild_id, allowed_channels) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET allowed_channels = EXCLUDED.allowed_channels",
            guild_id,
            ",".join(str(c) for c in sorted(channels)),
        )


    async def get_gamble_channel(self, guild_id: int) -> int | None:
        row = await self._fetchone(
            "SELECT channel_id FROM gamble_channels WHERE guild_id = $1", guild_id
        )
        return row[0] if row else None

    async def set_gamble_channel(self, guild_id: int, channel_id: int) -> None:
        await self._execute(
            "INSERT INTO gamble_channels (guild_id, channel_id) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id",
            guild_id,
            channel_id,
        )

    async def clear_gamble_channel(self, guild_id: int) -> None:
        await self._execute("DELETE FROM gamble_channels WHERE guild_id = $1", guild_id)

    async def get_idle_tracker_message(self) -> tuple[int, datetime.datetime | None] | None:
        row = await self._fetchone("SELECT message_id, posted_at FROM idle_tracker_state WHERE id = 1")
        return (row[0], row[1]) if row and row[0] else None

    async def set_idle_tracker_message(self, message_id: int, posted_at: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO idle_tracker_state (id, message_id, posted_at) VALUES (1, $1, $2) "
            "ON CONFLICT (id) DO UPDATE SET message_id = $1, posted_at = $2",
            message_id,
            posted_at,
        )

    async def save_idle_session(
        self,
        user_id: int, dungeon_key: str, display_name: str, deadline: datetime.datetime,
        channel_id: int, message_id: int, stats_json: str,
    ) -> None:
        await self._execute(
            "INSERT INTO idle_sessions "
            "(user_id, dungeon_key, display_name, deadline, channel_id, message_id, stats_json) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) "
            "ON CONFLICT (user_id) DO UPDATE SET deadline = $4, stats_json = $7",
            user_id, dungeon_key, display_name, deadline, channel_id, message_id, stats_json,
        )

    async def get_all_idle_sessions(self) -> list[dict]:
        rows = await self._fetchall(
            "SELECT user_id, dungeon_key, display_name, deadline, channel_id, message_id, stats_json "
            "FROM idle_sessions"
        )
        return [
            {
                "user_id": r[0], "dungeon_key": r[1], "display_name": r[2], "deadline": r[3],
                "channel_id": r[4], "message_id": r[5], "stats_json": r[6],
            }
            for r in rows
        ]

    async def delete_idle_session(self, user_id: int) -> None:
        await self._execute("DELETE FROM idle_sessions WHERE user_id = $1", user_id)

    async def get_updates_channel(self, guild_id: int) -> int | None:
        row = await self._fetchone(
            "SELECT channel_id FROM updates_channels WHERE guild_id = $1", guild_id
        )
        return row[0] if row else None

    async def set_updates_channel(self, guild_id: int, channel_id: int) -> None:
        await self._execute(
            "INSERT INTO updates_channels (guild_id, channel_id) VALUES ($1, $2) "
            "ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id",
            guild_id,
            channel_id,
        )

    async def clear_updates_channel(self, guild_id: int) -> None:
        await self._execute("DELETE FROM updates_channels WHERE guild_id = $1", guild_id)

    async def all_updates_channels(self) -> list[tuple[int, int]]:
        return await self._fetchall("SELECT guild_id, channel_id FROM updates_channels")


    async def get_marriage(self, user_id: int) -> int | None:
        row = await self._fetchone("SELECT partner_id FROM marriages WHERE user_id = $1", user_id)
        return row[0] if row else None

    async def marry(self, user_id: int, partner_id: int) -> None:
        now = datetime.datetime.utcnow()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO marriages (user_id, partner_id, married_at) VALUES ($1, $2, $3)",
                    user_id,
                    partner_id,
                    now,
                )
                await conn.execute(
                    "INSERT INTO marriages (user_id, partner_id, married_at) VALUES ($1, $2, $3)",
                    partner_id,
                    user_id,
                    now,
                )

    async def divorce(self, user_id: int) -> int | None:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            return None
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM marriages WHERE user_id = ANY($1::bigint[])",
                    [user_id, partner_id],
                )
                row = await conn.fetchrow(
                    "SELECT balance FROM marriage_bank WHERE user_id_a = $1 AND user_id_b = $2 "
                    "FOR UPDATE",
                    a,
                    b,
                )
                if row and row[0] > 0:
                    pot = row[0]
                    half = pot // 2
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE user_id = $2", half, user_id
                    )
                    await conn.execute(
                        "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                        pot - half,
                        partner_id,
                    )
                await conn.execute(
                    "DELETE FROM marriage_bank WHERE user_id_a = $1 AND user_id_b = $2", a, b
                )
        return partner_id

    async def get_marriage_bank(self, user_id: int) -> int | None:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            return None
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
        row = await self._fetchone(
            "SELECT balance FROM marriage_bank WHERE user_id_a = $1 AND user_id_b = $2", a, b
        )
        return row[0] if row else 0

    async def deposit_marriage_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT partner_id FROM marriages WHERE user_id = $1 FOR UPDATE", user_id
                )
                if row is None:
                    raise InsufficientFunds(f"User {user_id} is not married")
                partner_id = row[0]
                a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)

                status = await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1",
                    amount,
                    user_id,
                )
                if _rowcount(status) == 0:
                    raise InsufficientFunds(f"User {user_id} cannot deposit {amount}")
                await conn.execute(
                    "INSERT INTO marriage_bank (user_id_a, user_id_b, balance) VALUES ($1, $2, $3) "
                    "ON CONFLICT (user_id_a, user_id_b) DO UPDATE SET "
                    "balance = marriage_bank.balance + EXCLUDED.balance",
                    a,
                    b,
                    amount,
                )
                wallet_row = await conn.fetchrow(
                    "SELECT balance FROM users WHERE user_id = $1", user_id
                )
                bank_row = await conn.fetchrow(
                    "SELECT balance FROM marriage_bank WHERE user_id_a = $1 AND user_id_b = $2", a, b
                )
                return wallet_row[0], bank_row[0]

    async def withdraw_marriage_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            raise InsufficientFunds(f"User {user_id} is not married")
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                status = await conn.execute(
                    "UPDATE marriage_bank SET balance = balance - $1 "
                    "WHERE user_id_a = $2 AND user_id_b = $3 AND balance >= $1",
                    amount,
                    a,
                    b,
                )
                if _rowcount(status) == 0:
                    raise InsufficientFunds(f"Marriage bank for {user_id} cannot afford {amount}")
                await conn.execute(
                    "UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, user_id
                )
                wallet_row = await conn.fetchrow(
                    "SELECT balance FROM users WHERE user_id = $1", user_id
                )
                bank_row = await conn.fetchrow(
                    "SELECT balance FROM marriage_bank WHERE user_id_a = $1 AND user_id_b = $2", a, b
                )
                return wallet_row[0], bank_row[0]


    async def get_lottery_state(self) -> dict:
        row = await self._fetchone(
            "SELECT pot, next_draw, channel_id FROM lottery_state WHERE id = 1"
        )
        return {"pot": row[0], "next_draw": row[1], "channel_id": row[2]}

    async def set_lottery_channel(self, channel_id: int) -> None:
        await self._execute("UPDATE lottery_state SET channel_id = $1 WHERE id = 1", channel_id)

    async def get_lottery_tickets(self, user_id: int) -> int:
        row = await self._fetchone(
            "SELECT quantity FROM lottery_tickets WHERE user_id = $1", user_id
        )
        return row[0] if row else 0

    async def buy_lottery_tickets(self, user_id: int, quantity: int, cost: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                status = await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1",
                    cost,
                    user_id,
                )
                if _rowcount(status) == 0:
                    raise InsufficientFunds(f"User {user_id} cannot afford {cost}")
                await conn.execute(
                    "INSERT INTO lottery_tickets (user_id, quantity) VALUES ($1, $2) "
                    "ON CONFLICT (user_id) DO UPDATE SET "
                    "quantity = lottery_tickets.quantity + EXCLUDED.quantity",
                    user_id,
                    quantity,
                )
                await conn.execute("UPDATE lottery_state SET pot = pot + $1 WHERE id = 1", cost)

    async def all_lottery_tickets(self) -> list[tuple[int, int]]:
        rows = await self._fetchall(
            "SELECT user_id, quantity FROM lottery_tickets WHERE quantity > 0"
        )
        return [(r[0], r[1]) for r in rows]

    async def reset_lottery(self, next_draw: datetime.datetime) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM lottery_tickets")
                await conn.execute(
                    "UPDATE lottery_state SET pot = 0, next_draw = $1 WHERE id = 1", next_draw
                )


    async def create_character(self, user_id: int, class_key: str, starting_hp: int) -> None:
        now = datetime.datetime.utcnow()
        await self._execute(
            "INSERT INTO characters (user_id, class_key, current_hp, hp_updated_at) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO NOTHING",
            user_id,
            class_key,
            starting_hp,
            now,
        )

    async def get_character(self, user_id: int) -> dict | None:
        row = await self._fetchone(
            "SELECT c.class_key, c.level, c.xp, c.equipped_weapon, c.equipped_armor, c.equipped_accessory, "
            "c.wins, c.losses, c.current_hp, c.hp_updated_at, "
            "c.weapon_enchant, c.armor_enchant, c.accessory_enchant, "
            "c.equipped_primordial_weapon_id, c.equipped_primordial_armor_id, c.equipped_primordial_accessory_id, "
            "pw.affixes, pa.affixes, pacc.affixes "
            "FROM characters c "
            "LEFT JOIN primordial_items pw ON pw.id = c.equipped_primordial_weapon_id "
            "LEFT JOIN primordial_items pa ON pa.id = c.equipped_primordial_armor_id "
            "LEFT JOIN primordial_items pacc ON pacc.id = c.equipped_primordial_accessory_id "
            "WHERE c.user_id = $1",
            user_id,
        )
        if not row:
            return None
        keys = (
            "class_key",
            "level",
            "xp",
            "equipped_weapon",
            "equipped_armor",
            "equipped_accessory",
            "wins",
            "losses",
            "current_hp",
            "hp_updated_at",
            "weapon_enchant",
            "armor_enchant",
            "accessory_enchant",
            "equipped_primordial_weapon_id",
            "equipped_primordial_armor_id",
            "equipped_primordial_accessory_id",
        )
        values = list(row)
        character = dict(zip(keys, values[:16]))
        weapon_affixes, armor_affixes, accessory_affixes = values[16], values[17], values[18]
        character["primordial_weapon"] = {"affixes": json.loads(weapon_affixes)} if weapon_affixes else None
        character["primordial_armor"] = {"affixes": json.loads(armor_affixes)} if armor_affixes else None
        character["primordial_accessory"] = {"affixes": json.loads(accessory_affixes)} if accessory_affixes else None
        return character

    _CHARACTER_SWAP_COLUMNS = (
        "class_key", "level", "xp", "equipped_weapon", "equipped_armor", "equipped_accessory",
        "wins", "losses", "current_hp", "hp_updated_at",
        "weapon_enchant", "armor_enchant", "accessory_enchant",
        "equipped_primordial_weapon_id", "equipped_primordial_armor_id", "equipped_primordial_accessory_id",
    )

    async def get_character_backup(self, user_id: int) -> dict | None:
        cols = self._CHARACTER_SWAP_COLUMNS
        row = await self._fetchone(f"SELECT {', '.join(cols)} FROM character_backup WHERE user_id = $1", user_id)
        if not row:
            return None
        return dict(zip(cols, row))

    async def swap_character_slot(self, user_id: int, new_class_key: str, starting_hp: int) -> None:
        cols = self._CHARACTER_SWAP_COLUMNS
        now = datetime.datetime.utcnow()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow(
                    f"SELECT {', '.join(cols)} FROM characters WHERE user_id = $1 FOR UPDATE", user_id
                )
                if not current:
                    raise ValueError(f"User {user_id} has no active character")

                backup = await conn.fetchrow(
                    f"SELECT {', '.join(cols)} FROM character_backup WHERE user_id = $1 FOR UPDATE", user_id
                )

                col_list = ", ".join(cols)
                placeholders = ", ".join(f"${i + 2}" for i in range(len(cols)))
                update_list = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
                await conn.execute(
                    f"INSERT INTO character_backup (user_id, {col_list}) VALUES ($1, {placeholders}) "
                    f"ON CONFLICT (user_id) DO UPDATE SET {update_list}",
                    user_id, *current,
                )

                if backup and backup[0] == new_class_key:
                    set_clause = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(cols))
                    await conn.execute(
                        f"UPDATE characters SET {set_clause} WHERE user_id = $1", user_id, *backup
                    )
                else:
                    await conn.execute(
                        "UPDATE characters SET class_key = $1, level = 1, xp = 0, "
                        "equipped_weapon = NULL, equipped_armor = NULL, equipped_accessory = NULL, "
                        "wins = 0, losses = 0, current_hp = $2, hp_updated_at = $3, "
                        "weapon_enchant = 0, armor_enchant = 0, accessory_enchant = 0, "
                        "equipped_primordial_weapon_id = NULL, equipped_primordial_armor_id = NULL, "
                        "equipped_primordial_accessory_id = NULL "
                        "WHERE user_id = $4",
                        new_class_key, starting_hp, now, user_id,
                    )

    async def set_character_level(self, user_id: int, level: int, xp: int) -> None:
        await self._execute(
            "UPDATE characters SET level = $1, xp = $2 WHERE user_id = $3", level, xp, user_id
        )

    async def set_character_hp(self, user_id: int, hp: int, when: datetime.datetime) -> None:
        await self._execute(
            "UPDATE characters SET current_hp = $1, hp_updated_at = $2 WHERE user_id = $3",
            hp,
            when,
            user_id,
        )

    _EQUIP_COLUMNS = {
        "weapon": "equipped_weapon",
        "armor": "equipped_armor",
        "accessory": "equipped_accessory",
    }

    async def set_equipped(self, user_id: int, slot: str, item_key: str) -> None:
        column = self._EQUIP_COLUMNS[slot]
        await self._execute(
            f"UPDATE characters SET {column} = $1 WHERE user_id = $2", item_key, user_id
        )

    _ENCHANT_COLUMNS = {
        "weapon": "weapon_enchant",
        "armor": "armor_enchant",
        "accessory": "accessory_enchant",
    }

    async def set_enchant_level(self, user_id: int, slot: str, level: int) -> None:
        column = self._ENCHANT_COLUMNS[slot]
        await self._execute(f"UPDATE characters SET {column} = $1 WHERE user_id = $2", level, user_id)

    async def upgrade_enchant(self, user_id: int, slot: str, cost: int, new_level: int) -> int:
        column = self._ENCHANT_COLUMNS[slot]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                status = await conn.execute(
                    "UPDATE users SET balance = balance - $1 WHERE user_id = $2 AND balance >= $1",
                    cost,
                    user_id,
                )
                if _rowcount(status) == 0:
                    raise InsufficientFunds(f"User {user_id} cannot afford an upgrade costing {cost}")
                await conn.execute(
                    f"UPDATE characters SET {column} = $1 WHERE user_id = $2", new_level, user_id
                )
                row = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
                return row[0]

    _PRIMORDIAL_EQUIP_COLUMNS = {
        "weapon": "equipped_primordial_weapon_id",
        "armor": "equipped_primordial_armor_id",
        "accessory": "equipped_primordial_accessory_id",
    }

    async def add_primordial_item(self, user_id: int, slot: str, affixes_json: str) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO primordial_items (user_id, slot, affixes) VALUES ($1, $2, $3) RETURNING id",
                user_id,
                slot,
                affixes_json,
            )
            return row[0]

    async def get_primordial_items(self, user_id: int) -> list[dict]:
        rows = await self._fetchall(
            "SELECT id, slot, affixes FROM primordial_items WHERE user_id = $1 ORDER BY id",
            user_id,
        )
        return [{"id": r[0], "slot": r[1], "affixes": json.loads(r[2])} for r in rows]

    async def equip_primordial(self, user_id: int, slot: str, item_id: int) -> None:
        column = self._PRIMORDIAL_EQUIP_COLUMNS[slot]
        await self._execute(f"UPDATE characters SET {column} = $1 WHERE user_id = $2", item_id, user_id)

    async def unequip_primordial(self, user_id: int, slot: str) -> None:
        column = self._PRIMORDIAL_EQUIP_COLUMNS[slot]
        await self._execute(f"UPDATE characters SET {column} = NULL WHERE user_id = $1", user_id)

    async def get_boss_kills(self, user_id: int, dungeon_key: str) -> int:
        row = await self._fetchone(
            "SELECT kills FROM boss_kills WHERE user_id = $1 AND dungeon_key = $2",
            user_id,
            dungeon_key,
        )
        return row[0] if row else 0

    async def record_boss_kill(self, user_id: int, dungeon_key: str) -> None:
        await self._execute(
            "INSERT INTO boss_kills (user_id, dungeon_key, kills) VALUES ($1, $2, 1) "
            "ON CONFLICT (user_id, dungeon_key) DO UPDATE SET kills = boss_kills.kills + 1",
            user_id,
            dungeon_key,
        )

    async def total_boss_kills(self, user_id: int) -> int:
        row = await self._fetchone(
            "SELECT COALESCE(SUM(kills), 0) FROM boss_kills WHERE user_id = $1", user_id
        )
        return row[0] if row else 0

    async def record_duel_result(self, winner_id: int, loser_id: int) -> None:
        await self._execute("UPDATE characters SET wins = wins + 1 WHERE user_id = $1", winner_id)
        await self._execute("UPDATE characters SET losses = losses + 1 WHERE user_id = $1", loser_id)

    async def top_arena(self, limit: int = 10) -> list[tuple[int, int, int]]:
        rows = await self._fetchall(
            "SELECT user_id, wins, losses FROM characters ORDER BY wins DESC LIMIT $1", limit
        )
        return [(r[0], r[1], r[2]) for r in rows]

    async def get_rpg_inventory(self, user_id: int) -> list[tuple[str, int]]:
        rows = await self._fetchall(
            "SELECT item_key, quantity FROM rpg_equipment WHERE user_id = $1 AND quantity > 0",
            user_id,
        )
        return [(r[0], r[1]) for r in rows]

    async def get_rpg_item_quantity(self, user_id: int, item_key: str) -> int:
        row = await self._fetchone(
            "SELECT quantity FROM rpg_equipment WHERE user_id = $1 AND item_key = $2",
            user_id,
            item_key,
        )
        return row[0] if row else 0

    async def add_rpg_item(self, user_id: int, item_key: str, quantity: int) -> None:
        await self._execute(
            "INSERT INTO rpg_equipment (user_id, item_key, quantity) VALUES ($1, $2, $3) "
            "ON CONFLICT (user_id, item_key) DO UPDATE SET "
            "quantity = rpg_equipment.quantity + EXCLUDED.quantity",
            user_id,
            item_key,
            quantity,
        )

    async def remove_rpg_item(self, user_id: int, item_key: str, quantity: int) -> None:
        rowcount = await self._execute(
            "UPDATE rpg_equipment SET quantity = quantity - $1 "
            "WHERE user_id = $2 AND item_key = $3 AND quantity >= $1",
            quantity,
            user_id,
            item_key,
        )
        if rowcount == 0:
            raise InsufficientFunds(f"User {user_id} does not have {quantity}x {item_key}")


    async def reset_user(self, user_id: int, starting_balance: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE users SET balance = $1, bank_balance = 0, last_daily = NULL, "
                    "daily_streak = 0, protected_until = NULL, cooldown_bypass = FALSE "
                    "WHERE user_id = $2",
                    starting_balance,
                    user_id,
                )
                await conn.execute("DELETE FROM inventory WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM stats WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM lottery_tickets WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM cooldowns WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM characters WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM rpg_equipment WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM boss_kills WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM primordial_items WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM item_use_limits WHERE user_id = $1", user_id)
                await conn.execute("DELETE FROM achievements WHERE user_id = $1", user_id)
        await self.divorce(user_id)

    async def get_level_xp(self, guild_id: int, user_id: int) -> int:
        row = await self._fetchone(
            "SELECT xp FROM level_xp WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return row[0] if row else 0

    async def get_level_last_xp_at(self, guild_id: int, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT last_xp_at FROM level_xp WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return row[0] if row and row[0] else None

    async def add_level_xp(self, guild_id: int, user_id: int, amount: int, now: datetime.datetime) -> int:
        await self._execute(
            "INSERT INTO level_xp (guild_id, user_id, xp, message_xp, last_xp_at) VALUES ($1, $2, $3, $3, $4) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET "
            "xp = level_xp.xp + EXCLUDED.xp, message_xp = level_xp.message_xp + EXCLUDED.message_xp, "
            "last_xp_at = EXCLUDED.last_xp_at",
            guild_id, user_id, amount, now,
        )
        row = await self._fetchone(
            "SELECT xp FROM level_xp WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return row[0]

    async def add_level_admin_xp(self, guild_id: int, user_id: int, amount: int) -> int:
        await self._execute(
            "INSERT INTO level_xp (guild_id, user_id, xp) VALUES ($1, $2, GREATEST($3, 0)) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET xp = GREATEST(level_xp.xp + $3, 0)",
            guild_id, user_id, amount,
        )
        row = await self._fetchone(
            "SELECT xp FROM level_xp WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return row[0]

    async def add_level_voice(self, guild_id: int, user_id: int, amount: int, seconds: int) -> int:
        await self._execute(
            "INSERT INTO level_xp (guild_id, user_id, xp, voice_xp, vc_seconds) VALUES ($1, $2, $3, $3, $4) "
            "ON CONFLICT (guild_id, user_id) DO UPDATE SET "
            "xp = level_xp.xp + EXCLUDED.xp, voice_xp = level_xp.voice_xp + EXCLUDED.voice_xp, "
            "vc_seconds = level_xp.vc_seconds + EXCLUDED.vc_seconds",
            guild_id, user_id, amount, seconds,
        )
        row = await self._fetchone(
            "SELECT xp FROM level_xp WHERE guild_id = $1 AND user_id = $2", guild_id, user_id
        )
        return row[0]

    async def get_level_stats(self, guild_id: int, user_id: int) -> dict:
        row = await self._fetchone(
            "SELECT xp, message_xp, voice_xp, vc_seconds FROM level_xp WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        if not row:
            return {"xp": 0, "message_xp": 0, "voice_xp": 0, "vc_seconds": 0}
        return {"xp": row[0], "message_xp": row[1], "voice_xp": row[2], "vc_seconds": row[3]}

    async def get_level_leaderboard(self, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
        rows = await self._fetchall(
            "SELECT user_id, xp FROM level_xp WHERE guild_id = $1 ORDER BY xp DESC LIMIT $2",
            guild_id, limit,
        )
        return [(r[0], r[1]) for r in rows]

    async def set_level_boost(self, guild_id: int, multiplier: float, expires_at: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO level_boost (guild_id, multiplier, expires_at) VALUES ($1, $2, $3) "
            "ON CONFLICT (guild_id) DO UPDATE SET multiplier = $2, expires_at = $3",
            guild_id, multiplier, expires_at,
        )

    async def get_level_boost(self, guild_id: int) -> tuple[float, datetime.datetime] | None:
        row = await self._fetchone(
            "SELECT multiplier, expires_at FROM level_boost WHERE guild_id = $1", guild_id
        )
        return (row[0], row[1]) if row else None

    async def clear_level_boost(self, guild_id: int) -> bool:
        status = await self._execute("DELETE FROM level_boost WHERE guild_id = $1", guild_id)
        return status > 0

    async def dump_all_tables(self) -> dict[str, list[dict]]:
        async with self.pool.acquire() as conn:
            table_rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            tables = [row[0] for row in table_rows]

            result: dict[str, list[dict]] = {}
            for table in tables:
                records = await conn.fetch(f'SELECT * FROM "{table}"')
                result[table] = [dict(r) for r in records]
            return result
