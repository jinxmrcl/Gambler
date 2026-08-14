# Hustle: Work, Crime, Slut, Rob

Risk-based income commands, cooldowns persisted in the database (survive bot restarts):

- `/work` — low-risk small income, 60s cooldown
- `/crime` — bigger payout, chance of a fine, 900s cooldown
- `/slut` — same idea as crime with its own odds, 900s cooldown
- `/rob` — steal from another player, 1800s cooldown
  - target needs at least 100 gold to be worth robbing
  - 45% success chance; steals 10%-25%
    of the target's wallet balance
  - on failure, pays a 100-300 gold fine to the target
  - a [rob shield](Shop%20%26%20Inventory.md) or keeping money in the [bank](Bank.md) both protect against it

See [Economy Overview](Economy%20Overview.md).
