import datetime

import aiomysql


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
        self.pool = await aiomysql.create_pool(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            db=self._db,
            autocommit=True,
            minsize=1,
            maxsize=10,
        )
        await self._init_tables()

    async def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
            await self.pool.wait_closed()

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

    # -- Wallet -----------------------------------------------------------

    async def ensure_user(self, user_id: int, starting_balance: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT IGNORE INTO users (user_id, balance) VALUES (%s, %s)",
                    (user_id, starting_balance),
                )

    async def get_balance(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
                row = await cur.fetchone()
                return row[0] if row else 0

    async def update_balance(self, user_id: int, delta: int) -> int:
        """Atomically applies a balance delta. Raises InsufficientFunds if it would go negative."""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET balance = balance + %s "
                    "WHERE user_id = %s AND balance + %s >= 0",
                    (delta, user_id, delta),
                )
                if cur.rowcount == 0:
                    raise InsufficientFunds(f"User {user_id} cannot afford a change of {delta}")
                await cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
                row = await cur.fetchone()
                return row[0]

    async def set_balance(self, user_id: int, amount: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE users SET balance = %s WHERE user_id = %s", (amount, user_id))

    async def get_last_daily(self, user_id: int) -> datetime.datetime | None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT last_daily FROM users WHERE user_id = %s", (user_id,))
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_last_daily(self, user_id: int, when: datetime.datetime) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET last_daily = %s WHERE user_id = %s", (when, user_id)
                )

    async def top_balances(self, limit: int = 10) -> list[tuple[int, int]]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT %s",
                    (limit,),
                )
                return await cur.fetchall()

    # -- Bank ---------------------------------------------------------------

    async def get_bank_balance(self, user_id: int) -> int:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT bank_balance FROM users WHERE user_id = %s", (user_id,))
                row = await cur.fetchone()
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
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT protected_until FROM users WHERE user_id = %s", (user_id,))
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_protected_until(self, user_id: int, when: datetime.datetime) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET protected_until = %s WHERE user_id = %s", (when, user_id)
                )

    # -- Inventory ------------------------------------------------------------

    async def get_inventory(self, user_id: int) -> list[tuple[str, int]]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT item_key, quantity FROM inventory WHERE user_id = %s AND quantity > 0",
                    (user_id,),
                )
                return await cur.fetchall()

    async def get_item_quantity(self, user_id: int, item_key: str) -> int:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT quantity FROM inventory WHERE user_id = %s AND item_key = %s",
                    (user_id, item_key),
                )
                row = await cur.fetchone()
                return row[0] if row else 0

    async def add_item(self, user_id: int, item_key: str, quantity: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO inventory (user_id, item_key, quantity) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)",
                    (user_id, item_key, quantity),
                )

    async def remove_item(self, user_id: int, item_key: str, quantity: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE inventory SET quantity = quantity - %s "
                    "WHERE user_id = %s AND item_key = %s AND quantity >= %s",
                    (quantity, user_id, item_key, quantity),
                )
                if cur.rowcount == 0:
                    raise InsufficientFunds(f"User {user_id} does not have {quantity}x {item_key}")

    # -- Stats ------------------------------------------------------------------

    async def record_game_result(self, user_id: int, wagered: int, payout: int) -> None:
        net = payout - wagered
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
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
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO stats (user_id, robs_attempted, robs_succeeded) VALUES (%s, 1, %s) "
                    "ON DUPLICATE KEY UPDATE "
                    "robs_attempted = robs_attempted + 1, "
                    "robs_succeeded = robs_succeeded + VALUES(robs_succeeded)",
                    (user_id, 1 if success else 0),
                )

    async def record_robbed(self, user_id: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO stats (user_id, times_robbed) VALUES (%s, 1) "
                    "ON DUPLICATE KEY UPDATE times_robbed = times_robbed + 1",
                    (user_id,),
                )

    async def get_stats(self, user_id: int) -> dict:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT games_played, total_wagered, total_won, biggest_win, "
                    "robs_attempted, robs_succeeded, times_robbed FROM stats WHERE user_id = %s",
                    (user_id,),
                )
                row = await cur.fetchone()
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

    # -- Admin ------------------------------------------------------------------

    async def reset_user(self, user_id: int, starting_balance: int) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET balance = %s, bank_balance = 0, last_daily = NULL, "
                    "protected_until = NULL WHERE user_id = %s",
                    (starting_balance, user_id),
                )
                await cur.execute("DELETE FROM inventory WHERE user_id = %s", (user_id,))
                await cur.execute("DELETE FROM stats WHERE user_id = %s", (user_id,))
