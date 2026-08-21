# Admin Commands

All require the Administrator permission.

- `/addmoney`, `/setbalance`, `/giveall` (bulk-adjusts every player's balance), `/resetuser`
  (clears a player's bank savings in the current server only)
- `/permcooldown <user> <enabled>` — toggle a permanent bypass of `work`/`crime`/`slut`/`rob`/`duel` cooldowns for one player
- `/permshield <user> <enabled>` — toggle permanent `rob` immunity, reusing the same `protected_until` mechanism as the shop-bought [Rob Shield](../Economy/Shop%20%26%20Inventory.md) (never shrinks a longer shop-bought shield the player already has; toggling off only clears it if it's still the permanent marker)
- `/botstatus` — gateway latency, gateway rate-limit state, and the current [rate limiter](../Infrastructure/Rate%20Limiting.md)'s live edit/send token levels
- `/restart` — restarts the bot process from within Discord (calls the same clean-shutdown
  path as a SIGTERM; pm2's `autorestart` brings it back up)
- `/announce <message>` — posts an announcement to the configured updates channel
- `/rpgsetlevel`, `/rpggivexp` (grants RPG XP directly, applying level-ups automatically), `/rpggive` (equipment/potions, including the [Paladin-only shield slot](../Equipment%20%26%20Upgrades.md) — item choices use autocomplete rather than a fixed dropdown since the combined equipment+potion catalog is over Discord's 25-choice static limit)
- `/rpggiveprimordial <user> <slot>` — spawns a freshly-rolled [✨ Primordial](../Equipment%20Tiers/Primordial%20Tier.md) item straight to a player, bypassing the normal high-end-boss-only drop

The [Level System](../Level%20System.md) has its own separate admin commands
(`/level-givexp`, `/level-boost`, `/level-boost-clear`) — see that page.

See [RPG Overview](../RPG%20Overview.md) and [Admin Overview](Admin%20Overview.md).
