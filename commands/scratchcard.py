import asyncio
import math
import random

import discord
from discord import ui
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

RTP = 1 - HOUSE_EDGE
REVEAL_DELAY = 0.3
GRID_SIZE = 9
MATCH_THRESHOLD = 4
HIDDEN = "❔"

SYMBOLS = [
    ("🍀", 20, 2),
    ("🎁", 19, 3),
    ("🔔", 18, 5),
    ("💰", 16, 10),
    ("💎", 15, 25),
    ("👑", 12, 60),
]

_total_weight = sum(weight for _, weight, _ in SYMBOLS)
_POPULATION = [emoji for emoji, _, _ in SYMBOLS]
_WEIGHTS = [weight for _, weight, _ in SYMBOLS]


def _compositions(total: int, parts: int):
    if parts == 1:
        yield (total,)
        return
    for i in range(total + 1):
        for rest in _compositions(total - i, parts - 1):
            yield (i,) + rest


def _build_payouts() -> dict[str, float]:
    probs = [weight / _total_weight for _, weight, _ in SYMBOLS]
    base_mults = [base for _, _, base in SYMBOLS]

    expected_raw = 0.0
    for composition in _compositions(GRID_SIZE, len(SYMBOLS)):
        qualifying = [i for i, c in enumerate(composition) if c >= MATCH_THRESHOLD]
        if not qualifying:
            continue
        winner = max(qualifying, key=lambda i: base_mults[i])

        probability = math.factorial(GRID_SIZE)
        for c in composition:
            probability //= math.factorial(c) or 1
        probability = float(probability)
        for p, c in zip(probs, composition):
            probability *= p**c

        expected_raw += probability * base_mults[winner]

    scale = RTP / expected_raw
    return {emoji: round(scale * base, 2) for emoji, (_, _, base) in zip(_POPULATION, SYMBOLS)}


PAYOUTS = _build_payouts()


def draw_grid() -> list[str]:
    return random.choices(_POPULATION, weights=_WEIGHTS, k=GRID_SIZE)


def evaluate(grid: list[str], bet: int) -> tuple[int, str | None]:
    counts: dict[str, int] = {}
    for symbol in grid:
        counts[symbol] = counts.get(symbol, 0) + 1

    qualifying = [s for s, c in counts.items() if c >= MATCH_THRESHOLD]
    if not qualifying:
        return 0, None

    winner = max(qualifying, key=lambda s: PAYOUTS[s])
    return int(bet * PAYOUTS[winner]), winner


def render_grid(grid: list[str], revealed: set[int]) -> str:
    cells = [grid[i] if i in revealed else HIDDEN for i in range(GRID_SIZE)]
    return "\n".join(" ".join(cells[r * 3 : r * 3 + 3]) for r in range(3))


class ScratchcardView(ui.LayoutView):
    def __init__(self, bet: int):
        super().__init__(timeout=None)
        self.bet = bet
        self.container, self.text = game_container(
            "🎫 Scratchcard", f"{render_grid([HIDDEN] * GRID_SIZE, set())}\n\n**Bet:** {fmt(bet)}\n🎫 Scratching..."
        )
        self.add_item(self.container)

    def update(self, grid: list[str], revealed: set[int], *, footer: str | None = None, color: discord.Color | None = None):
        body = f"{render_grid(grid, revealed)}\n\n**Bet:** {fmt(self.bet)}"
        if footer:
            body += f"\n{footer}"
        self.text.content = f"## 🎫 Scratchcard\n{body}"
        if color:
            self.container.accent_colour = color


class Scratchcard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="scratchcard", aliases=["scratch"], description="Scratch off a 3x3 card — match 4+ symbols to win."
    )
    @game_enabled("scratchcard")
    async def scratchcard(self, ctx: commands.Context, bet: str):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        grid = draw_grid()
        view = ScratchcardView(amount)
        message = await ctx.send(view=view)

        order = list(range(GRID_SIZE))
        random.shuffle(order)
        revealed: set[int] = set()
        for index in order:
            await asyncio.sleep(REVEAL_DELAY)
            revealed.add(index)
            view.update(grid, revealed, footer="🎫 Scratching...")
            await limited_edit(message, view=view)

        payout, winner = evaluate(grid, amount)
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        won = payout > 0
        if won:
            footer = f"🎉 **4x {winner} matched!** {PAYOUTS[winner]:g}x → Payout {fmt(payout)}"
        else:
            footer = "😢 No match — better luck next time."

        view.update(grid, revealed, footer=footer, color=discord.Color.green() if won else discord.Color.red())
        await limited_edit(message, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Scratchcard(bot))
