import math
import random

import discord
from discord import ui
from discord.ext import commands

from database.db import InsufficientFunds
from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

RTP = 1 - HOUSE_EDGE
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


class ScratchTileButton(ui.Button):
    def __init__(self, index: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=HIDDEN, row=index // 3)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.view.reveal(interaction, self)


class ScratchcardView(ui.LayoutView):
    def __init__(self, cog: "Scratchcard", ctx: commands.Context, bet: int, grid: list[str]):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.grid = grid
        self.revealed: set[int] = set()
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container("🎫 Scratchcard", f"**Bet:** {fmt(bet)}\n🎫 Scratch a tile to reveal it!")
        self.tile_buttons = [ScratchTileButton(i) for i in range(GRID_SIZE)]

        for r in range(3):
            row = ui.ActionRow()
            for c in range(3):
                row.add_item(self.tile_buttons[r * 3 + c])
            self.container.add_item(row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your scratchcard!", ephemeral=True)
            return False
        return True

    def render(self, *, footer: str | None = None):
        body = f"**Bet:** {fmt(self.bet)}"
        if footer:
            body += f"\n{footer}"
        else:
            body += f"\n🎫 {len(self.revealed)}/{GRID_SIZE} tiles scratched"
        self.text.content = f"## 🎫 Scratchcard\n{body}"

    async def reveal(self, interaction: discord.Interaction, button: ScratchTileButton):
        if self.finished or button.disabled:
            return

        button.label = None
        button.emoji = self.grid[button.index]
        button.disabled = True
        self.revealed.add(button.index)

        if len(self.revealed) == GRID_SIZE:
            await self._finish(interaction)
        else:
            self.render()
            await interaction.response.edit_message(view=self)

    async def _finish(self, interaction: discord.Interaction):
        self.finished = True
        payout, winner = evaluate(self.grid, self.bet)
        if payout:
            await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)

        won = payout > 0
        if won:
            footer = f"🎉 **4x {winner} matched!** {PAYOUTS[winner]:g}x → Payout {fmt(payout)}"
        else:
            footer = "😢 No match — better luck next time."

        self.render(footer=footer)
        self.container.accent_colour = discord.Color.green() if won else discord.Color.red()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for button in self.tile_buttons:
            if not button.disabled:
                button.label = None
                button.emoji = self.grid[button.index]
                button.disabled = True
                self.revealed.add(button.index)

        payout, winner = evaluate(self.grid, self.bet)
        if payout:
            await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)

        won = payout > 0
        if won:
            footer = f"⏱️ Time's up — revealed automatically. 4x {winner} matched! {PAYOUTS[winner]:g}x → Payout {fmt(payout)}"
        else:
            footer = "⏱️ Time's up — revealed automatically. No match."

        self.render(footer=footer)
        self.container.accent_colour = discord.Color.green() if won else discord.Color.red()
        if self.message:
            await limited_edit(self.message, view=self)


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
        view = ScratchcardView(self, ctx, amount, grid)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Scratchcard(bot))
