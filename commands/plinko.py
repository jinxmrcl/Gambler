import random
from math import comb
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, StaticView, fmt, resolve_bet

RISK_EXPONENT = {"low": 0.3, "medium": 0.6, "high": 1.0}
RTP = 1 - HOUSE_EDGE


def build_multipliers(rows: int, risk: str) -> list[float]:
    exponent = RISK_EXPONENT[risk]
    probabilities = [comb(rows, i) / (2**rows) for i in range(rows + 1)]
    raw = [(1 / p) ** exponent for p in probabilities]
    expected_raw = sum(p * r for p, r in zip(probabilities, raw))
    scale = RTP / expected_raw
    return [round(scale * r, 2) for r in raw]


def drop_ball(rows: int) -> tuple[int, list[bool]]:
    path = [random.random() < 0.5 for _ in range(rows)]
    bucket = sum(path)
    return bucket, path


def render_path(path: list[bool]) -> str:
    return " ".join("↘️" if step else "↙️" for step in path)


def render_buckets(multipliers: list[float], landed: int) -> str:
    parts = []
    for i, mult in enumerate(multipliers):
        text = f"{mult:g}x"
        parts.append(f"[{text}]" if i == landed else text)
    return " ".join(parts)


class Plinko(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="plinko", description="Drop a ball through the Plinko board.")
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        risk="Risk level (affects how spread out the multipliers are)",
        rows="Number of rows (8-16, default: 12)",
    )
    @game_enabled("plinko")
    async def plinko(
        self,
        ctx: commands.Context,
        bet: str,
        risk: Literal["low", "medium", "high"] = "medium",
        rows: commands.Range[int, 8, 16] = 12,
    ):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        multipliers = build_multipliers(rows, risk)
        bucket, path = drop_ball(rows)
        multiplier = multipliers[bucket]
        payout = int(amount * multiplier)
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        won = payout > amount
        body = "\n".join(
            [
                f"**Bet:** {fmt(amount)}  •  **Risk:** {risk.capitalize()}  •  **Rows:** {rows}",
                f"**Ball path:** {render_path(path)}",
                f"**Board:** {render_buckets(multipliers, bucket)}",
                f"**Result:** Multiplier **{multiplier:g}x** → Payout {fmt(payout)}",
            ]
        )
        view = StaticView("🔴 Plinko", body, color=discord.Color.green() if won else discord.Color.red())
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Plinko(bot))
