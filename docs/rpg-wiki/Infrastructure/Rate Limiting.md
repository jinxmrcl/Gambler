# Rate Limiting

`utils/ratelimit.py` — three layered token buckets, all congestion-aware (the more callers
are simultaneously waiting on a bucket, the more its effective rate throttles down toward a
floor — then relaxes back once the spike clears). Every `limited_edit()` call acquires all
three, in order, before the real Discord API call:

- **Global edit** (20 requests/second bot-wide, floor 80% under contention) — caps total
  message-edit traffic across every simultaneous game session.
- **Per-channel** (3 requests per 5s per channel, floor 30% under contention) — Discord
  rate-limits message edits per-channel, so this stops a burst of edits in one busy channel
  (e.g. many games running in the same gamble channel) from tripping a 429 even if the
  global budget has room.
- **Per-message** (1 edit per 1.1s per exact message ID, no further throttling under
  contention — a fixed floor) — stops concurrent edits to the *same* message (e.g. the idle
  tracker, or a shared auto-round message) from bursting past what Discord allows for that
  one resource, regardless of how many different callers are racing to update it.

`limited_send()` (new messages, not edits) only goes through its own **global send** bucket
(8 requests/second, floor 15% under contention) — sends aren't bucketed per-channel by
Discord the same way edits are, so no per-channel layer is needed there.

This is a *pre-throttle* on top of discord.py's own built-in per-route bucket handling
(which still applies to every request regardless, including ones that don't go through
`limited_edit`/`limited_send`) — it exists for known-hot paths (game animations, the idle
tracker, Payday announcements) where waiting for Discord to react after the fact isn't
tight enough.

`/botstatus` (admin) surfaces the live state of all this — gateway latency,
`is_ws_ratelimited()`, and the current global edit/send token levels — so rate-limit health
is observable instead of only showing up as warnings in the logs.

See [Infrastructure Overview](Infrastructure%20Overview.md).
