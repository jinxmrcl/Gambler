import datetime
import logging

import aiomysql

log = logging.getLogger("gambler")


class InsufficientFunds(Exception):
    """Raised when a balance change would take a user's balance below zero."""


class Database:
    def __init__(self, host: str, port: int, user: str, password: str, db: str):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._db = db
        self.pool: aiomysql.Pool | None = None

    async def connect(self) -> None:
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
                pool_recycle=3600,  # recycle connections MySQL/proxies would otherwise drop silently
            )
        except Exception:
            log.exception(
                "Could not connect to MySQL at %s:%s (db=%s). Check DB_HOST/DB_PORT/DB_USER/"
                "DB_PASSWORD/DB_NAME in your .env.",
                self._host,
                self._port,
                self._db,
            )
            raise
        await self._init_tables()

    async def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
            await self.pool.wait_closed()

    # -- Low-level helpers --------------------------------------------------

    async def _execute(self, query: str, args: tuple = ()) -> int:
        """Runs a single statement outside any explicit transaction. Returns rowcount."""
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
                    CREATE TABLE IF NOT EXISTS marriages (
                        user_id BIGINT UNSIGNED PRIMARY KEY,
                        partner_id BIGINT UNSIGNED NOT NULL,
                        married_at DATETIME NOT NULL
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
                    CREATE TABLE IF NOT EXISTS cooldowns (
                        user_id BIGINT UNSIGNED NOT NULL,
                        action VARCHAR(16) NOT NULL,
                        expires_at DATETIME NOT NULL,
                        PRIMARY KEY (user_id, action)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                await cur.execute(
                    "INSERT IGNORE INTO lottery_state (id, pot, next_draw) VALUES (1, 0, %s)",
                    (datetime.datetime.utcnow() + datetime.timedelta(days=7),),
                )

    # -- Wallet -----------------------------------------------------------

    async def ensure_user(self, user_id: int, starting_balance: int) -> None:
        await self._execute(
            "INSERT IGNORE INTO users (user_id, balance) VALUES (%s, %s)",
            (user_id, starting_balance),
        )

    async def get_balance(self, user_id: int) -> int:
        row = await self._fetchone("SELECT balance FROM users WHERE user_id = %s", (user_id,))
        return row[0] if row else 0

    async def update_balance(self, user_id: int, delta: int) -> int:
        """Atomically applies a balance delta. Raises InsufficientFunds if it would go negative."""
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
        """Atomically moves `amount` from sender to recipient in one transaction.
        Raises InsufficientFunds if the sender can't afford it. Returns the sender's new balance."""
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
        """Atomically claims the daily bonus if the cooldown has elapsed.

        Returns the new balance, or None if the user is still on cooldown (no
        row is touched in that case, closing the check-then-act race a client
        could hit by firing the command twice at once)."""
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

    # -- Bank ---------------------------------------------------------------

    async def get_bank_balance(self, user_id: int) -> int:
        row = await self._fetchone("SELECT bank_balance FROM users WHERE user_id = %s", (user_id,))
        return row[0] if row else 0

    async def deposit_to_bank(self, user_id: int, amount: int) -> tuple[int, int]:
        """Moves `amount` from wallet balance to bank balance. Returns (balance, bank_balance)."""
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
        """Moves `amount` from bank balance to wallet balance. Returns (balance, bank_balance)."""
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

    # -- Rob protection -------------------------------------------------------

    async def get_protected_until(self, user_id: int) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT protected_until FROM users WHERE user_id = %s", (user_id,)
        )
        return row[0] if row else None

    async def set_protected_until(self, user_id: int, when: datetime.datetime) -> None:
        await self._execute(
            "UPDATE users SET protected_until = %s WHERE user_id = %s", (when, user_id)
        )

    # -- Cooldowns --------------------------------------------------------------

    async def get_cooldown(self, user_id: int, action: str) -> datetime.datetime | None:
        row = await self._fetchone(
            "SELECT expires_at FROM cooldowns WHERE user_id = %s AND action = %s",
            (user_id, action),
        )
        return row[0] if row else None

    async def set_cooldown(self, user_id: int, action: str, expires_at: datetime.datetime) -> None:
        await self._execute(
            "INSERT INTO cooldowns (user_id, action, expires_at) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE expires_at = VALUES(expires_at)",
            (user_id, action, expires_at),
        )

    async def try_consume_cooldown(
        self, user_id: int, action: str, period: datetime.timedelta, now: datetime.datetime
    ) -> bool:
        """Atomically claims `action` for `period` if it isn't already on cooldown.

        Returns True (and starts the cooldown) if the action was free; False if
        it's still on cooldown and nothing was changed. Doing the check and the
        write in one statement closes the race two near-simultaneous invocations
        of the same command would otherwise hit."""
        rowcount = await self._execute(
            "INSERT INTO cooldowns (user_id, action, expires_at) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "expires_at = IF(expires_at <= %s, VALUES(expires_at), expires_at)",
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

    # -- Inventory ------------------------------------------------------------

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
            "INSERT INTO inventory (user_id, item_key, quantity) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)",
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

    # -- Stats ------------------------------------------------------------------

    async def record_game_result(self, user_id: int, wagered: int, payout: int) -> None:
        net = payout - wagered
        await self._execute(
            "INSERT INTO stats (user_id, games_played, total_wagered, total_won, biggest_win) "
            "VALUES (%s, 1, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE "
            "games_played = games_played + 1, "
            "total_wagered = total_wagered + VALUES(total_wagered), "
            "total_won = total_won + VALUES(total_won), "
            "biggest_win = GREATEST(biggest_win, VALUES(biggest_win))",
            (user_id, wagered, payout, max(net, 0)),
        )

    async def record_rob_attempt(self, user_id: int, success: bool) -> None:
        await self._execute(
            "INSERT INTO stats (user_id, robs_attempted, robs_succeeded) VALUES (%s, 1, %s) "
            "ON DUPLICATE KEY UPDATE "
            "robs_attempted = robs_attempted + 1, "
            "robs_succeeded = robs_succeeded + VALUES(robs_succeeded)",
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

    # -- Leaderboards ------------------------------------------------------------

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

    # -- Guild settings ------------------------------------------------------------

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
                    "INSERT INTO guild_settings (guild_id, disabled_games) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE disabled_games = VALUES(disabled_games)",
                    (guild_id, ",".join(sorted(current_disabled))),
                )

    async def set_allowed_channels(self, guild_id: int, channels: set[int]) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO guild_settings (guild_id, allowed_channels) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE allowed_channels = VALUES(allowed_channels)",
                    (guild_id, ",".join(str(c) for c in sorted(channels))),
                )

    # -- Marriage ------------------------------------------------------------

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
                await cur.execute("DELETE FROM marriages WHERE user_id IN (%s, %s)", (user_id, partner_id))
        return partner_id

    # -- Lottery ------------------------------------------------------------

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
                        "INSERT INTO lottery_tickets (user_id, quantity) VALUES (%s, %s) "
                        "ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)",
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

    # -- Admin ------------------------------------------------------------------

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
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
        await self.divorce(user_id)
