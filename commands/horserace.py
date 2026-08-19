import asyncio
import random
from typing import Literal

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

RTP = 1 - HOUSE_EDGE
TRACK_LENGTH = 15
TICK_DELAY = 0.7
_CALIBRATION_TRIALS = 60_000
_CALIBRATION_SEED = 20260814

HORSE_PROFILES = [
    (2, 6),
    (2, 6),
    (1, 6),
    (1, 6),
    (1, 5),
    (1, 5),
]

NAME_POOL = [
    "Thunderbolt", "Silver Arrow", "Lucky Star", "Midnight", "Golden Hoof", "Longshot",
    "Blaze Runner", "Shadow Fox", "Crimson Comet", "Iron Will", "Velvet Storm", "Northern Wind",
    "Diamond Dash", "Copper Flash", "Wildfire", "Moonlit Gallop", "Rebel Yell", "Stormchaser",
    "Ghost Rider", "Ironclad", "Sundance", "Whisper", "Maverick", "Blue Thunder", "Firefly",
    "Nightshade", "Solar Flare", "Windwalker", "Ember", "Frostbite",
]


def _run_race(rng: random.Random) -> tuple[int, list[list[int]]]:
    """Simulates one race. Returns (winner_index, position_history) where
    position_history[t] is the list of every horse's position after tick t."""
    positions = [0] * len(HORSE_PROFILES)
    history = []
    while True:
        for i, (lo, hi) in enumerate(HORSE_PROFILES):
            positions[i] += rng.randint(lo, hi)
        history.append(list(positions))
        winners = [i for i, p in enumerate(positions) if p >= TRACK_LENGTH]
        if winners:
            return max(winners, key=lambda i: positions[i]), history


BetType = Literal["win", "place", "show"]
BET_TYPE_LABELS = {"win": "Win (1st)", "place": "Place (top 2)", "show": "Show (top 3)"}
_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th"}


def _rank_order(positions: list[int]) -> list[int]:
    return sorted(range(len(positions)), key=lambda i: (-positions[i], i))


def _calibrate_odds() -> tuple[list[float], list[float], list[float]]:
    rng = random.Random(_CALIBRATION_SEED)
    win_counts = [0] * len(HORSE_PROFILES)
    place_counts = [0] * len(HORSE_PROFILES)
    show_counts = [0] * len(HORSE_PROFILES)
    for _ in range(_CALIBRATION_TRIALS):
        _, history = _run_race(rng)
        order = _rank_order(history[-1])
        win_counts[order[0]] += 1
        for idx in order[:2]:
            place_counts[idx] += 1
        for idx in order[:3]:
            show_counts[idx] += 1
    win = [round(RTP / (w / _CALIBRATION_TRIALS), 2) for w in win_counts]
    place = [round(RTP / (p / _CALIBRATION_TRIALS), 2) for p in place_counts]
    show = [round(RTP / (s / _CALIBRATION_TRIALS), 2) for s in show_counts]
    return win, place, show


WIN_PAYOUTS, PLACE_PAYOUTS, SHOW_PAYOUTS = _calibrate_odds()
PAYOUTS_BY_TYPE = {"win": WIN_PAYOUTS, "place": PLACE_PAYOUTS, "show": SHOW_PAYOUTS}


def render_track(names: list[str], positions: list[int], payouts: list[float], *, winner: int | None = None) -> str:
    lines = []
    for i, name in enumerate(names):
        pos = min(positions[i], TRACK_LENGTH)
        track = "▫️" * pos + "🐎" + "▫️" * (TRACK_LENGTH - pos)
        marker = "🏆 " if winner == i else f"{i + 1}. "
        lines.append(f"{marker}**{name}** ({payouts[i]:g}x)  {track}🏁")
    return "\n".join(lines)


