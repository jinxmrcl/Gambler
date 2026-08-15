import asyncio
import datetime
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
                    protected_until TIMESTAMP NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
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
                CREATE TABLE IF NOT EXISTS crash_channels (
                    guild_id BIGINT PRIMARY KEY,
                    channel_id BIGINT NOT NULL,
                    message_id BIGINT NULL
                )
                """
            )
            await conn.execute("ALTER TABLE crash_channels ADD COLUMN IF NOT EXISTS message_id BIGINT NULL")
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
        self, user_id: int, amount: int, period: datetime.timedelta, now: datetime.datetime
    ) -> int | None:
        cutoff = now - period
        rowcount = await self._execute(
            "UPDATE users SET balance = balance + $1, last_daily = $2 "
            "WHERE user_id = $3 AND (last_daily IS NULL OR last_daily <= $4)",
            amount,
            now,
            user_id,
            cutoff,
        )
        if rowcount == 0:
            return None
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = $1", user_id)
        return row[0]

    async def get_last_daily(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone("SELECT last_daily FROM users WHERE user_id = $1", user_id)
        return row[0] if row else None

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

    async def set_protected_until(self, user_id: int, when: datetime.datetime) -> None:
        await self._execute("UPDATE users SET protected_until = $1 WHERE user_id = $2", when, user_id)


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

    async def get_users_needing_payday_schedule(self) -> list[int]:
        rows = await self._fetchall(
            "SELECT u.user_id FROM users u "
            "LEFT JOIN cooldowns c ON c.user_id = u.user_id AND c.action = 'payday' "
            "WHERE c.user_id IS NULL"
        )
        return [row[0] for row in rows]

    async def get_due_paydays(self, now: datetime.datetime) -> list[int]:
        rows = await self._fetchall(
            "SELECT user_id FROM cooldowns WHERE action = 'payday' AND expires_at <= $1", now
        )
        return [row[0] for row in rows]


    async def get_inventory(self, user_id: int) -> list[tuple[str, int]]:
        rows = await self._fetchall(
            "SELECT item_key, quantity FROM inventory WHERE user_id = $1 AND quantity > 0", user_id
        )
        return [(r[0], r[1]) for r in rows]

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

    async def get_crash_channel(self, guild_id: int) -> int | None:
        row = await self._fetchone(
            "SELECT channel_id FROM crash_channels WHERE guild_id = $1", guild_id
        )
        return row[0] if row else None

    async def set_crash_channel(self, guild_id: int, channel_id: int) -> None:
        await self._execute(
            "INSERT INTO crash_channels (guild_id, channel_id, message_id) VALUES ($1, $2, NULL) "
            "ON CONFLICT (guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id, message_id = NULL",
            guild_id,
            channel_id,
        )

    async def clear_crash_channel(self, guild_id: int) -> None:
        await self._execute("DELETE FROM crash_channels WHERE guild_id = $1", guild_id)

    async def all_crash_channels(self) -> list[tuple[int, int]]:
        return await self._fetchall("SELECT guild_id, channel_id FROM crash_channels")

    async def get_crash_message(self, guild_id: int) -> int | None:
        row = await self._fetchone(
            "SELECT message_id FROM crash_channels WHERE guild_id = $1", guild_id
        )
        return row[0] if row and row[0] else None

    async def set_crash_message(self, guild_id: int, message_id: int) -> None:
        await self._execute(
            "UPDATE crash_channels SET message_id = $1 WHERE guild_id = $2", message_id, guild_id
        )

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
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            raise InsufficientFunds(f"User {user_id} is not married")
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
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
            "SELECT class_key, level, xp, equipped_weapon, equipped_armor, equipped_accessory, "
            "wins, losses, current_hp, hp_updated_at, weapon_enchant, armor_enchant, "
            "accessory_enchant FROM characters WHERE user_id = $1",
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
        )
        return dict(zip(keys, row))

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
                    "protected_until = NULL WHERE user_id = $2",
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
        await self.divorce(user_id)
