# Infrastructure Overview

The non-gameplay plumbing that keeps the bot reliable.

- [Database Layer](Database%20Layer.md) — MySQL schema, atomic transactions, migrations
- [Supabase Fallback](Supabase%20Fallback.md) — startup-only Postgres failover if MySQL is unreachable
- [Rate Limiting](Rate%20Limiting.md) — global + per-channel throttling for message edits and sends
- [Hot Reload](Hot%20Reload.md) — live code reload during development
- [Auto Updates](Auto%20Updates.md) — in-process git watcher that pulls and announces new commits
- [Restart Announcements](Restart%20Announcements.md) — crash/clean-shutdown detection
- [Error Handling](Error%20Handling.md) — friendly error messages for both slash and prefix commands
