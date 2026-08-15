# Admin Commands

All require the Administrator permission.

- `/addmoney`, `/setbalance`, `/giveall` (bulk-adjusts every player's balance), `/resetuser`
  (fully wipes a player's economy + RPG data)
- `/restart` — restarts the bot process from within Discord (calls the same clean-shutdown
  path as a SIGTERM; pm2's `autorestart` brings it back up)
- `/rpgsetlevel`, `/rpggive` — RPG-specific level/gear administration
- `/rpggiveprimordial <user> <slot>` — spawns a freshly-rolled [✨ Primordial](../Equipment%20Tiers/Primordial%20Tier.md) item straight to a player, bypassing the normal high-end-boss-only drop

See [RPG Overview](../RPG%20Overview.md) and [Admin Overview](Admin%20Overview.md).
