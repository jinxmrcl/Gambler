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

HORSES = [
    ("Thunderbolt", 2, 6),
    ("Silver Arrow", 2, 6),
    ("Lucky Star", 1, 6),
    ("Midnight", 1, 6),
    ("Golden Hoof", 1, 5),
    ("Longshot", 1, 5),
]
HorseName = Literal["Thunderbolt", "Silver Arrow", "Lucky Star", "Midnight", "Golden Hoof", "Longshot"]
NAME_TO_INDEX = {name: i for i, (name, _, _) in enumerate(HORSES)}


def _run_race(rng: random.Random) -> tuple[int, list[list[int]]]:
    """Simulates one race. Returns (winner_index, position_history) where
    position_history[t] is the list of every horse's position after tick t."""
    positions = [0] * len(HORSES)
    history = []
    while True:
        for i, (_, lo, hi) in enumerate(HORSES):
            positions[i] += rng.randint(lo, hi)
        history.append(list(positions))
        winners = [i for i, p in enumerate(positions) if p >= TRACK_LENGTH]
        if winners:
            return max(winners, key=lambda i: positions[i]), history


def _calibrate_odds() -> list[float]:
    rng = random.Random(_CALIBRATION_SEED)
    wins = [0] * len(HORSES)
    for _ in range(_CALIBRATION_TRIALS):
        winner, _ = _run_race(rng)
        wins[winner] += 1
    return [round(RTP / (w / _CALIBRATION_TRIALS), 2) for w in wins]


PAYOUTS = _calibrate_odds()


def render_track(positions: list[int], *, winner: int | None = None) -> str:
    lines = []
    for i, (name, _, _) in enumerate(HORSES):
        pos = min(positions[i], TRACK_LENGTH)
        track = "▫️" * pos + "🐎" + "▫️" * (TRACK_LENGTH - pos)
        marker = "🏆 " if winner == i else f"{i + 1}. "
        lines.append(f"{marker}**{name}** ({PAYOUTS[i]:g}x)  {track}🏁")
    return "\n".join(lines)


class HorseRaceView(ui.LayoutView):
    def __init__(self, bet: int, horse_index: int):
        super().__init__(timeout=None)
        self.bet = bet
        self.horse_index = horse_index
        self.container, self.text = game_container(
            "🏇 Horse Race",
            f"{render_track([0] * len(HORSES))}\n\n**Bet:** {fmt(bet)} on {HORSES[horse_index][0]}\n🏁 And they're off!",
        )
        self.add_item(self.container)

    def update(self, positions: list[int], *, winner: int | None = None, footer: str | None = None, color=None):
        body = f"{render_track(positions, winner=winner)}\n\n**Bet:** {fmt(self.bet)} on {HORSES[self.horse_index][0]}"
        if footer:
            body += f"\n{footer}"
        self.text.content = f"## 🏇 Horse Race\n{body}"
        if color:
            self.container.accent_colour = color


class HorseRace(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="horserace", aliases=["horse"], description="Bet on a horse and watch the race.")
    @app_commands.describe(bet="Bet (a number, 'half', 'all', or e.g. '50%')", horse="Which horse to back")
    @game_enabled("horserace")
    async def horserace(self, ctx: commands.Context, bet: str, horse: HorseName):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        horse_index = NAME_TO_INDEX[horse]
        winner, history = _run_race(random)
        view = HorseRaceView(amount, horse_index)
        message = await ctx.send(view=view)

        for tick, positions in enumerate(history):
            await asyncio.sleep(TICK_DELAY)
            is_last = tick == len(history) - 1
            view.update(positions, winner=winner if is_last else None, footer=None if is_last else "🏇 Racing...")
            await limited_edit(message, view=view)

        won = winner == horse_index
        multiplier = PAYOUTS[horse_index]
        payout = int(amount * multiplier) if won else 0
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        if won:
            footer = f"🎉 **{HORSES[horse_index][0]} wins!** {multiplier:g}x → Payout {fmt(payout)}"
        else:
            footer = f"😢 **{HORSES[winner][0]} wins.** Your horse didn't place first."

        view.update(history[-1], winner=winner, footer=footer, color=discord.Color.green() if won else discord.Color.red())
        await limited_edit(message, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(HorseRace(bot))
