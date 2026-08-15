# Supabase Fallback

`database/db_postgres.py` — a `PostgresDatabase` class that mirrors `Database` (see
[Database Layer](Database%20Layer.md)) method-for-method: same public methods, same signatures, same
`InsufficientFunds` exception, so calling code never needs to know which backend is active.

Used only as a **startup-only failover**: `main.py`'s `setup_hook` tries MySQL first (with its
own retry loop); only if that's fully exhausted does it construct and connect a
`PostgresDatabase` instead for the rest of that run. It never switches mid-session, so a single
player's balance can never end up split across both databases.

Built on `asyncpg` against a real Postgres connection (direct or Supabase's transaction-mode
pooler — `statement_cache_size=0` is set specifically so the pooler works, since transaction
pooling breaks asyncpg's normal per-connection prepared-statement cache). Every query was
hand-translated from MySQL syntax: `ON DUPLICATE KEY UPDATE` → `ON CONFLICT ... DO UPDATE`,
`%s` → `$1`/`$2` placeholders, manual `BEGIN`/`COMMIT` → `async with conn.transaction()`.

Credentials never live in `.env` as literal values — `SUPABASE_DB_URL_FILE` points at a
gitignored secret file instead, same pattern as `DB_PASSWORD_FILE` for MySQL.

See [Infrastructure Overview](Infrastructure%20Overview.md).
