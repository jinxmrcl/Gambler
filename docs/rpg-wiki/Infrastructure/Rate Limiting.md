# Rate Limiting

`utils/ratelimit.py` — two layered token buckets, both congestion-aware (the more callers are
simultaneously waiting on a bucket, the more its effective rate throttles down, to a floor of
30% of normal — then relaxes back once the spike clears):

- **Per-channel** (3 requests per 5s per channel) — `limited_edit()`, since Discord rate-limits
  message edits per-channel. Used by [Slots](../Casino%20Games/Slots.md)' spin animation and every
  game's timeout-driven message edit, so a burst of edits in one channel can't trip a 429.
- **Global** (45 requests/second bot-wide, under Discord's hard 50/s ceiling) — every
  `limited_edit()` call acquires this too, and a separate `limited_send()` applies it to message
  sends (currently used by [Payday](../Economy/Payday.md)'s announcements), so total bot-wide
  traffic across every simultaneous game session stays under the cap even if per-channel limits
  alone wouldn't catch it.

See [Infrastructure Overview](Infrastructure%20Overview.md).
