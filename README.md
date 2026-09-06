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
(9 classes, 16 dungeons, level 1-1500 with prestige) that shares the same wallet — every
server the bot joins gets its own fully isolated SQLite database, so balances, RPG
progress, inventories, and everything else are completely independent from server to
server, with an optional periodic off-site backup to Postgres/Supabase.

## Table of contents

- [Features](#features)
- [Setup](#setup)
- [Deploying to a VPS](#deploying-to-a-vps)
- [Documentation](#documentation)
- [Commands](#commands)
- [Project structure](#project-structure)

## Features

**Casino Games** — 13 games against the house, plus a PvP duel:

- Blackjack (with Split), Mines (customizable grid), Hilo, Plinko, Limbo, Keno, Slots,
  Roulette, Dice, Baccarat, Horse Race, Scratchcard, Solo Coinflip (`/soloflip`)
- PvP `/coinflip` — challenge another player directly instead of the house
- Every game shares one fixed, transparent house edge (`HOUSE_EDGE` in
  `utils/economy.py`, default 3%) — Horse Race and Baccarat derive their odds by
  simulating the actual game rules rather than hand-picked numbers
- Interactive games (Blackjack, Mines, Hilo, Keno, Scratchcard, Horse Race) use
  Discord's native buttons and select menus — Scratchcard is click-to-reveal tile by
  tile, Horse Race picks your horse from a dropdown after betting
- Several (Blackjack, Slots, Horse Race, Baccarat) play out with a timed animated
  reveal instead of showing the result instantly
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
  up to 2 hours, quietly, with a single summary + ping (including a per-monster/boss kill
  breakdown) sent back to the channel `/idle` was called from once the timer's up. An `auto`
  toggle switches to running indefinitely instead — 60-minute checkpoints (a non-pinging
  progress summary each hour, counters reset after each one) forever, until `/idle` is run
  again to stop it and deliver a final pinging summary of whatever accumulated since the
  last checkpoint — progress and the remaining/checkpoint time are saved every tick, so a
  hot-reload or restart just pauses the run silently and it resumes on its own next time the
  bot is up, still counting toward the original end (or next checkpoint) time — a separate
  tracker message in a configurable channel lists everyone currently idle farming, refreshes
  on a 1-minute timer plus whenever someone starts or finishes (debounced so a burst of
  events — e.g. many sessions resuming at once after a
  restart — collapses into a single edit), and reposts itself if it goes over 12 hours
  without refreshing
- prestige every 50 levels (up to prestige 29) once you hit the level cap, now with a small
  permanent stat bonus per tier (+0.5%, up to +14.5% at max prestige) on top of a smoother
  XP curve
- 3 equipment slots (weapon/armor/accessory) across 6 purchasable tiers (common → ancient)
  plus a 7th drop-only ✨ Primordial tier with randomly-rolled bonus affixes (lifesteal,
  crit damage, damage reflect, gold find, and more) exclusive to the 5 highest-tier
  bosses — split as a single roll across the party in a team fight rather than per member
- a 4th slot, shields, exclusive to Paladins across the same 6 tiers — each shield grants
  both flat damage reduction and a chance to fully block a hit, distinct mechanics from
  what armor already provides, stacking with Paladin's own Divine Shield skill
- a gold-sink enchant/upgrade system per item — `/rpgautoupgrade` greedily maxes out
  whatever's equipped until you're out of gold, and `/rpgautobuy` buys/equips the gear
  tier recommended for your level in one click
- 3 consumable potions to heal mid-run, persistent HP with passive regen, and `/heal` to
  pay gold for an instant restore (also revives you at 0 HP)
- PvP `/duel` with a cooldown, and an `/arena` leaderboard of top duelists

**Economy** — a per-user virtual balance stored in that server's own database, with:
- `daily` bonus with a consecutive-day streak: +10% per day claimed on time, up to +100%
  at a 10-day streak; missing a day resets it back to 1, `work`/`crime`/`slut` for
  risk-based income, and `rob` to steal from others
- a passive **Payday**: every 2-4h, one random user gets a random amount (100-10,000 by
  default), announced in a configurable channel (`PAYDAY_CHANNEL_ID`) — no command needed,
  no per-user cooldown or fairness tracking, just a single global timer so payouts land one
  at a time instead of clustering
- a `bank` to protect balance from being robbed
- a `shop` with items (rob shield, cooldown reset), plus `gift` and `trade` between players
- `marry`/`divorce` and a weekly `lottery` with an automatic prize draw
- `profile`/`stats` and multiple `leaderboard` variants (balance, games played, biggest
  win, most successful robberies)
- a persistent **achievement system** (`utils/achievements.py`) — 12 one-time unlocks
  across net worth, total wagered, successful robs, games played, and daily streak
  tiers, checked automatically after every casino/economy command (`events/
  achievements.py`) and announced in the channel the moment one is earned, not just
  recomputed live each time you check `/profile`
- `cooldowns` to check your remaining cooldowns without triggering them
- admin commands to add, set, give-to-everyone, or reset a user's balance, grant RPG
  levels/items directly, and per-server `settings` to disable individual games or
  restrict them to specific channels

**Level System** — a per-server activity leveling system separate from the RPG's own
character leveling:
- earns XP from chatting (with a spam-proof per-message cooldown) and from being active
  in voice channels (deafened members and empty/AFK channels don't count); max level 150,
  tuned to take months of real activity to reach
- every level 1-150 has its own unique badge, and leveling up pays out gold into the same
  balance every casino game uses
- anyone holding a role in `BLACKLIST_ROLE_IDS` earns nothing from this system at all — the
  same blacklist Payday checks before picking a winner
- admins can run a temporary server-wide XP multiplier with `/level-boost`, or grant/
  remove XP for a specific member directly with `/level-givexp` (still runs through the
  normal level-up gold payout and announcement if it crosses a level)
- `/level`, `/stats`, `/level-leaderboard`, `/level-badges` for everyone;
  `/level-boost`, `/level-boost-clear`, `/level-givexp` for admins

**Commands** — casino/economy commands are hybrid commands (work as both `/slash` and
`!prefix`); the RPG is slash-only for simplicity.

**UI** — built entirely with Discord's Components V2 (`Container`, `TextDisplay`,
`ActionRow`) instead of classic embeds, which requires `discord.py` 2.6 or newer.

**Infrastructure**:

- A global + per-channel + per-message rate limiter (`utils/ratelimit.py`) tuned to the
  real, commonly-observed Discord bucket sizes (~5 requests/5s per channel or message,
  50/s global) to avoid Discord API throttling on frequent message edits and sends, without
  leaving so much safety margin that a busy shared gamble channel queues up behind itself.
  Edits (in-progress game state) and new sends (initial command replies) draw from separate
  budgets. Multiplayer-feeling games (Blackjack's Hit/Stand/Double/Split) route their
  per-click card reveals through Discord's separate interaction-response API instead of a
  plain message edit, so those don't compete with other concurrent games in the same
  channel for the shared per-channel edit budget at all — only the automated parts (deal
  animation, the dealer's own auto-play) do
- Gamble-channel restriction (`/set-gamblechannel`) auto-manages that channel's native
  Discord slowmode, scaled to actual traffic: a 2s baseline when set, auto-raised to 5s if
  the channel's message rate hits a configurable threshold (checked once a minute), and
  cleared when the restriction is removed — never overrides a slowmode value set manually
- Hot code reloading in development (`HOT_RELOAD=true`, picks up changes to
  `commands/`, `events/`, `rpg/`, `utils/`, and `database/` within ~1.5s, no restart)
- An in-process git watcher that checks `origin` every 60s and fast-forward-pulls any
  new commits, posting to the restart channel when one lands
- Every Discord server the bot is in gets its own isolated SQLite database file at
  `data/guilds/<guild_id>.db`, created automatically the first time it's needed — no
  shared state between servers, and no external database server to install or run
- An automated backup every 30-60 minutes — a full JSON snapshot of every guild's SQLite
  tables, written silently to `backups/` (gitignored) with the oldest pruned once more
  than 48 accumulate; if `SUPABASE_DB_URL`/`SUPABASE_DB_URL_FILE` is configured, the same
  snapshot is also pushed to Postgres/Supabase as a best-effort off-site copy — Supabase
  is never read from live, it's purely a disaster-recovery copy alongside the local JSON
  backup
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

2. **Database**

   Nothing to create — each Discord server the bot joins gets its own SQLite database
   file, created automatically at `data/guilds/<guild_id>.db` the first time it's needed,
   tables included. Just make sure the bot process can write to the `data/` directory.

3. **Configure `.env`**

   Copy `.env.example` to `.env` and fill it in:

   ```bash
   cp .env.example .env
   ```

   | Variable | Description |
   |---|---|
   | `DISCORD_TOKEN` | Bot token from the [Discord Developer Portal](https://discord.com/developers/applications) |
   | `PREFIX` | Prefix for text commands (default: `!`) |
   | `SUPABASE_DB_URL` / `SUPABASE_DB_URL_FILE` | Optional Postgres/Supabase connection string (or a file holding one) — if set, a snapshot of every guild's SQLite data is pushed there every 30-60 minutes as an off-site backup; purely for disaster recovery, never used as a live database |
   | `STARTING_BALANCE` | Starting balance for new players (default: 100000) |
   | `DAILY_AMOUNT` | Amount granted by the daily bonus (default: 500) |
   | `PAYDAY_MIN_AMOUNT` / `PAYDAY_MAX_AMOUNT` | Range for the random passive Payday payout, one random user every 2-4h (default: 100-10000) |
   | `PAYDAY_CHANNEL_ID` | Channel Payday payouts are announced in |
   | `HOT_RELOAD` | Auto-reload changed cogs/modules in development (default: `true`) |
   | `RESTART_LOG_CHANNEL_ID` | Optional channel ID for startup/crash/restart announcements |
   | `IDLE_ANNOUNCE_CHANNEL_ID` | Channel that shows a live-updated list of everyone currently `/idle` farming |
   | `BLACKLIST_ROLE_IDS` | Comma-separated role IDs excluded from Level System XP/badges/gold and from being picked for Payday |

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

The bot runs natively under [pm2](https://pm2.keymetrics.dev/) — there's no database
server to install or run, so `git pull` + a pm2 restart is all a routine update needs.

1. Get the code onto the VPS (`git clone` this repo, or `scp` it over), install pm2
   (Python deps are handled automatically — see below):

   ```bash
   npm install -g pm2
   ```

2. Create `.env`:

   ```bash
   cp .env.example .env
   ```

   Fill in `DISCORD_TOKEN`. There are no database credentials to configure — just make
   sure the bot's working directory is writable so it can create `data/guilds/`.
   Optionally set `SUPABASE_DB_URL`/`SUPABASE_DB_URL_FILE` if you want the periodic
   backup snapshots pushed off-site to a Postgres/Supabase project too.

3. Start the bot under pm2:

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

The bot recovers automatically from a crash via pm2's `autorestart`; `cron_restart`
additionally restarts the process daily at 4am. Useful commands: `pm2 status`,
`pm2 logs GamblerV2`, `pm2 restart GamblerV2`.

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
| [Casino Games](docs/rpg-wiki/Casino%20Games/Casino%20Overview.md) | All 13 games of chance and their odds |
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
  `total_wagered`, `biggest_win`, or `robs_succeeded`); medals for the top 3, a divider
  before the rest, comma-formatted values, a `(you)` tag on your own row if you're
  shown, and a board-specific accent color
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
- `shop` — shows purchasable items with their item key, price, and description
- `buy <item> [quantity=1]` — buy an item (`shield` or `cooldown_reset`)
- `inventory` (alias `inv`) — shows your inventory with item keys and quantities
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
  success rate, and how often you've been robbed, grouped into sections with a divider;
  shows your permanently unlocked achievement badges and an accent color reflecting
  overall profit/loss

### Admin
Requires the **Administrator** permission on the server.
- `addmoney <user> <amount>` — add or (with a negative amount) remove balance
- `setbalance <user> <amount>` — set balance to an exact value
- `giveall <amount>` — give (or take) balance from every player at once
- `resetuser <user>` — reset a user's balance, bank, inventory, marriage, RPG character,
  and statistics
- `rpgsetlevel <user> <level> [xp=0]` — set a player's RPG level directly
- `rpggivexp <user> <amount>` — grant a player raw XP, running it through the same
  level-up math as monster/boss kills (handles multi-level jumps and the level cap)
  instead of hard-setting level/XP like `rpgsetlevel`
- `rpggive <user> <item> [quantity=1]` — give a player a piece of equipment or a potion
  for free
- `rpggiveprimordial <user> <slot>` — spawn a freshly-rolled ✨ Primordial item straight
  to a player
- `permcooldown <user> <enabled>` — toggle a permanent bypass of `work`/`crime`/`slut`/
  `rob`/`duel` cooldowns for a player
- `permshield <user> <enabled>` — toggle permanent `rob` immunity for a player (reuses
  the same shield mechanism as the `shield` item, just set far in the future)
- `restart` — restart the bot process
- `settings` — shows this server's disabled games and channel restrictions
- `togglegame <game> <enabled>` — enable or disable a specific game on this server
- `togglechannel <add|remove|clear>` — restrict games to specific channels
- `set-gamblechannel [channel] [clear]` — restrict the whole bot to one channel
  (admins are always exempt)
- `set-updateschannel [channel] [clear]` — announce newly shipped commands/game modes
  here after a restart

### Misc
- `help` — interactive command browser with a category dropdown (economy, games, RPG,
  admin, etc.) instead of one long wall of text; the overview groups categories into
  sections (Economy & Social, Casino Games, RPG, Server & Admin) with a running command
  count, and each category has its own accent color when selected

### Games
All games accept the bet as a number, `all`, `half`, or a percentage (`50%`).

- `blackjack <bet> [perfect_pairs] [twentyone_plus_three] [insurance]` — classic
  Blackjack with Hit/Stand/Double/Split buttons; cards are dealt, drawn, and the
  dealer's hand is revealed with an animated reveal instead of appearing instantly.
  Three optional side bets settle right after the deal, independent of how the main
  hand plays out: **Perfect Pairs** (your first two cards match — Mixed 5:1, Colored
  10:1, Perfect 30:1), **21+3** (your two cards + the dealer's up-card make a poker
  hand — Flush 5:1, Straight 10:1, Three of a Kind 30:1, Straight Flush 40:1, Suited
  Trips 100:1), and **Insurance** (max half your main bet, only offered when the
  dealer's up-card is an Ace — pays 2:1 if the dealer has Blackjack). A **Surrender**
  button is available as your very first decision on the initial two cards — forfeit
  and get back half your main bet instead of playing out a bad hand
- `mines <bet> [mines=3] [cols=5] [rows=4] [auto_cashout]` — customizable grid (2-5
  cols, 2-5 rows — the full 5x5 unlocks up to 23 mines), avoid mines, cash out
  anytime; optionally set `auto_cashout` to a number of safe tiles and the game cashes
  out for you automatically the moment you reach it
- `hilo <bet>` — guess higher/lower, multiplier grows with each correct card
- `plinko <bet> [risk=medium] [rows=12]` — drop a ball through the Plinko board
- `limbo <bet> <target>` — set a target multiplier (up to 1,000x), the random result
  must reach it
- `keno <bet> [picks=5]` — pick numbers and hope for hits in the draw
- `slots <bet>` — animated 3x3 grid with 5 paylines (rows + both diagonals); reels stop
  one column at a time before the result is revealed. A 🃏 **Wild** symbol substitutes
  for any other symbol to complete a line (three wilds pay the game's top jackpot)
- `roulette <bet> <choice>` — bet on a straight number (0-36), color (`red`/`black`),
  even/odd, a dozen (`1st12`/`2nd12`/`3rd12`, pays 3x), a column (`col1`/`col2`/`col3`,
  pays 3x), or a split between two table-adjacent numbers (e.g. `17/18`, pays 18x)
- `dice <bet> <prediction>` — predict the sum of two dice (2-12)
- `soloflip <bet> [call=heads]` (alias `cf`) — call heads or tails against the house
- `scratchcard <bet>` (alias `scratch`) — click each of the 9 tiles yourself to scratch
  it off; match 4 or more of the same symbol to win
- `horserace <bet> [bet_type=win]` (alias `horse`) — place your bet, then pick from 6
  randomly-named horses in a dropdown (odds shown per horse, individually simulated) and
  watch the animated race. `bet_type` picks **Win** (1st place only, default), **Place**
  (top 2, lower payout), or **Show** (top 3, lowest payout but easiest to hit) — each with
  its own independently calibrated odds per horse
- `baccarat <bet> <choice> [player_pair] [banker_pair]` — bet on Player, Banker, or Tie;
  plays out the real casino drawing rules (natural 8/9, third-card rules for both hands)
  with an animated reveal. Two optional side bets settle on the first two cards dealt,
  independent of the main hand: **Player Pair** and **Banker Pair** (either pays 11:1 if
  that hand's first two cards are a pair)

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
- `idle <name> [minutes=30] [auto=False]` — auto-farms that dungeon (monsters + boss) in
  the background for up to 120 minutes, then posts one summary with a ping — no per-fight
  spam. With `auto: True`, runs indefinitely in 60-minute checkpoints instead, until `idle`
  is run again to stop it
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
main.py                     Bot entry point, loads cogs, opens per-guild SQLite databases, hot reload, restart announcements, git watcher, DB backups
database/manager.py          GuildDatabaseManager — lazily opens/creates a guild's SQLite database file on first use
database/guild_db.py         Per-guild SQLite engine (aiosqlite) — wallet/bank/inventory/stats/social/RPG/leveling tables & queries
database/backup.py           SupabaseBackup — pushes a periodic off-site JSON snapshot of each guild's data to Postgres/Supabase
utils/economy.py             Bet parsing, formatting, house edge constant, UI building blocks
utils/cards.py                Card deck + custom card emoji mapping for Blackjack & Hilo
assets/cards/                 Downloaded card emoji images (reference copies, not loaded at runtime)
utils/items.py                Shop catalog (item keys, prices, effects)
utils/achievements.py         Achievement catalog + unlock/announce logic, shared by /profile and the listener
utils/checks.py               Per-server game enable/channel checks
utils/ratelimit.py            Global + per-channel, congestion-aware token-bucket limiters for edits/sends
utils/level_math.py           Level System XP↔level curve math
utils/level_badges.py         Level System badge rendering (mirrors rpg/badges.py)
utils/role_blacklist.py       Shared role-ID blacklist, checked by the Level System and Payday
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
commands/admin.py             addmoney, setbalance, giveall, resetuser, permcooldown, permshield, botstatus, restart, rpgsetlevel, rpggivexp, rpggive, rpggiveprimordial
commands/settings.py          settings, togglegame, togglechannel, set-gamblechannel, set-updateschannel
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
commands/rpg_character.py     rpgstart, rpgswitchclass, classes, character, heal
commands/rpg_dungeon.py       dungeons, dungeon, dungeonboss (both with a team-fight lobby mode), idle
commands/rpg_shop.py          rpgshop, rpgbuy, rpgequip, rpguse, rpgsell, rpgupgrade, rpgautoupgrade, rpgautobuy, rpgequipprimordial, rpgunequipprimordial, rpginventory
commands/rpg_arena.py         duel, arena
commands/levels.py            level, stats, level-leaderboard, level-badges, level-boost, level-boost-clear, level-givexp
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
events/payday.py              Background loop: one random user gets a passive payday every 2-4h, announced in a channel
events/achievements.py        Listens for command completions and checks/announces newly unlocked achievements
deploy/ecosystem.config.js    pm2 process config (autorestart, daily 4am cron_restart)
deploy/install_pm2.sh         Starts the bot under pm2, posts a startup status message
docs/rpg-wiki/                Obsidian vault documenting every system, generated from live game data
```

---

## License

No license has been specified yet — all rights reserved by default until one is added.
