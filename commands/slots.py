import asyncio
import random

import discord
from discord import ui
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, fmt, game_container, resolve_bet

RTP = 1 - HOUSE_EDGE
SPIN_DELAY = 0.8

SYMBOLS = [
    ("🍒", 30, 3),
    ("🍋", 25, 4),
    ("🍇", 20, 6),
    ("🔔", 15, 10),
    ("💎", 7, 25),
    ("7️⃣", 3, 50),
]

PAYLINES = [
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 4, 8),
    (2, 4, 6),
]
LINE_NAMES = ["Top row", "Middle row", "Bottom row", "Diagonal ↘", "Diagonal ↗"]
COLUMNS = [(0, 3, 6), (1, 4, 7), (2, 5, 8)]

_total_weight = sum(weight for _, weight, _ in SYMBOLS)
_expected_raw = sum(((weight / _total_weight) ** 3) * base_mult for _, weight, base_mult in SYMBOLS)
_target_per_line = RTP / len(PAYLINES)
_scale = _target_per_line / _expected_raw
PAYOUTS = {emoji: round(_scale * base_mult, 2) for emoji, _, base_mult in SYMBOLS}
_POPULATION = [emoji for emoji, _, _ in SYMBOLS]
_WEIGHTS = [weight for _, weight, _ in SYMBOLS]


def random_symbol() -> str:
    return random.choices(_POPULATION, weights=_WEIGHTS, k=1)[0]


def spin_grid() -> list[str]:
    return random.choices(_POPULATION, weights=_WEIGHTS, k=9)


def render_grid(grid: list[str]) -> str:
    return "\n".join(" ".join(grid[r * 3 : r * 3 + 3]) for r in range(3))


def evaluate(grid: list[str], bet: int) -> tuple[int, list[str]]:
    total_payout = 0
    winning_lines = []
    for name, (a, b, c) in zip(LINE_NAMES, PAYLINES):
        if grid[a] == grid[b] == grid[c]:
            multiplier = PAYOUTS[grid[a]]
            line_payout = int(bet * multiplier)
            total_payout += line_payout
            winning_lines.append(f"{name}: {grid[a]}{grid[b]}{grid[c]} → {multiplier:g}x = {fmt(line_payout)}")
    return total_payout, winning_lines


class SlotsView(ui.LayoutView):
    def __init__(self, bet: int):
        super().__init__(timeout=None)
        self.bet = bet
        self.container, self.text = game_container(
            "🎰 Slots", f"{render_grid([random_symbol() for _ in range(9)])}\n\n**Bet:** {fmt(bet)}\n🎲 Spinning..."
        )
        self.add_item(self.container)

    def update(self, grid: list[str], *, footer: str | None = None, color: discord.Color | None = None):
        body = f"{render_grid(grid)}\n\n**Bet:** {fmt(self.bet)}"
        if footer:
            body += f"\n{footer}"
        self.text.content = f"## 🎰 Slots\n{body}"
        if color:
            self.container.accent_colour = color


class Slots(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="slots", description="Spin the 3x3 slot machine (5 paylines).")
    @game_enabled("slots")
    async def slots(self, ctx: commands.Context, bet: str):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        final_grid = spin_grid()
        view = SlotsView(amount)
        message = await ctx.send(view=view)

        display = [random_symbol() for _ in range(9)]
        for locked_columns in range(4):
            await asyncio.sleep(SPIN_DELAY)
            for col in range(3):
                indices = COLUMNS[col]
                if col < locked_columns:
                    for idx in indices:
                        display[idx] = final_grid[idx]
                else:
                    for idx in indices:
                        display[idx] = random_symbol()

            if locked_columns < 3:
                view.update(display, footer="🎲 Spinning...")
                await message.edit(view=view)

        payout, winning_lines = evaluate(final_grid, amount)
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        won = payout > 0
        if won:
            footer = "🎉 **Winning lines:**\n" + "\n".join(winning_lines) + f"\n**Total payout:** {fmt(payout)}"
        else:
            footer = "😢 No winning lines — better luck next spin."

        view.update(final_grid, footer=footer, color=discord.Color.green() if won else discord.Color.red())
        await message.edit(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Slots(bot))
