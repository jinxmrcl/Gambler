# Admin Commands

All require the Administrator permission.

- `/addmoney`, `/setbalance`, `/giveall` (bulk-adjusts every player's balance), `/resetuser`
  (fully wipes a player's economy + RPG data)
- `/restart` — restarts the bot process from within Discord (calls the same clean-shutdown
  path as a SIGTERM; pm2's `autorestart` brings it back up)
- `/rpgsetlevel`, `/rpggive` — RPG-specific level/gear administration

See [[../RPG Overview|RPG Overview]] and [[Admin Overview]].
