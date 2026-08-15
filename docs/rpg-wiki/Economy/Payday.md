# Payday 💰

Fully passive — no command. A background loop (`events/payday.py`) checks every 60s for any
user whose scheduled payday has arrived, credits a random amount (`PAYDAY_MIN_AMOUNT`-
`PAYDAY_MAX_AMOUNT`, default 100-10,000), then reschedules them for another random 6-24h out.
New users get an initial random schedule the first time they're seen. Announced in a single
configurable channel (`PAYDAY_CHANNEL_ID`), mentioning the winner — not a DM, since balance is
global across every server a user shares with the bot.

Reuses the existing `cooldowns` table (`action="payday"`) rather than a new one, so it works
identically whether the bot is running on MySQL or has fallen back to
[Supabase](../Infrastructure/Supabase%20Fallback.md). Announcements go through the global rate
limiter (see [Rate Limiting](../Infrastructure/Rate%20Limiting.md)) so a burst of simultaneous paydays can't spike
past Discord's bot-wide request limit.

See [Economy Overview](Economy%20Overview.md).