class HorseSelect(ui.Select):
    def __init__(self, names: list[str], payouts: list[float]):
        options = [
            discord.SelectOption(label=name, value=str(i), description=f"Odds: {payouts[i]:g}x")
            for i, name in enumerate(names)
        ]
        super().__init__(placeholder="Choose your horse...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await self.view.start_race(interaction, int(self.values[0]))


class HorseRaceView(ui.LayoutView):
    def __init__(
        self, cog: "HorseRace", ctx: commands.Context, bet: int, names: list[str], bet_type: BetType,
    ):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.names = names
        self.bet_type = bet_type
        self.payouts = PAYOUTS_BY_TYPE[bet_type]
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container(
            "🏇 Horse Race",
            f"{render_track(names, [0] * len(names), self.payouts)}\n\n"
            f"**Bet:** {fmt(bet)}  •  **Type:** {BET_TYPE_LABELS[bet_type]}\n🐎 Pick your horse below!",
        )
        self.select = HorseSelect(names, self.payouts)
        row = ui.ActionRow()
        row.add_item(self.select)
        self.container.add_item(row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your race!", ephemeral=True)
            return False
        return True

    def update(self, positions: list[int], *, winner: int | None = None, footer: str | None = None, color=None):
        body = (
            f"{render_track(self.names, positions, self.payouts, winner=winner)}\n\n"
            f"**Bet:** {fmt(self.bet)}  •  **Type:** {BET_TYPE_LABELS[self.bet_type]}"
        )
        if footer:
            body += f"\n{footer}"
        self.text.content = f"## 🏇 Horse Race\n{body}"
        if color:
            self.container.accent_colour = color

    async def start_race(self, interaction: discord.Interaction, horse_index: int):
        if self.finished:
            return
        self.finished = True
        self.select.disabled = True
        self.select.placeholder = self.names[horse_index]

        self.update([0] * len(self.names), footer=f"🏁 You bet on **{self.names[horse_index]}**. And they're off!")
        await interaction.response.edit_message(view=self)

        winner, history = _run_race(random)
        for tick, positions in enumerate(history):
            await asyncio.sleep(TICK_DELAY)
            is_last = tick == len(history) - 1
            self.update(positions, winner=winner if is_last else None, footer=None if is_last else "🏇 Racing...")
            await limited_edit(self.message, view=self)

        order = _rank_order(history[-1])
        cutoff = {"win": 1, "place": 2, "show": 3}[self.bet_type]
        won = horse_index in order[:cutoff]
        finish_rank = order.index(horse_index) + 1
        multiplier = self.payouts[horse_index]
        payout = int(self.bet * multiplier) if won else 0
        if payout:
            await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)

        ordinal = _ORDINALS.get(finish_rank, f"{finish_rank}th")
        if won:
            footer = (
                f"🎉 **{self.names[horse_index]} finished {ordinal}!** "
                f"{multiplier:g}x → Payout {fmt(payout)}"
            )
        else:
            footer = f"😢 **{self.names[horse_index]} finished {ordinal}.** Not good enough for {BET_TYPE_LABELS[self.bet_type]}."

        self.update(history[-1], winner=winner, footer=footer, color=discord.Color.green() if won else discord.Color.red())
        await limited_edit(self.message, view=self)
        self.stop()

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self.select.disabled = True
        if self.message:
            await self.cog.bot.db.update_balance(self.ctx.author.id, self.bet)
            self.update(
                [0] * len(self.names),
                footer="⏱️ No horse chosen in time — bet refunded.",
                color=discord.Color.greyple(),
            )
            await limited_edit(self.message, view=self)


class HorseRace(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="horserace", aliases=["horse"], description="Place a bet, then pick a horse and watch the race."
    )
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        bet_type="Win = 1st place only (default), Place = top 2, Show = top 3 (lower payout, easier to hit)",
    )
    @game_enabled("horserace")
    async def horserace(self, ctx: commands.Context, bet: str, bet_type: BetType = "win"):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        names = random.sample(NAME_POOL, len(HORSE_PROFILES))
        view = HorseRaceView(self, ctx, amount, names, bet_type)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(HorseRace(bot))
