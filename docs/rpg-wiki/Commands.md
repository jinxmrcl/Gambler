# Commands

## Character
- `/rpgstart` — create your character (pick a [class](RPG%20Overview.md#classes))
- `/character` — view your sheet
- `/classes` — list all classes
- `/heal` — pay gold to restore HP / revive
- `/rpgswitchclass <class>` — switch to your other class, or unlock a second one (exactly 2 total). Both classes' level, XP, gear, and Primordial items are kept fully separate — switching back and forth never loses progress on either.

## Dungeons
- `/dungeons` — list all [dungeons](RPG%20Overview.md#dungeons-in-level-order)
- `/dungeon` — fight a regular monster, no cooldown (add `team: True` to open a [team-fight](Combat%20System.md#team-fights) lobby)
- `/dungeonboss` — challenge a dungeon's [boss](RPG%20Overview.md#bosses), no cooldown (add `team: True` for a team fight)
- `/idle <dungeon> [minutes=30]` — auto-farms that dungeon's regular monsters and its boss in the background for up to 120 minutes, then delivers one final summary — no per-fight spam. The summary is always posted as a fresh, pinging message in the channel `/idle` was run in (never an edit — Discord invalidates the command's reply token after 15 minutes, so editing the original message can't be relied on for a run this long), and includes fight/boss win counts, a per-monster kill breakdown, total gold and XP earned, any level-up, and any loot — you also get pinged with the same results in the tracker channel (`IDLE_ANNOUNCE_CHANNEL_ID`). Progress and the remaining deadline are saved to the database every farming tick, so a hot-reload or restart pauses the run rather than losing it — it silently picks back up (still counting down toward the original end time) the next time the bot comes online, with no interrupted/partial message shown for that. A separate tracker message in that channel lists everyone currently idle farming, updates as sessions start/finish, and reposts itself (rather than editing forever) once it's over 12 hours old

## Shop
- `/rpgshop` — browse [gear](Equipment%20%26%20Upgrades.md) and [potions](Consumables.md)
- `/rpgbuy`, `/rpgequip`, `/rpguse`, `/rpgsell`, `/rpgupgrade`, `/rpginventory`
- `/rpgautoupgrade` — repeatedly upgrades your equipped gear (cheapest slot first) until every slot is maxed or you can't afford the next level
- `/rpgautobuy` — buys and equips the gear tier recommended for your current level in each slot (skipping any slot that's already at or above that tier, or has a Primordial item equipped)
- `/rpgequipprimordial <item_id>` — equip a [✨ Primordial](Equipment%20Tiers/Primordial%20Tier.md) item you own by its ID (shown in `/rpginventory`)
- `/rpgunequipprimordial <slot>` — revert a slot back to your regular gear

## PvP
- `/duel` — challenge another player (always full HP, see [Combat System](Combat%20System.md))
- `/arena` — leaderboard
