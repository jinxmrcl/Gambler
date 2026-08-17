import asyncio
import datetime
import json
import logging
import warnings

import aiomysql
import pymysql

log = logging.getLogger("gambler")


class InsufficientFunds(Exception):
    pass


class Database:
    def __init__(self, host: str, port: int, user: str, password: str, db: str):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._db = db
        self.pool: aiomysql.Pool | None = None

    async def connect(self, *, retries: int = 5, retry_delay: float = 3.0) -> None:
        for attempt in range(1, retries + 1):
            try:
                self.pool = await aiomysql.create_pool(
                    host=self._host,
                    port=self._port,
                    user=self._user,
                    password=self._password,
                    db=self._db,
                    autocommit=True,
                    minsize=1,
                    maxsize=10,
                    connect_timeout=10,
                    pool_recycle=3600,
                )
                break
            except Exception:
                if attempt == retries:
                    log.exception(
                        "Could not connect to MySQL at %s:%s (db=%s) after %d attempts. Check "
                        "DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME in your .env.",
                        self._host,
                        self._port,
                        self._db,
                        retries,
                    )
                    raise
                log.warning(
                    "MySQL connection attempt %d/%d failed, retrying in %.0fs (server may still "
                    "be starting up)...",
                    attempt,
                    retries,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
        await self._init_tables()

    async def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
            await self.pool.wait_closed()


    async def _execute(self, query: str, args: tuple = ()) -> int:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args)
                return cur.rowcount

    async def _fetchone(self, query: str, args: tuple = ()):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args)
                return await cur.fetchone()

    async def _fetchall(self, query: str, args: tuple = ()):
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args)
                return await cur.fetchall()

    async def _init_tables(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=pymysql.Warning)
            await self._create_tables()

    async def _create_tables(self) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT UNSIGNED PRIMARY KEY,
                        balance BIGINT NOT NULL DEFAULT 0,
                        bank_balance BIGINT NOT NULL DEFAULT 0,
                        last_daily DATETIME NULL,
                        protected_until DATETIME NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS inventory (
                        user_id BIGINT UNSIGNED NOT NULL,
                        item_key VARCHAR(32) NOT NULL,
                        quantity INT NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, item_key)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS stats (
                        user_id BIGINT UNSIGNED PRIMARY KEY,
                        games_played INT NOT NULL DEFAULT 0,
                        total_wagered BIGINT NOT NULL DEFAULT 0,
                        total_won BIGINT NOT NULL DEFAULT 0,
                        biggest_win BIGINT NOT NULL DEFAULT 0,
                        robs_attempted INT NOT NULL DEFAULT 0,
                        robs_succeeded INT NOT NULL DEFAULT 0,
                        times_robbed INT NOT NULL DEFAULT 0
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS guild_settings (
                        guild_id BIGINT UNSIGNED PRIMARY KEY,
                        disabled_games VARCHAR(255) NOT NULL DEFAULT '',
                        allowed_channels VARCHAR(255) NOT NULL DEFAULT ''
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gamble_channels (
                        guild_id BIGINT UNSIGNED PRIMARY KEY,
                        channel_id BIGINT UNSIGNED NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS crash_channels (
                        guild_id BIGINT UNSIGNED PRIMARY KEY,
                        channel_id BIGINT UNSIGNED NOT NULL,
                        message_id BIGINT UNSIGNED NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = 'crash_channels' AND column_name = 'message_id'"
                )
                (has_message_id,) = await cur.fetchone()
                if not has_message_id:
                    await cur.execute("ALTER TABLE crash_channels ADD COLUMN message_id BIGINT UNSIGNED NULL")
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS updates_channels (
                        guild_id BIGINT UNSIGNED PRIMARY KEY,
                        channel_id BIGINT UNSIGNED NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS marriages (
                        user_id BIGINT UNSIGNED PRIMARY KEY,
                        partner_id BIGINT UNSIGNED NOT NULL,
                        married_at DATETIME NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS marriage_bank (
                        user_id_a BIGINT UNSIGNED NOT NULL,
                        user_id_b BIGINT UNSIGNED NOT NULL,
                        balance BIGINT NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id_a, user_id_b)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lottery_tickets (
                        user_id BIGINT UNSIGNED PRIMARY KEY,
                        quantity INT NOT NULL DEFAULT 0
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lottery_state (
                        id TINYINT PRIMARY KEY,
                        pot BIGINT NOT NULL DEFAULT 0,
                        next_draw DATETIME NOT NULL,
                        channel_id BIGINT UNSIGNED NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS idle_tracker_state (
                        id TINYINT PRIMARY KEY,
                        message_id BIGINT UNSIGNED NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cooldowns (
                        user_id BIGINT UNSIGNED NOT NULL,
                        action VARCHAR(32) NOT NULL,
                        expires_at DATETIME NOT NULL,
                        PRIMARY KEY (user_id, action)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute("ALTER TABLE cooldowns MODIFY COLUMN action VARCHAR(32) NOT NULL")
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS item_use_limits (
                        user_id BIGINT UNSIGNED NOT NULL,
                        item_key VARCHAR(32) NOT NULL,
                        use_count INT NOT NULL DEFAULT 0,
                        window_started_at DATETIME NOT NULL,
                        PRIMARY KEY (user_id, item_key)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS characters (
                        user_id BIGINT UNSIGNED PRIMARY KEY,
                        class_key VARCHAR(16) NOT NULL,
                        level INT NOT NULL DEFAULT 1,
                        xp INT NOT NULL DEFAULT 0,
                        equipped_weapon VARCHAR(32) NULL,
                        equipped_armor VARCHAR(32) NULL,
                        equipped_accessory VARCHAR(32) NULL,
                        wins INT NOT NULL DEFAULT 0,
                        losses INT NOT NULL DEFAULT 0,
                        current_hp INT NULL,
                        hp_updated_at DATETIME NULL,
                        weapon_enchant INT NOT NULL DEFAULT 0,
                        armor_enchant INT NOT NULL DEFAULT 0,
                        accessory_enchant INT NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                for column, coltype in (
                    ("current_hp", "INT NULL"),
                    ("hp_updated_at", "DATETIME NULL"),
                    ("equipped_accessory", "VARCHAR(32) NULL"),
                    ("weapon_enchant", "INT NOT NULL DEFAULT 0"),
                    ("armor_enchant", "INT NOT NULL DEFAULT 0"),
                    ("accessory_enchant", "INT NOT NULL DEFAULT 0"),
                    ("equipped_primordial_weapon_id", "INT NULL"),
                    ("equipped_primordial_armor_id", "INT NULL"),
                    ("equipped_primordial_accessory_id", "INT NULL"),
                ):
                    await cur.execute(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() AND table_name = 'characters' AND column_name = %s",
                        (column,),
                    )
                    (exists,) = await cur.fetchone()
                    if not exists:
                        await cur.execute(f"ALTER TABLE characters ADD COLUMN {column} {coltype}")
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS rpg_equipment (
                        user_id BIGINT UNSIGNED NOT NULL,
                        item_key VARCHAR(32) NOT NULL,
                        quantity INT NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, item_key)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS boss_kills (
                        user_id BIGINT UNSIGNED NOT NULL,
                        dungeon_key VARCHAR(32) NOT NULL,
                        kills INT NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, dungeon_key)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS primordial_items (
                        id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                        user_id BIGINT UNSIGNED NOT NULL,
                        slot VARCHAR(16) NOT NULL,
                        affixes TEXT NOT NULL,
                        dropped_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS character_backup (
                        user_id BIGINT UNSIGNED PRIMARY KEY,
                        class_key VARCHAR(16) NOT NULL,
                        level INT NOT NULL DEFAULT 1,
                        xp INT NOT NULL DEFAULT 0,
                        equipped_weapon VARCHAR(32) NULL,
                        equipped_armor VARCHAR(32) NULL,
                        equipped_accessory VARCHAR(32) NULL,
                        wins INT NOT NULL DEFAULT 0,
                        losses INT NOT NULL DEFAULT 0,
                        current_hp INT NULL,
                        hp_updated_at DATETIME NULL,
                        weapon_enchant INT NOT NULL DEFAULT 0,
                        armor_enchant INT NOT NULL DEFAULT 0,
                        accessory_enchant INT NOT NULL DEFAULT 0,
                        equipped_primordial_weapon_id INT NULL,
                        equipped_primordial_armor_id INT NULL,
                        equipped_primordial_accessory_id INT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    "INSERT INTO lottery_state (id, pot, next_draw) VALUES (1, 0, %s) "
                    "ON DUPLICATE KEY UPDATE id = id",
                    (datetime.datetime.utcnow() + datetime.timedelta(days=7),),
                )


    async def ensure_user(self, user_id: int, starting_balance: int) -> None:
        await self._execute(
            "INSERT INTO users (user_id, balance) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE user_id = user_id",
            (user_id, starting_balance),
        )

    async def get_balance(self, user_id: int) -> int:
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        return row[0] if row else 0

    async def update_balance(self, user_id: int, delta: int) -> int:
        rowcount = await self._execute(
            "UPDATE users SET balance = balance + %s "
            "WHERE user_id = %s AND balance + %s >= 0",
            (delta, user_id, delta),
        )
        if rowcount == 0:
            raise InsufficientFunds(f"User {user_id} cannot afford a change of {delta}")
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        return row[0]

    async def transfer_balance(self, sender_id: int, recipient_id: int, amount: int) -> int:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute(
                        "UPDATE users SET balance = balance - %s "
                        "WHERE user_id = %s AND balance >= %s",
                        (amount, sender_id, amount),
                    )
                    if cur.rowcount == 0:
                        await conn.rollback()
                        raise InsufficientFunds(f"User {sender_id} cannot afford a transfer of {amount}")
                    await cur.execute(
                        "UPDATE users SET balance = balance + %s WHERE user_id = %s",
                        (amount, recipient_id),
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
                await cur.execute("SELECT balance FROM users WHERE user_id = %s", (sender_id,))
                row = await cur.fetchone()
                return row[0]

    async def set_balance(self, user_id: int, amount: int) -> None:
        await self._execute("UPDATE users SET balance = %s WHERE user_id = %s", (amount, user_id))

    async def claim_daily(
        self, user_id: int, amount: int, period: datetime.timedelta, now: datetime.datetime
    ) -> int | None:
        cutoff = now - period
        rowcount = await self._execute(
            "UPDATE users SET balance = balance + %s, last_daily = %s "
            "WHERE user_id = %s AND (last_daily IS NULL OR last_daily <= %s)",
            (amount, now, user_id, cutoff),
        )
        if rowcount == 0:
            return None
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        return row[0]

    async def get_last_daily(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone("SELECT last_daily FROM users WHERE user_id = %s", (user_id,))
        return row[0] if row else None

    async def top_balances(self, limit: int = 10) -> list[tuple[int, int]]:
        return await self._fetchall(
            "SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT %s",
            (limit,),
        )

    async def give_all_users(self, amount: int) -> int:
        return await self._execute(
            "UPDATE users SET balance = GREATEST(balance + %s, 0)", (amount,)
        )


    async def get_bank_balance(self, user_id: int) -> int:
        row = await self._fetchone("SELECT bank_balance FROM users WHERE user_id = %s", (user_id,))
        return row[0] if row else 0

    async def deposit_to_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute(
                        "UPDATE users SET balance = balance - %s "
                        "WHERE user_id = %s AND balance >= %s",
                        (amount, user_id, amount),
                    )
                    if cur.rowcount == 0:
                        await conn.rollback()
                        raise InsufficientFunds(f"User {user_id} cannot deposit {amount}")
                    await cur.execute(
                        "UPDATE users SET bank_balance = bank_balance + %s WHERE user_id = %s",
                        (amount, user_id),
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
                await cur.execute(
                    "SELECT balance, bank_balance FROM users WHERE user_id = %s", (user_id,)
                )
                return await cur.fetchone()

    async def withdraw_from_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute(
                        "UPDATE users SET bank_balance = bank_balance - %s "
                        "WHERE user_id = %s AND bank_balance >= %s",
                        (amount, user_id, amount),
                    )
                    if cur.rowcount == 0:
                        await conn.rollback()
                        raise InsufficientFunds(f"User {user_id} cannot withdraw {amount}")
                    await cur.execute(
                        "UPDATE users SET balance = balance + %s WHERE user_id = %s",
                        (amount, user_id),
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
                await cur.execute(
                    "SELECT balance, bank_balance FROM users WHERE user_id = %s", (user_id,)
                )
                return await cur.fetchone()


    async def get_protected_until(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT protected_until FROM users WHERE user_id = %s", (user_id,)
        )
        return row[0] if row else None

    async def set_protected_until(self, user_id: int, when: datetime.datetime) -> None:
        await self._execute(
            "UPDATE users SET protected_until = %s WHERE user_id = %s", (when, user_id)
        )


    async def get_cooldown(self, user_id: int, action: str) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT expires_at FROM cooldowns WHERE user_id = %s AND action = %s",
            (user_id, action),
        )
        return row[0] if row else None

    async def set_cooldown(self, user_id: int, action: str, expires_at: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO cooldowns (user_id, action, expires_at) VALUES (%s, %s, %s) AS new "
            "ON DUPLICATE KEY UPDATE expires_at = new.expires_at",
            (user_id, action, expires_at),
        )

    async def try_consume_cooldown(
        self, user_id: int, action: str, period: datetime.timedelta, now: datetime.datetime
    ) -> bool:
        rowcount = await self._execute(
            "INSERT INTO cooldowns (user_id, action, expires_at) VALUES (%s, %s, %s) AS new "
            "ON DUPLICATE KEY UPDATE "
            "expires_at = IF(cooldowns.expires_at <= %s, new.expires_at, cooldowns.expires_at)",
            (user_id, action, now + period, now),
        )
        return rowcount > 0

    async def clear_cooldowns(self, user_id: int, actions: tuple[str, ...]) -> None:
        if not actions:
            return
        placeholders = ", ".join(["%s"] * len(actions))
        await self._execute(
            f"DELETE FROM cooldowns WHERE user_id = %s AND action IN ({placeholders})",
            (user_id, *actions),
        )

    async def get_item_use_count(
        self, user_id: int, item_key: str, window: datetime.timedelta, now: datetime.datetime
    ) -> int:
        row = await self._fetchone(
            "SELECT use_count, window_started_at FROM item_use_limits WHERE user_id = %s AND item_key = %s",
            (user_id, item_key),
        )
        if not row:
            return 0
        use_count, window_started_at = row
        if now - window_started_at >= window:
            return 0
        return use_count

    async def record_item_use(
        self, user_id: int, item_key: str, window: datetime.timedelta, now: datetime.datetime
    ) -> None:
        row = await self._fetchone(
            "SELECT use_count, window_started_at FROM item_use_limits WHERE user_id = %s AND item_key = %s",
            (user_id, item_key),
        )
        if row and (now - row[1]) < window:
            new_count = row[0] + 1
            window_start = row[1]
        else:
            new_count = 1
            window_start = now
        await self._execute(
            "INSERT INTO item_use_limits (user_id, item_key, use_count, window_started_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE use_count = %s, window_started_at = %s",
            (user_id, item_key, new_count, window_start, new_count, window_start),
        )

    async def get_item_use_reset(
        self, user_id: int, item_key: str, window: datetime.timedelta
    ) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT window_started_at FROM item_use_limits WHERE user_id = %s AND item_key = %s",
            (user_id, item_key),
        )
        if not row:
            return None
        return row[0] + window

    async def get_users_needing_payday_schedule(self) -> list[int]:
        rows = await self._fetchall(
            "SELECT u.user_id FROM users u "
            "LEFT JOIN cooldowns c ON c.user_id = u.user_id AND c.action = 'payday' "
            "WHERE c.user_id IS NULL"
        )
        return [row[0] for row in rows]

    async def get_due_paydays(self, now: datetime.datetime) -> list[int]:
        rows = await self._fetchall(
            "SELECT user_id FROM cooldowns WHERE action = 'payday' AND expires_at <= %s", (now,)
        )
        return [row[0] for row in rows]


    async def get_inventory(self, user_id: int) -> list[tuple[str, int]]:
        return await self._fetchall(
            "SELECT item_key, quantity FROM inventory WHERE user_id = %s AND quantity > 0",
            (user_id,),
        )

    async def get_item_quantity(self, user_id: int, item_key: str) -> int:
        row = await self._fetchone(
            "SELECT quantity FROM inventory WHERE user_id = %s AND item_key = %s",
            (user_id, item_key),
        )
        return row[0] if row else 0

    async def add_item(self, user_id: int, item_key: str, quantity: int) -> None:
        await self._execute(
            "INSERT INTO inventory (user_id, item_key, quantity) VALUES (%s, %s, %s) AS new "
            "ON DUPLICATE KEY UPDATE quantity = inventory.quantity + new.quantity",
            (user_id, item_key, quantity),
        )

    async def remove_item(self, user_id: int, item_key: str, quantity: int) -> None:
        rowcount = await self._execute(
            "UPDATE inventory SET quantity = quantity - %s "
            "WHERE user_id = %s AND item_key = %s AND quantity >= %s",
            (quantity, user_id, item_key, quantity),
        )
        if rowcount == 0:
            raise InsufficientFunds(f"User {user_id} does not have {quantity}x {item_key}")


    async def record_game_result(self, user_id: int, wagered: int, payout: int) -> None:
        net = payout - wagered
        await self._execute(
            "INSERT INTO stats (user_id, games_played, total_wagered, total_won, biggest_win) "
            "VALUES (%s, 1, %s, %s, %s) AS new "
            "ON DUPLICATE KEY UPDATE "
            "stats.games_played = stats.games_played + 1, "
            "stats.total_wagered = stats.total_wagered + new.total_wagered, "
            "stats.total_won = stats.total_won + new.total_won, "
            "stats.biggest_win = GREATEST(stats.biggest_win, new.biggest_win)",
            (user_id, wagered, payout, max(net, 0)),
        )

    async def record_rob_attempt(self, user_id: int, success: bool) -> None:
        await self._execute(
            "INSERT INTO stats (user_id, robs_attempted, robs_succeeded) VALUES (%s, 1, %s) AS new "
            "ON DUPLICATE KEY UPDATE "
            "stats.robs_attempted = stats.robs_attempted + 1, "
            "stats.robs_succeeded = stats.robs_succeeded + new.robs_succeeded",
            (user_id, 1 if success else 0),
        )

    async def record_robbed(self, user_id: int) -> None:
        await self._execute(
            "INSERT INTO stats (user_id, times_robbed) VALUES (%s, 1) "
            "ON DUPLICATE KEY UPDATE times_robbed = times_robbed + 1",
            (user_id,),
        )

    async def get_stats(self, user_id: int) -> dict:
        row = await self._fetchone(
            "SELECT games_played, total_wagered, total_won, biggest_win, "
            "robs_attempted, robs_succeeded, times_robbed FROM stats WHERE user_id = %s",
            (user_id,),
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
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT user_id, {column} FROM stats ORDER BY {column} DESC LIMIT %s",
                    (limit,),
                )
                return await cur.fetchall()


    async def get_guild_settings(self, guild_id: int) -> tuple[set[str], set[int]]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT disabled_games, allowed_channels FROM guild_settings WHERE guild_id = %s",
                    (guild_id,),
                )
                row = await cur.fetchone()
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
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO guild_settings (guild_id, disabled_games) VALUES (%s, %s) AS new "
                    "ON DUPLICATE KEY UPDATE disabled_games = new.disabled_games",
                    (guild_id, ",".join(sorted(current_disabled))),
                )

    async def set_allowed_channels(self, guild_id: int, channels: set[int]) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO guild_settings (guild_id, allowed_channels) VALUES (%s, %s) AS new "
                    "ON DUPLICATE KEY UPDATE allowed_channels = new.allowed_channels",
                    (guild_id, ",".join(str(c) for c in sorted(channels))),
                )


    async def get_gamble_channel(self, guild_id: int) -> int | None:
        row = await self._fetchone(
            "SELECT channel_id FROM gamble_channels WHERE guild_id = %s", (guild_id,)
        )
        return row[0] if row else None

    async def set_gamble_channel(self, guild_id: int, channel_id: int) -> None:
        await self._execute(
            "INSERT INTO gamble_channels (guild_id, channel_id) VALUES (%s, %s) AS new "
            "ON DUPLICATE KEY UPDATE channel_id = new.channel_id",
            (guild_id, channel_id),
        )

    async def clear_gamble_channel(self, guild_id: int) -> None:
        await self._execute("DELETE FROM gamble_channels WHERE guild_id = %s", (guild_id,))

    async def get_crash_channel(self, guild_id: int) -> int | None:
        row = await self._fetchone(
            "SELECT channel_id FROM crash_channels WHERE guild_id = %s", (guild_id,)
        )
        return row[0] if row else None

    async def set_crash_channel(self, guild_id: int, channel_id: int) -> None:
        await self._execute(
            "INSERT INTO crash_channels (guild_id, channel_id, message_id) VALUES (%s, %s, NULL) AS new "
            "ON DUPLICATE KEY UPDATE channel_id = new.channel_id, message_id = NULL",
            (guild_id, channel_id),
        )

    async def clear_crash_channel(self, guild_id: int) -> None:
        await self._execute("DELETE FROM crash_channels WHERE guild_id = %s", (guild_id,))

    async def all_crash_channels(self) -> list[tuple[int, int]]:
        return await self._fetchall("SELECT guild_id, channel_id FROM crash_channels")

    async def get_crash_message(self, guild_id: int) -> int | None:
        row = await self._fetchone(
            "SELECT message_id FROM crash_channels WHERE guild_id = %s", (guild_id,)
        )
        return row[0] if row and row[0] else None

    async def set_crash_message(self, guild_id: int, message_id: int) -> None:
        await self._execute(
            "UPDATE crash_channels SET message_id = %s WHERE guild_id = %s", (message_id, guild_id)
        )

    async def get_idle_tracker_message(self) -> int | None:
        row = await self._fetchone("SELECT message_id FROM idle_tracker_state WHERE id = 1")
        return row[0] if row and row[0] else None

    async def set_idle_tracker_message(self, message_id: int) -> None:
        await self._execute(
            "INSERT INTO idle_tracker_state (id, message_id) VALUES (1, %s) "
            "ON DUPLICATE KEY UPDATE message_id = VALUES(message_id)",
            (message_id,),
        )

    async def get_updates_channel(self, guild_id: int) -> int | None:
        row = await self._fetchone(
            "SELECT channel_id FROM updates_channels WHERE guild_id = %s", (guild_id,)
        )
        return row[0] if row else None

    async def set_updates_channel(self, guild_id: int, channel_id: int) -> None:
        await self._execute(
            "INSERT INTO updates_channels (guild_id, channel_id) VALUES (%s, %s) AS new "
            "ON DUPLICATE KEY UPDATE channel_id = new.channel_id",
            (guild_id, channel_id),
        )

    async def clear_updates_channel(self, guild_id: int) -> None:
        await self._execute("DELETE FROM updates_channels WHERE guild_id = %s", (guild_id,))

    async def all_updates_channels(self) -> list[tuple[int, int]]:
        return await self._fetchall("SELECT guild_id, channel_id FROM updates_channels")


    async def get_marriage(self, user_id: int) -> int | None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT partner_id FROM marriages WHERE user_id = %s", (user_id,))
                row = await cur.fetchone()
                return row[0] if row else None

    async def marry(self, user_id: int, partner_id: int) -> None:
        now = datetime.datetime.utcnow()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO marriages (user_id, partner_id, married_at) VALUES (%s, %s, %s)",
                    (user_id, partner_id, now),
                )
                await cur.execute(
                    "INSERT INTO marriages (user_id, partner_id, married_at) VALUES (%s, %s, %s)",
                    (partner_id, user_id, now),
                )

    async def divorce(self, user_id: int) -> int | None:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            return None
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute("DELETE FROM marriages WHERE user_id IN (%s, %s)", (user_id, partner_id))
                    a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
                    await cur.execute(
                        "SELECT balance FROM marriage_bank WHERE user_id_a = %s AND user_id_b = %s FOR UPDATE",
                        (a, b),
                    )
                    row = await cur.fetchone()
                    if row and row[0] > 0:
                        pot = row[0]
                        half = pot // 2
                        await cur.execute(
                            "UPDATE users SET balance = balance + %s WHERE user_id = %s", (half, user_id)
                        )
                        await cur.execute(
                            "UPDATE users SET balance = balance + %s WHERE user_id = %s",
                            (pot - half, partner_id),
                        )
                    await cur.execute(
                        "DELETE FROM marriage_bank WHERE user_id_a = %s AND user_id_b = %s", (a, b)
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
        return partner_id


    async def get_marriage_bank(self, user_id: int) -> int | None:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            return None
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)
        row = await self._fetchone(
            "SELECT balance FROM marriage_bank WHERE user_id_a = %s AND user_id_b = %s", (a, b)
        )
        return row[0] if row else 0

    async def deposit_marriage_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            raise InsufficientFunds(f"User {user_id} is not married")
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute(
                        "UPDATE users SET balance = balance - %s "
                        "WHERE user_id = %s AND balance >= %s",
                        (amount, user_id, amount),
                    )
                    if cur.rowcount == 0:
                        await conn.rollback()
                        raise InsufficientFunds(f"User {user_id} cannot deposit {amount}")
                    await cur.execute(
                        "INSERT INTO marriage_bank (user_id_a, user_id_b, balance) VALUES (%s, %s, %s) AS new "
                        "ON DUPLICATE KEY UPDATE balance = marriage_bank.balance + new.balance",
                        (a, b, amount),
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
                await cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
                wallet = (await cur.fetchone())[0]
                await cur.execute(
                    "SELECT balance FROM marriage_bank WHERE user_id_a = %s AND user_id_b = %s", (a, b)
                )
                bank = (await cur.fetchone())[0]
                return wallet, bank

    async def withdraw_marriage_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        partner_id = await self.get_marriage(user_id)
        if partner_id is None:
            raise InsufficientFunds(f"User {user_id} is not married")
        a, b = (user_id, partner_id) if user_id < partner_id else (partner_id, user_id)

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute(
                        "UPDATE marriage_bank SET balance = balance - %s "
                        "WHERE user_id_a = %s AND user_id_b = %s AND balance >= %s",
                        (amount, a, b, amount),
                    )
                    if cur.rowcount == 0:
                        await conn.rollback()
                        raise InsufficientFunds(f"Marriage bank for {user_id} cannot afford {amount}")
                    await cur.execute(
                        "UPDATE users SET balance = balance + %s WHERE user_id = %s", (amount, user_id)
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
                await cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
                wallet = (await cur.fetchone())[0]
                await cur.execute(
                    "SELECT balance FROM marriage_bank WHERE user_id_a = %s AND user_id_b = %s", (a, b)
                )
                bank = (await cur.fetchone())[0]
                return wallet, bank


    async def get_lottery_state(self) -> dict:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT pot, next_draw, channel_id FROM lottery_state WHERE id = 1")
                pot, next_draw, channel_id = await cur.fetchone()
                return {"pot": pot, "next_draw": next_draw, "channel_id": channel_id}

    async def set_lottery_channel(self, channel_id: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE lottery_state SET channel_id = %s WHERE id = 1", (channel_id,)
                )

    async def get_lottery_tickets(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT quantity FROM lottery_tickets WHERE user_id = %s", (user_id,)
                )
                row = await cur.fetchone()
                return row[0] if row else 0

    async def buy_lottery_tickets(self, user_id: int, quantity: int, cost: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute(
                        "UPDATE users SET balance = balance - %s "
                        "WHERE user_id = %s AND balance >= %s",
                        (cost, user_id, cost),
                    )
                    if cur.rowcount == 0:
                        await conn.rollback()
                        raise InsufficientFunds(f"User {user_id} cannot afford {cost}")
                    await cur.execute(
                        "INSERT INTO lottery_tickets (user_id, quantity) VALUES (%s, %s) AS new "
                        "ON DUPLICATE KEY UPDATE quantity = lottery_tickets.quantity + new.quantity",
                        (user_id, quantity),
                    )
                    await cur.execute(
                        "UPDATE lottery_state SET pot = pot + %s WHERE id = 1", (cost,)
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise

    async def all_lottery_tickets(self) -> list[tuple[int, int]]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT user_id, quantity FROM lottery_tickets WHERE quantity > 0")
                return await cur.fetchall()

    async def reset_lottery(self, next_draw: datetime.datetime) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM lottery_tickets")
                await cur.execute(
                    "UPDATE lottery_state SET pot = 0, next_draw = %s WHERE id = 1", (next_draw,)
                )


    async def create_character(self, user_id: int, class_key: str, starting_hp: int) -> None:
        now = datetime.datetime.utcnow()
        await self._execute(
            "INSERT INTO characters (user_id, class_key, current_hp, hp_updated_at) "
            "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE user_id = user_id",
            (user_id, class_key, starting_hp, now),
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
            "WHERE c.user_id = %s",
            (user_id,),
        )
        if not row:
            return None
        keys = (
            "class_key", "level", "xp", "equipped_weapon", "equipped_armor", "equipped_accessory",
            "wins", "losses", "current_hp", "hp_updated_at",
            "weapon_enchant", "armor_enchant", "accessory_enchant",
            "equipped_primordial_weapon_id", "equipped_primordial_armor_id", "equipped_primordial_accessory_id",
        )
        character = dict(zip(keys, row[:16]))
        weapon_affixes, armor_affixes, accessory_affixes = row[16], row[17], row[18]
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
        row = await self._fetchone(
            f"SELECT {', '.join(cols)} FROM character_backup WHERE user_id = %s", (user_id,)
        )
        if not row:
            return None
        return dict(zip(cols, row))

    async def swap_character_slot(self, user_id: int, new_class_key: str, starting_hp: int) -> None:
        cols = self._CHARACTER_SWAP_COLUMNS
        now = datetime.datetime.utcnow()
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute(
                        f"SELECT {', '.join(cols)} FROM characters WHERE user_id = %s FOR UPDATE", (user_id,)
                    )
                    current = await cur.fetchone()
                    if not current:
                        await conn.rollback()
                        raise ValueError(f"User {user_id} has no active character")

                    await cur.execute(
                        f"SELECT {', '.join(cols)} FROM character_backup WHERE user_id = %s FOR UPDATE",
                        (user_id,),
                    )
                    backup = await cur.fetchone()

                    col_list = ", ".join(cols)
                    placeholders = ", ".join(["%s"] * len(cols))
                    update_list = ", ".join(f"{c} = VALUES({c})" for c in cols)
                    await cur.execute(
                        f"INSERT INTO character_backup (user_id, {col_list}) VALUES (%s, {placeholders}) "
                        f"ON DUPLICATE KEY UPDATE {update_list}",
                        (user_id, *current),
                    )

                    if backup and backup[0] == new_class_key:
                        set_clause = ", ".join(f"{c} = %s" for c in cols)
                        await cur.execute(
                            f"UPDATE characters SET {set_clause} WHERE user_id = %s", (*backup, user_id)
                        )
                    else:
                        await cur.execute(
                            "UPDATE characters SET class_key = %s, level = 1, xp = 0, "
                            "equipped_weapon = NULL, equipped_armor = NULL, equipped_accessory = NULL, "
                            "wins = 0, losses = 0, current_hp = %s, hp_updated_at = %s, "
                            "weapon_enchant = 0, armor_enchant = 0, accessory_enchant = 0, "
                            "equipped_primordial_weapon_id = NULL, equipped_primordial_armor_id = NULL, "
                            "equipped_primordial_accessory_id = NULL "
                            "WHERE user_id = %s",
                            (new_class_key, starting_hp, now, user_id),
                        )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise

    async def set_character_level(self, user_id: int, level: int, xp: int) -> None:
        await self._execute(
            "UPDATE characters SET level = %s, xp = %s WHERE user_id = %s", (level, xp, user_id)
        )

    async def set_character_hp(self, user_id: int, hp: int, when: datetime.datetime) -> None:
        await self._execute(
            "UPDATE characters SET current_hp = %s, hp_updated_at = %s WHERE user_id = %s",
            (hp, when, user_id),
        )

    _EQUIP_COLUMNS = {
        "weapon": "equipped_weapon",
        "armor": "equipped_armor",
        "accessory": "equipped_accessory",
    }

    async def set_equipped(self, user_id: int, slot: str, item_key: str) -> None:
        column = self._EQUIP_COLUMNS[slot]
        await self._execute(
            f"UPDATE characters SET {column} = %s WHERE user_id = %s", (item_key, user_id)
        )

    _ENCHANT_COLUMNS = {
        "weapon": "weapon_enchant",
        "armor": "armor_enchant",
        "accessory": "accessory_enchant",
    }

    async def set_enchant_level(self, user_id: int, slot: str, level: int) -> None:
        column = self._ENCHANT_COLUMNS[slot]
        await self._execute(
            f"UPDATE characters SET {column} = %s WHERE user_id = %s", (level, user_id)
        )

    async def upgrade_enchant(self, user_id: int, slot: str, cost: int, new_level: int) -> int:
        column = self._ENCHANT_COLUMNS[slot]
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute(
                        "UPDATE users SET balance = balance - %s "
                        "WHERE user_id = %s AND balance >= %s",
                        (cost, user_id, cost),
                    )
                    if cur.rowcount == 0:
                        await conn.rollback()
                        raise InsufficientFunds(f"User {user_id} cannot afford an upgrade costing {cost}")
                    await cur.execute(
                        f"UPDATE characters SET {column} = %s WHERE user_id = %s",
                        (new_level, user_id),
                    )
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
                await cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
                row = await cur.fetchone()
                return row[0]

    _PRIMORDIAL_EQUIP_COLUMNS = {
        "weapon": "equipped_primordial_weapon_id",
        "armor": "equipped_primordial_armor_id",
        "accessory": "equipped_primordial_accessory_id",
    }

    async def add_primordial_item(self, user_id: int, slot: str, affixes_json: str) -> int:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO primordial_items (user_id, slot, affixes) VALUES (%s, %s, %s)",
                    (user_id, slot, affixes_json),
                )
                return cur.lastrowid

    async def get_primordial_items(self, user_id: int) -> list[dict]:
        rows = await self._fetchall(
            "SELECT id, slot, affixes FROM primordial_items WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        return [{"id": r[0], "slot": r[1], "affixes": json.loads(r[2])} for r in rows]

    async def equip_primordial(self, user_id: int, slot: str, item_id: int) -> None:
        column = self._PRIMORDIAL_EQUIP_COLUMNS[slot]
        await self._execute(f"UPDATE characters SET {column} = %s WHERE user_id = %s", (item_id, user_id))

    async def unequip_primordial(self, user_id: int, slot: str) -> None:
        column = self._PRIMORDIAL_EQUIP_COLUMNS[slot]
        await self._execute(f"UPDATE characters SET {column} = NULL WHERE user_id = %s", (user_id,))

    async def get_boss_kills(self, user_id: int, dungeon_key: str) -> int:
        row = await self._fetchone(
            "SELECT kills FROM boss_kills WHERE user_id = %s AND dungeon_key = %s",
            (user_id, dungeon_key),
        )
        return row[0] if row else 0

    async def record_boss_kill(self, user_id: int, dungeon_key: str) -> None:
        await self._execute(
            "INSERT INTO boss_kills (user_id, dungeon_key, kills) VALUES (%s, %s, 1) AS new "
            "ON DUPLICATE KEY UPDATE kills = boss_kills.kills + new.kills",
            (user_id, dungeon_key),
        )

    async def total_boss_kills(self, user_id: int) -> int:
        row = await self._fetchone(
            "SELECT COALESCE(SUM(kills), 0) FROM boss_kills WHERE user_id = %s", (user_id,)
        )
        return row[0] if row else 0

    async def record_duel_result(self, winner_id: int, loser_id: int) -> None:
        await self._execute("UPDATE characters SET wins = wins + 1 WHERE user_id = %s", (winner_id,))
        await self._execute("UPDATE characters SET losses = losses + 1 WHERE user_id = %s", (loser_id,))

    async def top_arena(self, limit: int = 10) -> list[tuple[int, int, int]]:
        return await self._fetchall(
            "SELECT user_id, wins, losses FROM characters ORDER BY wins DESC LIMIT %s", (limit,)
        )


    async def get_rpg_inventory(self, user_id: int) -> list[tuple[str, int]]:
        return await self._fetchall(
            "SELECT item_key, quantity FROM rpg_equipment WHERE user_id = %s AND quantity > 0",
            (user_id,),
        )

    async def get_rpg_item_quantity(self, user_id: int, item_key: str) -> int:
        row = await self._fetchone(
            "SELECT quantity FROM rpg_equipment WHERE user_id = %s AND item_key = %s",
            (user_id, item_key),
        )
        return row[0] if row else 0

    async def add_rpg_item(self, user_id: int, item_key: str, quantity: int) -> None:
        await self._execute(
            "INSERT INTO rpg_equipment (user_id, item_key, quantity) VALUES (%s, %s, %s) AS new "
            "ON DUPLICATE KEY UPDATE quantity = rpg_equipment.quantity + new.quantity",
            (user_id, item_key, quantity),
        )

    async def remove_rpg_item(self, user_id: int, item_key: str, quantity: int) -> None:
        rowcount = await self._execute(
            "UPDATE rpg_equipment SET quantity = quantity - %s "
            "WHERE user_id = %s AND item_key = %s AND quantity >= %s",
            (quantity, user_id, item_key, quantity),
        )
        if rowcount == 0:
            raise InsufficientFunds(f"User {user_id} does not have {quantity}x {item_key}")


    async def reset_user(self, user_id: int, starting_balance: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await conn.begin()
                try:
                    await cur.execute(
                        "UPDATE users SET balance = %s, bank_balance = 0, last_daily = NULL, "
                        "protected_until = NULL WHERE user_id = %s",
                        (starting_balance, user_id),
                    )
                    await cur.execute("DELETE FROM inventory WHERE user_id = %s", (user_id,))
                    await cur.execute("DELETE FROM stats WHERE user_id = %s", (user_id,))
                    await cur.execute("DELETE FROM lottery_tickets WHERE user_id = %s", (user_id,))
                    await cur.execute("DELETE FROM cooldowns WHERE user_id = %s", (user_id,))
                    await cur.execute("DELETE FROM characters WHERE user_id = %s", (user_id,))
                    await cur.execute("DELETE FROM rpg_equipment WHERE user_id = %s", (user_id,))
                    await cur.execute("DELETE FROM boss_kills WHERE user_id = %s", (user_id,))
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
        await self.divorce(user_id)
