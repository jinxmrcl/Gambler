# Rate Limiting

`utils/ratelimit.py` — a per-channel token-bucket limiter (3 requests per
5s per channel), since Discord rate-limits message edits per-channel rather than
against the bot-wide global limit. Used by [[../Casino Games/Slots|Slots]]' spin animation and
every game's timeout-driven message edit, so a burst of edits in one channel can't trip a 429.

See [[Infrastructure Overview]].
