# Payday 💰

Fully passive — no command. A background loop (`events/payday.py`) checks every 60s whether
the next scheduled payday has arrived; when it has, it picks one random user (from everyone
who has ever used the bot) and credits them a random amount (`PAYDAY_MIN_AMOUNT`-
`PAYDAY_MAX_AMOUNT`, default 100-10,000), then reschedules the next payday for a random 2-4h
out. There's no per-user cooldown or fairness tracking — it's a single global "next payday"
timer, so exactly one payday can ever fire at a time and the same person can win again right
away. Announced in a single configurable channel (`PAYDAY_CHANNEL_ID`), mentioning the winner
— not a DM, since balance is global across every server a user shares with the bot.

Before crediting, the bot checks whether the winner is still a member of that channel's
server. If they've left, that firing is skipped (no credit, no announcement) and the next
payday timer still moves forward as normal — they're simply eligible to be picked again once
they rejoin.

See [Economy Overview](Economy%20Overview.md).
