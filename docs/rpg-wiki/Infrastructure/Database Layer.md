# Database Layer

`database/db.py` — a single `Database` class wrapping an `aiomysql` connection pool.

- All balance-changing operations use atomic conditional `UPDATE ... WHERE balance >= amount`
  queries, or explicit transactions (`deposit_to_bank`, `transfer_balance`,
  `withdraw_marriage_bank`, etc.) so concurrent requests can't create or destroy money.
- Schema migrations are additive `ALTER TABLE ... ADD COLUMN` guarded by an
  `information_schema` existence check (MySQL has no `ADD COLUMN IF NOT EXISTS`, unlike MariaDB).
- Cooldowns (`try_consume_cooldown`) and the daily bonus (`claim_daily`) use a single atomic
  statement each to close check-then-act races from a command being fired twice at once.

`database/db_postgres.py` mirrors every method here 1:1 for Supabase/Postgres — see
[[Supabase Fallback]].

See [[Infrastructure Overview]].
