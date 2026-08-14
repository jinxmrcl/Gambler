import math
import random
from math import comb

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

POOL_SIZE = 25
DRAWN_COUNT = 10
RTP = 1 - HOUSE_EDGE


def hypergeometric(picks: int, hits: int) -> float:
    if hits > DRAWN_COUNT or hits > picks:
        return 0.0
    remaining_needed = DRAWN_COUNT - hits
    remaining_pool = POOL_SIZE - picks
    if remaining_needed < 0 or remaining_needed > remaining_pool:
        return 0.0
    return comb(picks, hits) * comb(remaining_pool, remaining_needed) / comb(POOL_SIZE, DRAWN_COUNT)


def build_paytable(picks: int) -> dict[int, float]:
    threshold = max(1, math.ceil(picks * 0.4))
    paying_hits = [h for h in range(threshold, picks + 1) if hypergeometric(picks, h) > 0]
    if not paying_hits:
        return {}

    weights = {h: h**2.5 for h in paying_hits}
    total_weight = sum(weights.values())

    return {
        h: (RTP * weights[h]) / (hypergeometric(picks, h) * total_weight)
        for h in paying_hits
    }


class NumberSelect(ui.Select):
    def __init__(self, picks: int):
        options = [discord.SelectOption(label=str(n)) for n in range(1, POOL_SIZE + 1)]
        super().__init__(
            placeholder=f"Pick exactly {picks} numbers (1-{POOL_SIZE})",
            min_values=picks,
            max_values=picks,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.resolve(interaction, {int(v) for v in self.values})


class KenoView(ui.LayoutView):
    def __init__(self, cog: "Keno", ctx: commands.Context, bet: int, picks: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.picks = picks
        self.paytable = build_paytable(picks)
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container(
            "🔢 Keno",
            f"**Bet:** {fmt(bet)}\nPick exactly **{picks}** numbers from 1-{POOL_SIZE} below.",
        )
        self.select = NumberSelect(picks)
        row = ui.ActionRow()
        row.add_item(self.select)
        self.container.add_item(row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    async def resolve(self, interaction: discord.Interaction, chosen: set[int]):
        if self.finished:
            return
        self.finished = True
        self.select.disabled = True

        drawn = set(random.sample(range(1, POOL_SIZE + 1), DRAWN_COUNT))
        hits = len(chosen & drawn)
        multiplier = self.paytable.get(hits, 0.0)
        payout = int(self.bet * multiplier)
        if payout:
            await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)

        won = payout > 0
        lines = [
            f"**Your numbers:** {', '.join(str(n) for n in sorted(chosen))}",
            f"**Drawn numbers:** {', '.join(str(n) for n in sorted(drawn))}",
            f"**Hits:** {hits}  •  **Multiplier:** {multiplier:g}x  •  **Payout:** {fmt(payout)}",
        ]
        self.text.content = "## 🔢 Keno\n" + "\n".join(lines)
        self.container.accent_colour = discord.Color.green() if won else discord.Color.red()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self.select.disabled = True
        if self.message:
            await self.cog.bot.db.update_balance(self.ctx.author.id, self.bet)
            self.text.content = "## 🔢 Keno\n⏱️ No selection made — bet was refunded."
            self.container.accent_colour = discord.Color.greyple()
            await limited_edit(self.message, view=self)


class Keno(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="keno", description="Pick numbers and hope for hits in the draw.")
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        picks="How many numbers you pick (1-10)",
    )
    @game_enabled("keno")
    async def keno(self, ctx: commands.Context, bet: str, picks: commands.Range[int, 1, 10] = 5):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        view = KenoView(self, ctx, amount, picks)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Keno(bot))
