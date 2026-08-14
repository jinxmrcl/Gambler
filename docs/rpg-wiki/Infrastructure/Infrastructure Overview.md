# Infrastructure Overview

The non-gameplay plumbing that keeps the bot reliable.

- [[Database Layer]] — MySQL schema, atomic transactions, migrations
- [[Supabase Fallback]] — startup-only Postgres failover if MySQL is unreachable
- [[Rate Limiting]] — global + per-channel throttling for message edits and sends
- [[Hot Reload]] — live code reload during development
- [[Auto Updates]] — in-process git watcher that pulls and announces new commits
- [[Restart Announcements]] — crash/clean-shutdown detection
- [[Error Handling]] — friendly error messages for both slash and prefix commands
