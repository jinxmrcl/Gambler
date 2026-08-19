# Level System 📈

A per-server activity leveling system, separate from the [RPG](RPG%20Overview.md)'s own
character leveling — this one tracks how active a member is in the *Discord server
itself* (chatting, being in voice), not their RPG character.

## Earning XP

- **Messages**: 15-25 XP per eligible message, once per 60s per member (stops
  spam-farming). Bots never earn XP.
- **Voice**: checked once a minute — every non-bot member currently in a voice channel
  earns 6-10 XP for that minute, but only if there's at least one other non-bot member in
  the same channel, the member isn't deafened, and the channel isn't the server's
  configured AFK channel.
- Members holding any role listed in `BLACKLIST_ROLE_IDS` (comma-separated role IDs, see
  `utils/role_blacklist.py`) earn nothing at all from this system — no XP, no badges, no
  gold. The same blacklist is also checked by [Payday](Economy/Payday.md) before it picks
  a winner.

Leveling is intentionally slow — max level is 150, and it takes roughly **9-10 months**
of realistic activity (~30 messages + ~1h voice/day) or **~2-2.5 months** for a very
active member (~100 messages + ~5h voice/day) to reach it.

## Rewards

- **Gold** — `500 × new level`, paid straight into the normal economy balance (the same
  balance every casino game uses).
- **Badge** — every level from 1 to 150 has its own unique badge, shown next to the level
  number in `/level`, `/stats`, and the leaderboard.

A level-up posts an announcement in the channel the triggering message was sent in.
Voice-driven level-ups don't have a natural channel, so those apply their rewards
silently.

## Temporary XP boosts

`/level-boost <multiplier> <days>` (admin) multiplies XP gains (both message and voice)
server-wide for a set number of days — useful for events. `/level-boost-clear` ends one
early. Only one boost is active per server at a time.

## Commands

| Command | Who | What |
|---|---|---|
| `/level [user]` | everyone | Level, badge, and progress toward the next level |
| `/stats [user]` | everyone | All-time totals: XP breakdown (message vs. voice) and active VC time |
| `/level-leaderboard` | everyone | Top 10 by XP in the current server |
| `/level-badges` | everyone | Preview of the badge progression (every 10th level) |
| `/level-boost <multiplier> <days>` | admin | Temporary server-wide XP multiplier |
| `/level-boost-clear` | admin | End the active boost early |

## How it's built

- `commands/levels.py` — the cog: XP-gain listeners, level-up handling, all commands.
- `utils/level_math.py` — pure XP↔level curve math.
- `utils/level_badges.py` — loads `assets/level/manifest.json` and maps a level to its
  `<:emoji:id>` string, mirroring how [RPG prestige badges](RPG%20Overview.md) work.
- `utils/role_blacklist.py` — the shared `BLACKLIST_ROLE_IDS` set and `is_blacklisted()`
  check, used by both this system and Payday.
- Storage lives in the same MySQL/Postgres-fallback database as everything else —
  `level_xp` (per-guild, per-user XP with a message/voice breakdown and total voice
  seconds) and `level_boost` (the active multiplier, if any) — distinct table names from
  the rest of the schema, no collisions.

Badges were generated with `scripts/generate_level_badges.py` (Pillow, gitignored — not
part of the bot's runtime dependencies) and uploaded as Discord Application Emojis via
`scripts/upload_level_emojis.py`, the same mechanism the RPG's prestige badges use.

See [Economy Overview](Economy/Economy%20Overview.md) for how the gold reward fits into
the wider economy.
