<div align="center">

![Economy Bot](assets/economy_bot_banner_1.png)

![discord.py](https://img.shields.io/badge/discord.py-2.6%2B-5865F2?logo=discord&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![Components V2](https://img.shields.io/badge/UI-Components%20V2-57F287)
![Multi--guild](https://img.shields.io/badge/servers-unlimited-2B2D31)
[![Discord](https://img.shields.io/badge/Discord-Join%20server-5865F2?logo=discord&logoColor=white)](https://discord.gg/P992BnNMbw)
[![Lines of Code](https://img.shields.io/endpoint?url=https%3A%2F%2Fghloc.vercel.app%2Fapi%2Fjinxmrcl%2FGambler%2Fbadge)](https://github.com/jinxmrcl/Gambler)

</div>

# Economy Bot

An open source economy bot for your Discord server, built with `discord.py`. At its core
is a full virtual economy (bank, shop, trading, marriage, weekly lottery, robbing, a
random passive Payday), layered with 14 casino games of chance and a from-scratch RPG
(9 classes, 16 dungeons, level 1-1500 with prestige) that shares the same wallet —
all backed by MySQL (or Postgres/Supabase).

## Table of contents

- [Features](#features)
- [Setup](#setup)
- [Deploying to a VPS](#deploying-to-a-vps)
- [Documentation](#documentation)
- [Commands](#commands)
- [Project structure](#project-structure)

## Features

**Casino Games** — 14 games against the house, plus a PvP duel:

- Blackjack (with Split), Mines (customizable grid), Hilo, Plinko, Limbo, Keno, Slots,
  Roulette, Dice, Baccarat, Horse Race, Scratchcard, Crash, Solo Coinflip (`/soloflip`)
- PvP `/coinflip` — challenge another player directly instead of the house
- Every game shares one fixed, transparent house edge (`HOUSE_EDGE` in
  `utils/economy.py`, default 3%) — Horse Race and Baccarat derive their odds by
  simulating the actual game rules rather than hand-picked numbers, and Crash reuses
  Limbo's exact crash-point formula
- Interactive games (Blackjack, Mines, Hilo, Keno, Scratchcard, Horse Race, Crash) use
  Discord's native buttons and select menus — Scratchcard is click-to-reveal tile by
  tile, Horse Race picks your horse from a dropdown after betting, and Crash lets you
  hit Cash Out live while the multiplier climbs
- Several (Blackjack, Slots, Horse Race, Baccarat, Crash) play out with a timed animated
  reveal instead of showing the result instantly
- Admins can set a Crash autoplay channel (`/set-crashchannel`) — once set, a new
  shared round starts automatically every minute, self-editing one live message
  through a countdown, the rocket climb, and the result, forever, with no manual
  play needed. Anyone can hit **Place Bet** during the countdown to enter an amount
  and join, the message lists everyone playing live, and each player hits their own
  **Cash Out** before it crashes
- Crash renders the climb as a small vertical rocket track (🚀 climbing a column of
  bars, like Horse Race's track but straight up) instead of just a number, ticks on
  a fixed real-time schedule so the pace stays steady, survives transient Discord
  API hiccups without dropping a round, and remembers its message across bot
  restarts instead of posting a new one
- The regular `/crash <bet>` command still works everywhere for a private, instant
  round outside of the autoplay channel
- Blackjack and Hilo render real playing cards via custom Discord emojis
  (`assets/cards/`, mapped in `utils/cards.py`) instead of plain text

**RPG** (`rpg/`, `commands/rpg_*.py`) — a full slash-only RPG sharing the same wallet as
the casino:
- 9 classes (Warrior, Mage, Rogue, Paladin, Necromancer, Ranger, Berserker, Monk, Druid),
  each with a unique active skill — Paladin's Divine Shield adds a genuine damage-absorption
  buffer (soaks a chunk of damage before real HP) on top of its heal
- `/rpgswitchclass` lets a player unlock and freely swap between exactly 2 classes, each
  with fully independent level/XP/gear/Primordial items — nothing is ever lost switching
  back and forth
- 16 dungeons spanning level 1-1500, each with a programmatically-scaled boss fight and
  its own per-dungeon difficulty curve (simulation-tuned so every class lands in a
  similar win-rate band at every tier, solo or in a team); the 5 highest-tier bosses each
  carry a unique special ability (Enrage or Double Strike) on top of their stats
- open team-fight lobbies (`team: True` on `/dungeon` / `/dungeonboss`) — anyone can join,
  the monster/boss scales up steeply with party size (deliberately harder than a flat
  split, so teaming up stays a real challenge), a win pays every member the full
  solo-equivalent reward, and anyone in the lobby can spend one potion to heal the whole
  party before the fight starts
- `/idle` auto-farms a dungeon (monsters + occasional boss attempts) in the background for
  up to 2 hours, quietly, with a single summary + ping at the end instead of per-fight spam
  (posted as a new message if the run outlasted Discord's 15-minute reply window) — a
  live-updated tracker message in a configurable channel lists everyone currently idle
  farming and reposts itself if it goes over 12 hours without refreshing
- prestige every 50 levels (up to prestige 29) once you hit the level cap, now with a small
  permanent stat bonus per tier (+0.5%, up to +14.5% at max prestige) on top of a smoother
  XP curve
- 3 equipment slots (weapon/armor/accessory) across 6 purchasable tiers (common → ancient)
  plus a 7th drop-only ✨ Primordial tier with randomly-rolled bonus affixes (lifesteal,
  crit damage, damage reflect, gold find, and more) exclusive to the 5 highest-tier
  bosses — split as a single roll across the party in a team fight rather than per member
- a gold-sink enchant/upgrade system per item — `/rpgautoupgrade` greedily maxes out
  whatever's equipped until you're out of gold, and `/rpgautobuy` buys/equips the gear
  tier recommended for your level in one click
- 3 consumable potions to heal mid-run, persistent HP with passive regen, and `/heal` to
  pay gold for an instant restore (also revives you at 0 HP)
- PvP `/duel` with a cooldown, and an `/arena` leaderboard of top duelists

**Economy** — a per-user virtual balance stored in MySQL, with:
- `daily` bonus, `work`/`crime`/`slut` for risk-based income, and `rob` to steal from others
- a passive **Payday**: every 1-24h (randomized per user), a random amount (100-10,000 by
  default) is announced in a configurable channel (`PAYDAY_CHANNEL_ID`) — no command
  needed; if several land in the same check cycle their announcements are staggered
  instead of firing all at once
- a `bank` to protect balance from being robbed
- a `shop` with items (rob shield, cooldown reset), plus `gift` and `trade` between players
- `marry`/`divorce` and a weekly `lottery` with an automatic prize draw
- `profile`/`stats` and multiple `leaderboard` variants (balance, games played, biggest
  win, most successful robberies)
- `cooldowns` to check your remaining cooldowns without triggering them
- admin commands to add, set, give-to-everyone, or reset a user's balance, grant RPG
  levels/items directly, and per-server `settings` to disable individual games or
  restrict them to specific channels

**Commands** — casino/economy commands are hybrid commands (work as both `/slash` and
`!prefix`); the RPG is slash-only for simplicity.

**UI** — built entirely with Discord's Components V2 (`Container`, `TextDisplay`,
`ActionRow`) instead of classic embeds, which requires `discord.py` 2.6 or newer.

**Infrastructure**:

- A global + per-channel rate limiter (`utils/ratelimit.py`), both congestion-aware —
  they throttle harder the more callers are waiting simultaneously, then relax back
  down — to avoid Discord API throttling on frequent message edits and sends
- Hot code reloading in development (`HOT_RELOAD=true`, picks up changes to
  `commands/`, `events/`, `rpg/`, `utils/`, and `database/` within ~1.5s, no restart)
- An in-process git watcher that checks `origin` every 60s and fast-forward-pulls any
  new commits, posting to the restart channel when one lands
- A Supabase/Postgres fallback database that only kicks in if MySQL can't be reached
  at bot startup
- An automated DB backup every 30-60 minutes — a full JSON snapshot of every table,
  written silently to `backups/` (gitignored) with the oldest pruned once more than 48
  accumulate; works against whichever backend (MySQL or the Postgres fallback) is
  currently active
- A shared error handler for every interactive button/menu (`discord.ui.View`), so a
  failed click gets logged and the player sees a friendly message instead of the
  interaction silently doing nothing
- Optional restart/crash health announcements to a bot-owner-configured channel
- Separately, a per-server `/set-updateschannel` posts a Components V2 Container
  listing whatever new commands/game modes were detected after an actual process
  restart (not on hot reload) — diffed against the previous run's command list, and
  distinct from both the git-pull watcher and the restart-health announcements above

---

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

   All required tables are created automatically on startup.

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
   | `DB_PASSWORD_FILE` | Optional path to a file holding the MySQL password (for Docker secrets) instead of `DB_PASSWORD` |
   | `SUPABASE_DB_URL` / `SUPABASE_DB_URL_FILE` | Optional Postgres/Supabase connection string (or a file holding one) — if set, the bot automatically falls back to it when MySQL is unreachable at startup |
   | `STARTING_BALANCE` | Starting balance for new players (default: 100000) |
   | `DAILY_AMOUNT` | Amount granted by the daily bonus (default: 500) |
   | `PAYDAY_MIN_AMOUNT` / `PAYDAY_MAX_AMOUNT` | Range for the random passive Payday payout every 1-24h (default: 100-10000) |
   | `PAYDAY_CHANNEL_ID` | Channel Payday payouts are announced in |
   | `HOT_RELOAD` | Auto-reload changed cogs/modules in development (default: `true`) |
   | `RESTART_LOG_CHANNEL_ID` | Optional channel ID for startup/crash/restart announcements |
   | `IDLE_ANNOUNCE_CHANNEL_ID` | Channel that shows a live-updated list of everyone currently `/idle` farming |

   In the Developer Portal, enable the **Message Content Intent** under **Bot** (required
   for text commands), and when inviting the bot, select the `bot` + `applications.commands`
   scopes along with sufficient permissions (Send Messages, Embed Links).

4. **Run the bot**

   ```bash
   python main.py
   ```

   On startup, all cogs in `commands/` and `events/` are loaded automatically and slash
   commands are synced with Discord.

---

## Deploying to a VPS

MySQL runs in Docker; the bot itself runs natively under [pm2](https://pm2.keymetrics.dev/)
so `git pull` + a pm2 restart is all a routine update needs. MySQL is bound to `127.0.0.1`
only — reachable from the bot process on the same VPS, never from the public internet.

1. Get the code onto the VPS (`git clone` this repo, or `scp` it over), install Docker
   and pm2 (Python deps are handled automatically — see below):

   ```bash
   curl -fsSL https://get.docker.com | sh
   npm install -g pm2
   ```

2. Create `.env` and generate the DB secret files:

   ```bash
   cp .env.example .env
   bash deploy/init_secrets.sh
   ```

   Fill in `DISCORD_TOKEN` in `.env`. The DB password itself is never stored in `.env` —
   `init_secrets.sh` generates `secrets/mysql_root_password.txt` and
   `secrets/db_password.txt` (gitignored), which `docker-compose.yml` reads directly via
   Docker secrets. Point `.env`'s `DB_PASSWORD_FILE` at the same `db_password.txt` path it
   printed, and set `DB_HOST=127.0.0.1`, `DB_USER=gambler_bot`, `DB_PORT=3306` — unless
   the VPS already has its own MySQL/MariaDB bound to port 3306 (`sudo ss -tlnp | grep
   3306` to check), in which case use `DB_PORT=3307` and update the port mapping in
   `docker-compose.yml` to `127.0.0.1:3307:3306` to match. Using the same file on both
   sides means the bot and MySQL can never end up with mismatched credentials.

3. Start MySQL:

   ```bash
   docker compose up -d mysql
   ```

4. Start the bot under pm2:

   ```bash
   bash deploy/install_pm2.sh
   ```

   This starts the bot as pm2 process `GamblerV2` (auto-restart on crash, daily restart at
   4am via `cron_restart`, see `deploy/ecosystem.config.js`), runs `pm2 save`, and posts a
   ✅/❌ status message to `RESTART_LOG_CHANNEL_ID` if it's set in `.env`. Run
   `pm2 startup` once afterward (and follow the printed command) so pm2 itself — and
   everything it manages — comes back up after a VPS reboot.

   On first run, `main.py` bootstraps its own `venv/` and installs `requirements.txt`
   into it automatically before importing anything third-party, then relaunches itself
   inside that venv — no manual `pip install` step needed, and later restarts are a
   no-op since the venv already exists.

Both MySQL (`restart: unless-stopped`) and the bot (pm2 `autorestart`) recover
automatically from a crash; pm2's `cron_restart` additionally restarts the bot process
daily at 4am. Useful commands: `pm2 status`, `pm2 logs GamblerV2`, `pm2 restart GamblerV2`.

---

## Documentation

A 92-note wiki at [`docs/rpg-wiki/`](docs/rpg-wiki) documents every system in the bot in
detail, generated from the bot's own live game data to stay accurate. Start at
[`Home.md`](docs/rpg-wiki/Home.md) — it's an [Obsidian](https://obsidian.md) vault, so
opening the `docs/rpg-wiki` folder in Obsidian gets you the full interlinked graph view,
but every note is plain Markdown and browsable directly on GitHub too.

| Section | Covers |
|---|---|
| [RPG Overview](docs/rpg-wiki/RPG%20Overview.md) | Classes, dungeons, bosses, equipment tiers, leveling & prestige (level 1-1500) |
| [Casino Games](docs/rpg-wiki/Casino%20Games/Casino%20Overview.md) | All 14 games of chance and their odds |
| [Economy](docs/rpg-wiki/Economy/Economy%20Overview.md) | Balance, daily, bank, hustling (work/crime/slut/rob) |
| [Social](docs/rpg-wiki/Social/Social%20Overview.md) | Marriage, trading, the weekly lottery |
| [Admin & Settings](docs/rpg-wiki/Admin%20%26%20Settings/Admin%20Overview.md) | Server configuration, moderation commands |
| [Infrastructure](docs/rpg-wiki/Infrastructure/Infrastructure%20Overview.md) | Database layer, rate limiting, hot reload, error handling |

---

## Commands

### Economy
- `balance [user]` — view balance
- `daily` — claim your daily bonus
- `leaderboard [board] [limit]` — leaderboard (`balance`, `games_played`,
  `total_wagered`, `biggest_win`, or `robs_succeeded`)
- `pay <user> <amount>` — transfer balance to another player

### Earning money (on cooldown)
- `work` — risk-free small income (cooldown: 30 min)
- `crime` — high payout possible, but risk of a fine (cooldown: 45 min)
- `slut` — same idea as `crime` with its own odds (cooldown: 45 min)
- `rob <user>` — try to steal balance from another player; pay a fine to the victim on
  failure (cooldown: 60 min, target needs at least 100 🪙, bank balance and an active
  `shield` protect against it)
- `cooldowns` — shows how long until your work/crime/slut/rob are ready again

### Bank
- `bank` — shows cash and bank balance
- `deposit <amount>` — move cash into the bank (number, `half`, or `all`)
- `withdraw <amount>` — move money from the bank back to cash (number, `half`, or `all`)

Money in the bank can't be stolen with `rob`.

### Shop, Inventory & Trading
- `shop` — shows purchasable items
- `buy <item> [quantity=1]` — buy an item (`shield` or `cooldown_reset`)
- `inventory` (alias `inv`) — shows your inventory
- `use <item>` — use an item (`shield` protects you from `rob` for 2h, `cooldown_reset`
  instantly resets work/crime/slut/rob) — each item can only be *used* up to 2x per
  rolling 24h, independent of how many you own
- `gift <user> <item> [quantity=1]` — gift an item to another player
- `trade <user> <give> <give_quantity> <want> <want_quantity>` — offer money or an item
  in exchange for money or an item from another player; they must accept

### Social
- `coinflip <user> <amount>` — challenge another player to a coinflip wager; they must
  accept before any balance changes hands
- `marry <user>` / `divorce` / `marriage [user]` — propose marriage, end it, or check
  someone's marriage status
- `lottery` / `lottery_buy <quantity>` — buy tickets for the weekly lottery; a winner is
  drawn automatically once the pot's countdown ends
- `lottery_setchannel` (Admin) — set the channel where lottery draw results are announced

### Statistics
- `profile [user]` (alias `stats`) — net worth, total wagered/won, biggest win, rob
  success rate, and how often you've been robbed

### Admin
Requires the **Administrator** permission on the server.
- `addmoney <user> <amount>` — add or (with a negative amount) remove balance
- `setbalance <user> <amount>` — set balance to an exact value
- `giveall <amount>` — give (or take) balance from every player at once
- `resetuser <user>` — reset a user's balance, bank, inventory, marriage, RPG character,
  and statistics
- `rpgsetlevel <user> <level> [xp=0]` — set a player's RPG level directly
- `rpggive <user> <item> [quantity=1]` — give a player a piece of equipment or a potion
  for free
- `rpggiveprimordial <user> <slot>` — spawn a freshly-rolled ✨ Primordial item straight
  to a player
- `restart` — restart the bot process
- `settings` — shows this server's disabled games and channel restrictions
- `togglegame <game> <enabled>` — enable or disable a specific game on this server
- `togglechannel <add|remove|clear>` — restrict games to specific channels
- `set-gamblechannel [channel] [clear]` — restrict the whole bot to one channel
  (admins are always exempt)
- `set-crashchannel [channel] [clear]` — run a shared, bettable Crash round every
  minute in a channel, self-editing through countdown/climb/result forever
- `set-updateschannel [channel] [clear]` — announce newly shipped commands/game modes
  here after a restart

### Misc
- `help` — interactive command browser with a category dropdown (economy, games, RPG,
  admin, etc.) instead of one long wall of text

### Games
All games accept the bet as a number, `all`, `half`, or a percentage (`50%`).

- `blackjack <bet>` — classic Blackjack with Hit/Stand/Double/Split buttons; cards are
  dealt, drawn, and the dealer's hand is revealed with an animated reveal instead of
  appearing instantly
- `mines <bet> [mines=3] [cols=5] [rows=4]` — customizable grid (2-5 cols, 2-5 rows —
  the full 5x5 unlocks up to 23 mines), avoid mines, cash out anytime
- `hilo <bet>` — guess higher/lower, multiplier grows with each correct card
- `plinko <bet> [risk=medium] [rows=12]` — drop a ball through the Plinko board
- `limbo <bet> <target>` — set a target multiplier (up to 1,000x), the random result
  must reach it
- `keno <bet> [picks=5]` — pick numbers and hope for hits in the draw
- `slots <bet>` — animated 3x3 grid with 5 paylines (rows + both diagonals); reels stop
  one column at a time before the result is revealed
- `roulette <bet> <choice>` — bet on a number, color, or even/odd
- `dice <bet> <prediction>` — predict the sum of two dice (2-12)
- `soloflip <bet> [call=heads]` (alias `cf`) — call heads or tails against the house
- `scratchcard <bet>` (alias `scratch`) — click each of the 9 tiles yourself to scratch
  it off; match 4 or more of the same symbol to win
- `horserace <bet>` (alias `horse`) — place your bet, then pick from 6 randomly-named
  horses in a dropdown (odds shown per horse, individually simulated: ~2.7x favorite up
  to ~40x longshot) and watch the animated race
- `baccarat <bet> <choice>` — bet on Player, Banker, or Tie; plays out the real casino
  drawing rules (natural 8/9, third-card rules for both hands) with an animated reveal
- `crash <bet>` — watch the multiplier climb in real time and hit **Cash Out** before it
  crashes; wait too long and you lose the bet entirely

All games share a 3% house edge (`HOUSE_EDGE` in `utils/economy.py`, or the standard
European single-zero odds for `roulette`), which scales payout multipliers to stay
mathematically fair while slightly favoring the house.

### RPG
Slash-only. Shares the same wallet (🪙) as the casino games.

- `rpgstart <class>` — create your character
- `classes` — shows the available RPG classes and their stats
- `character [user]` — shows a character sheet (level, gear, HP, boss kills)
- `heal` — pay gold to restore HP instantly (also revives you from 0 HP)
- `rpgswitchclass <class>` — switch to your other class, or unlock a second one (exactly
  2 total, free to swap between them); each keeps fully independent progress
- `dungeons` — shows the available dungeons and their level requirements
- `dungeon <name> [team=False]` — fight your way through a dungeon for gold and XP, no
  cooldown; with `team: True`, opens a public join lobby instead of fighting solo
- `dungeonboss <name> [team=False]` — challenge a dungeon's boss for bigger rewards, no
  cooldown; `team: True` opens a join lobby, scaling the boss to party size
- `idle <name> [minutes=30]` — auto-farms that dungeon (monsters + boss) in the
  background for up to 120 minutes, then posts one summary with a ping — no per-fight spam
- `rpgshop` — shows the equipment and potion shop
- `rpgbuy <item> [quantity=1]` — buy a piece of equipment or a potion
- `rpgequip <item>` — equip an owned weapon, armor, or accessory
- `rpguse <item>` — use a potion from your inventory
- `rpgsell <item> [quantity=1]` — sell an owned item back for gold
- `rpgupgrade <slot>` — spend gold to enchant your equipped gear in a slot
- `rpgautoupgrade` — repeatedly enchants your cheapest available equipped slot until
  everything's maxed or you're out of gold
- `rpgautobuy` — buys and equips the gear tier recommended for your level, per slot
- `rpgequipprimordial <item_id>` — equip a drop-only ✨ Primordial item by its id
- `rpgunequipprimordial <slot>` — revert a slot back to your regular gear
- `rpginventory` — shows your owned equipment, potions, and Primordial items
- `duel <user>` — challenge another player to a PvP duel (60s cooldown)
- `arena` — shows the top duelists

---

## Project structure

```
main.py                     Bot entry point, loads cogs, connects to MySQL, hot reload, restart announcements, git watcher, DB backups
database/db.py               aiomysql connection pool + wallet/bank/inventory/stats/social/RPG functions
utils/economy.py             Bet parsing, formatting, house edge constant, UI building blocks
utils/cards.py                Card deck + custom card emoji mapping for Blackjack & Hilo
assets/cards/                 Downloaded card emoji images (reference copies, not loaded at runtime)
utils/items.py                Shop catalog (item keys, prices, effects)
utils/checks.py               Per-server game enable/channel checks
utils/ratelimit.py            Global + per-channel, congestion-aware token-bucket limiters for edits/sends
commands/economy.py           balance, daily, leaderboard, pay
commands/hustle.py            work, crime, slut, rob
commands/bank.py              bank, deposit, withdraw
commands/shop.py              shop, buy, inventory, use, gift
commands/trade.py             trade
commands/coinflip.py          coinflip (PvP), soloflip (vs house)
commands/marriage.py          marry, divorce, marriage
commands/lottery.py           lottery, lottery_buy, lottery_setchannel (weekly background task)
commands/profile.py           profile / stats
commands/cooldowns.py         cooldowns
commands/admin.py             addmoney, setbalance, giveall, resetuser, restart, rpgsetlevel, rpggive, rpggiveprimordial
commands/settings.py          settings, togglegame, togglechannel, set-gamblechannel, set-crashchannel, set-updateschannel
commands/help.py              help
commands/blackjack.py         Blackjack
commands/mines.py             Mines
commands/hilo.py              Hilo
commands/plinko.py            Plinko
commands/limbo.py             Limbo
commands/keno.py              Keno
commands/slots.py             Slots
commands/roulette.py          Roulette
commands/dice.py              Dice
commands/scratchcard.py       Scratchcard
commands/horserace.py         Horse Race
commands/baccarat.py          Baccarat
commands/crash.py             Crash (with autonomous, self-editing autoplay channel)
commands/rpg_character.py     rpgstart, rpgswitchclass, classes, character, heal
commands/rpg_dungeon.py       dungeons, dungeon, dungeonboss (both with a team-fight lobby mode), idle
commands/rpg_shop.py          rpgshop, rpgbuy, rpgequip, rpguse, rpgsell, rpgupgrade, rpgautoupgrade, rpgautobuy, rpgequipprimordial, rpgunequipprimordial, rpginventory
commands/rpg_arena.py         duel, arena
rpg/classes.py                9 class definitions (stats + active skill)
rpg/combat.py                 Turn-based solo + team combat simulation, damage mitigation, class skills, boss abilities
rpg/monsters.py               16 dungeons, boss generation + abilities, level-scaling, party-size scaling
rpg/equipment.py              6 purchasable equipment tiers, 18 items, enchant/upgrade system
rpg/primordial.py             Drop-only 7th gear tier with randomly-rolled bonus affixes
rpg/consumables.py            3 healing potions
rpg/leveling.py               XP curve, prestige math + stat perks (level cap 1500)
rpg/character.py              Character dataclass helpers, full stat resolution (class + gear + Primordial + prestige)
rpg/badges.py                 Prestige badge rendering
rpg/events.py                 Random in-dungeon events
events/on_ready.py            Startup logging & presence
events/error_handler.py       Centralized error handling for text & slash commands, and every interactive view's buttons
events/payday.py              Background loop: random passive payday payout per user, announced in a channel
database/db_postgres.py       Postgres/Supabase implementation of the same DB interface (automatic fallback)
deploy/ecosystem.config.js    pm2 process config (autorestart, daily 4am cron_restart)
deploy/install_pm2.sh         Starts the bot under pm2, posts a startup status message
deploy/init_secrets.sh        Generates the gitignored MySQL secret files docker-compose.yml reads
docs/rpg-wiki/                Obsidian vault documenting every system, generated from live game data
```

---

## License

No license has been specified yet — all rights reserved by default until one is added.
