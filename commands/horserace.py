import asyncio
import random

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


def _calibrate_odds() -> list[float]:
    rng = random.Random(_CALIBRATION_SEED)
    wins = [0] * len(HORSE_PROFILES)
    for _ in range(_CALIBRATION_TRIALS):
        winner, _ = _run_race(rng)
        wins[winner] += 1
    return [round(RTP / (w / _CALIBRATION_TRIALS), 2) for w in wins]


PAYOUTS = _calibrate_odds()


def render_track(names: list[str], positions: list[int], *, winner: int | None = None) -> str:
    lines = []
    for i, name in enumerate(names):
        pos = min(positions[i], TRACK_LENGTH)
        track = "▫️" * pos + "🐎" + "▫️" * (TRACK_LENGTH - pos)
        marker = "🏆 " if winner == i else f"{i + 1}. "
        lines.append(f"{marker}**{name}** ({PAYOUTS[i]:g}x)  {track}🏁")
    return "\n".join(lines)


class HorseSelect(ui.Select):
    def __init__(self, names: list[str]):
        options = [
            discord.SelectOption(label=name, value=str(i), description=f"Odds: {PAYOUTS[i]:g}x")
            for i, name in enumerate(names)
        ]
        super().__init__(placeholder="Choose your horse...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await self.view.start_race(interaction, int(self.values[0]))


class HorseRaceView(ui.LayoutView):
    def __init__(self, cog: "HorseRace", ctx: commands.Context, bet: int, names: list[str]):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.names = names
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container(
            "🏇 Horse Race",
            f"{render_track(names, [0] * len(names))}\n\n**Bet:** {fmt(bet)}\n🐎 Pick your horse below!",
        )
        self.select = HorseSelect(names)
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
        body = f"{render_track(self.names, positions, winner=winner)}\n\n**Bet:** {fmt(self.bet)}"
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

        won = winner == horse_index
        multiplier = PAYOUTS[horse_index]
        payout = int(self.bet * multiplier) if won else 0
        if payout:
            await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)

        if won:
            footer = f"🎉 **{self.names[horse_index]} wins!** {multiplier:g}x → Payout {fmt(payout)}"
        else:
            footer = f"😢 **{self.names[winner]} wins.** Your horse didn't place first."

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
    @app_commands.describe(bet="Bet (a number, 'half', 'all', or e.g. '50%')")
    @game_enabled("horserace")
    async def horserace(self, ctx: commands.Context, bet: str):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        names = random.sample(NAME_POOL, len(HORSE_PROFILES))
        view = HorseRaceView(self, ctx, amount, names)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(HorseRace(bot))
