import asyncio
import json
import random
from pathlib import Path

import discord
from discord import ui
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

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

WILD_SYMBOL = "🃏"
WILD_WEIGHT = 2
WILD_BASE_MULT = 100

_MANIFEST_PATH = Path(__file__).parent.parent / "assets" / "slots" / "manifest.json"
_SYMBOL_KEYS = {
    "🍒": "cherry",
    "🍋": "lemon",
    "🍇": "grape",
    "🔔": "bell",
    "💎": "diamond",
    "7️⃣": "seven",
}


def _load_symbol_emojis() -> dict[str, str]:
    try:
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {
        unicode_emoji: f"<:{manifest[key]['emoji_name']}:{manifest[key]['id']}>"
        for unicode_emoji, key in _SYMBOL_KEYS.items()
        if key in manifest
    }


SYMBOL_EMOJIS = _load_symbol_emojis()


def display(symbol: str) -> str:
    return SYMBOL_EMOJIS.get(symbol, symbol)

PAYLINES = [
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 4, 8),
    (2, 4, 6),
]
LINE_NAMES = ["Top row", "Middle row", "Bottom row", "Diagonal ↘", "Diagonal ↗"]
COLUMNS = [(0, 3, 6), (1, 4, 7), (2, 5, 8)]

BASE_MULT = {emoji: base_mult for emoji, _, base_mult in SYMBOLS}
BASE_MULT[WILD_SYMBOL] = WILD_BASE_MULT
_POPULATION = [emoji for emoji, _, _ in SYMBOLS] + [WILD_SYMBOL]
_WEIGHTS = [weight for _, weight, _ in SYMBOLS] + [WILD_WEIGHT]


def _line_symbol(a: str, b: str, c: str) -> str | None:
    """Returns the symbol a line pays as (wilds substitute for anything), or None if it doesn't win."""
    non_wild = [s for s in (a, b, c) if s != WILD_SYMBOL]
    if not non_wild:
        return WILD_SYMBOL
    if all(s == non_wild[0] for s in non_wild):
        return non_wild[0]
    return None


def _calibrate_scale() -> float:
    # For 3 independent cells, P(line resolves to symbol i) = (p_i + p_wild)^3 - p_wild^3
    # (all non-wild cells among the 3 are i, excluding the all-wild case which resolves to WILD instead).
    total_weight = sum(_WEIGHTS)
    p_wild = WILD_WEIGHT / total_weight
    expected_raw = (p_wild**3) * WILD_BASE_MULT
    for emoji, weight, base_mult in SYMBOLS:
        p = weight / total_weight
        expected_raw += ((p + p_wild) ** 3 - p_wild**3) * base_mult
    target_per_line = RTP / len(PAYLINES)
    return target_per_line / expected_raw


_scale = _calibrate_scale()
PAYOUTS = {emoji: round(_scale * base_mult, 2) for emoji, base_mult in BASE_MULT.items()}


def random_symbol() -> str:
    return random.choices(_POPULATION, weights=_WEIGHTS, k=1)[0]


def spin_grid() -> list[str]:
    return random.choices(_POPULATION, weights=_WEIGHTS, k=9)


def render_grid(grid: list[str]) -> str:
    return "\n".join(" ".join(display(s) for s in grid[r * 3 : r * 3 + 3]) for r in range(3))


def evaluate(grid: list[str], bet: int) -> tuple[int, list[str]]:
    total_payout = 0
    winning_lines = []
    for name, (a, b, c) in zip(LINE_NAMES, PAYLINES):
        symbol = _line_symbol(grid[a], grid[b], grid[c])
        if symbol:
            multiplier = PAYOUTS[symbol]
            line_payout = int(bet * multiplier)
            total_payout += line_payout
            symbols = f"{display(grid[a])}{display(grid[b])}{display(grid[c])}"
            wild_note = " (🃏 wild)" if WILD_SYMBOL in (grid[a], grid[b], grid[c]) and symbol != WILD_SYMBOL else ""
            winning_lines.append(f"{name}: {symbols}{wild_note} → {multiplier:g}x = {fmt(line_payout)}")
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

    @commands.hybrid_command(
        name="slots", description="Spin the 3x3 slot machine (5 paylines). 🃏 Wilds substitute for any symbol."
    )
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
                await limited_edit(message, view=view)

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
        await limited_edit(message, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Slots(bot))
