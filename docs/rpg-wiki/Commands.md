# Commands

## Character
- `/rpgstart` — create your character (pick a [class](RPG%20Overview.md#classes))
- `/character` — view your sheet
- `/classes` — list all classes
- `/heal` — pay gold to restore HP / revive

## Dungeons
- `/dungeons` — list all [dungeons](RPG%20Overview.md#dungeons-in-level-order)
- `/dungeon` — fight a regular monster (add `team: True` to open a [team-fight](Combat%20System.md#team-fights) lobby)
- `/dungeonboss` — challenge a dungeon's [boss](RPG%20Overview.md#bosses) (add `team: True` for a team fight)
- `/idle <dungeon> [minutes=30]` — auto-farms that dungeon's regular monsters (and attempts its boss whenever the boss cooldown is up) in the background for up to 120 minutes, then edits its message once with a final summary — no per-fight spam

## Shop
- `/rpgshop` — browse [gear](Equipment%20%26%20Upgrades.md) and [potions](Consumables.md)
- `/rpgbuy`, `/rpgequip`, `/rpguse`, `/rpgsell`, `/rpgupgrade`, `/rpginventory`
- `/rpgautoupgrade` — repeatedly upgrades your equipped gear (cheapest slot first) until every slot is maxed or you can't afford the next level
- `/rpgequipprimordial <item_id>` — equip a [✨ Primordial](Equipment%20Tiers/Primordial%20Tier.md) item you own by its ID (shown in `/rpginventory`)
- `/rpgunequipprimordial <slot>` — revert a slot back to your regular gear

## PvP
- `/duel` — challenge another player (always full HP, see [Combat System](Combat%20System.md))
- `/arena` — leaderboard
