<div align="center">

![Ticket Tool](assets/gambling_bot_banner_1.png)

![discord.py](https://img.shields.io/badge/discord.py-2.6%2B-5865F2?logo=discord&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![Components V2](https://img.shields.io/badge/UI-Components%20V2-57F287)
![Multi--guild](https://img.shields.io/badge/servers-unlimited-2B2D31)
[![Discord](https://img.shields.io/badge/Discord-Join%20server-5865F2?logo=discord&logoColor=white)](https://discord.gg/P992BnNMbw)

</div>

# Gambler

A Discord economy & gambling bot built with `discord.py`, featuring six casino games,
a full virtual economy (bank, shop, robbing), and MySQL-backed persistence.

📊 **~2,100 lines of Python** across 22 files.

## Features

**Games** — Blackjack, Mines, Hilo, Plinko, Limbo, Keno. All games are mathematically
fair with a fixed, transparent house edge (`HOUSE_EDGE` in `utils/economy.py`, default 3%),
and interactive ones (Blackjack, Mines, Hilo, Keno) use Discord's native buttons and
select menus.

**Economy** — a per-user virtual balance stored in MySQL, with:
- `daily` bonus, `work`/`crime`/`slut` for risk-based income, and `rob` to steal from others
- a `bank` to protect balance from being robbed
- a `shop` with items (rob shield, cooldown reset) and a `gift` command
- `profile`/`stats` tracking wagered/won amounts, biggest win, and rob success rate
- admin commands to add, set, or reset a user's balance

**Commands** — every command is a hybrid command: it works as both a slash command
(`/blackjack`) and a prefix command (`!blackjack`), with no code duplication.

**UI** — built entirely with Discord's Components V2 (`Container`, `TextDisplay`,
`ActionRow`) instead of classic embeds, which requires `discord.py` 2.6 or newer.

## Setup

1. **Install dependencies**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Create a MySQL database**

   ```sql
   CREATE DATABASE gambler CHARACTER SET utf8mb4;
   ```

   The required tables (`users`, `inventory`, `stats`) are created automatically on startup.

3. **Configure `.env`**

   Copy `.env.example` to `.env` and fill it in:

   ```bash
   cp .env.example .env
   ```

   | Variable | Description |
   |---|---|
   | `DISCORD_TOKEN` | Bot token from the [Discord Developer Portal](https://discord.com/developers/applications) |
   | `PREFIX` | Prefix for text commands (default: `!`) |
   | `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | MySQL credentials |
   | `STARTING_BALANCE` | Starting balance for new players (default: 1000) |
   | `DAILY_AMOUNT` | Amount granted by the daily bonus (default: 500) |

   In the Developer Portal, enable the **Message Content Intent** under **Bot** (required
   for text commands), and when inviting the bot, select the `bot` + `applications.commands`
   scopes along with sufficient permissions (Send Messages, Embed Links).

4. **Run the bot**

   ```bash
   python main.py
   ```

   On startup, all cogs in `commands/` and `events/` are loaded automatically and slash
   commands are synced with Discord.

## Commands

### Economy
- `balance [user]` — view balance
- `daily` — claim your daily bonus
- `leaderboard [limit]` — richest players
- `pay <user> <amount>` — transfer balance to another player

### Earning money (on cooldown)
- `work` — risk-free small income (cooldown: 30 min)
- `crime` — high payout possible, but risk of a fine (cooldown: 45 min)
- `slut` — same idea as `crime` with its own odds (cooldown: 45 min)
- `rob <user>` — try to steal balance from another player; pay a fine to the victim on
  failure (cooldown: 60 min, target needs at least 100 🪙, bank balance and an active
  `shield` protect against it)

### Bank
- `bank` — shows cash and bank balance
- `deposit <amount>` — move cash into the bank (number, `half`, or `all`)
- `withdraw <amount>` — move money from the bank back to cash (number, `half`, or `all`)

Money in the bank can't be stolen with `rob`.

### Shop & Inventory
- `shop` — shows purchasable items
- `buy <item> [quantity=1]` — buy an item (`shield` or `cooldown_reset`)
- `inventory` (alias `inv`) — shows your inventory
- `use <item>` — use an item (`shield` protects you from `rob` for 2h, `cooldown_reset`
  instantly resets work/crime/slut/rob)
- `gift <user> <item> [quantity=1]` — gift an item to another player

### Statistics
- `profile [user]` (alias `stats`) — net worth, total wagered/won, biggest win, rob
  success rate, and how often you've been robbed

### Admin
Requires the **Administrator** permission on the server.
- `addmoney <user> <amount>` — add or (with a negative amount) remove balance
- `setbalance <user> <amount>` — set balance to an exact value
- `resetuser <user>` — reset a user's balance, bank, inventory, and statistics

### Misc
- `help` — overview of all commands

### Games
All games accept the bet as a number, `all`, `half`, or a percentage (`50%`).

- `blackjack <bet>` — classic Blackjack with Hit/Stand/Double buttons
- `mines <bet> [mines=3]` — 5×4 grid, avoid mines, cash out anytime
- `hilo <bet>` — guess higher/lower, multiplier grows with each correct card
- `plinko <bet> [risk=medium] [rows=12]` — drop a ball through the Plinko board
- `limbo <bet> <target>` — set a target multiplier, the random result must reach it
- `keno <bet> [picks=5]` — pick numbers and hope for hits in the draw

All games share a 3% house edge (`HOUSE_EDGE` in `utils/economy.py`), which scales
payout multipliers to stay mathematically fair while slightly favoring the house.

## Project structure

```
main.py                 Bot entry point, loads cogs, connects to MySQL
database/db.py           aiomysql connection pool + wallet/bank/inventory/stats functions
utils/economy.py         Bet parsing, formatting, house edge constant, UI building blocks
utils/cards.py            Card deck for Blackjack & Hilo
utils/items.py            Shop catalog (item keys, prices, effects)
commands/economy.py       balance, daily, leaderboard, pay
commands/hustle.py         work, crime, slut, rob
commands/bank.py           bank, deposit, withdraw
commands/shop.py           shop, buy, inventory, use, gift
commands/profile.py        profile / stats
commands/admin.py          addmoney, setbalance, resetuser
commands/help.py           help
commands/blackjack.py     Blackjack
commands/mines.py         Mines
commands/hilo.py          Hilo
commands/plinko.py        Plinko
commands/limbo.py         Limbo
commands/keno.py          Keno
events/on_ready.py        Startup logging & presence
events/error_handler.py   Centralized error handling for text & slash commands
```

## License

No license has been specified yet — all rights reserved by default until one is added.
