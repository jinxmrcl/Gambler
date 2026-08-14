# Infrastructure Overview

The non-gameplay plumbing that keeps the bot reliable.

- [[Database Layer]] — MySQL schema, atomic transactions, migrations
- [[Rate Limiting]] — per-channel throttling for message edits
- [[Hot Reload]] — live code reload during development
- [[Restart Announcements]] — crash/clean-shutdown detection
- [[Error Handling]] — friendly error messages for both slash and prefix commands
