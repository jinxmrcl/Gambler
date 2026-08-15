import asyncio
import math
import random
import time

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, StaticView, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

RTP = 1 - HOUSE_EDGE
MAX_CRASH = 1_000.0
TICK_DELAY = 0.5
GROWTH_RATE = 0.20


def roll_crash_point() -> float:
    r = random.random()
    crash_point = RTP / (1 - r)
    return min(max(1.0, crash_point), MAX_CRASH)


def multiplier_at(elapsed_seconds: float) -> float:
    return math.exp(GROWTH_RATE * elapsed_seconds)


def _spectator_body(player_name: str, bet: int, multiplier: float, footer: str | None = None) -> str:
    body = f"👀 **{player_name}** is playing — Bet: {fmt(bet)}\n\n## {multiplier:.2f}x"
    if footer:
        body += f"\n{footer}"
    return body


class CashOutButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Cash Out", emoji="💸")

    async def callback(self, interaction: discord.Interaction):
        await self.view.cash_out(interaction)


class CrashView(ui.LayoutView):
    def __init__(self, cog: "Crash", ctx: commands.Context, bet: int):
        super().__init__(timeout=90)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.current_multiplier = 1.0
        self.finished = False
        self.message: discord.Message | None = None
        self.spectator_message: discord.Message | None = None

        self.container, self.text = game_container("🚀 Crash", f"**Bet:** {fmt(bet)}\n\n## 1.00x\n🚀 Launching...")
        self.cash_out_button = CashOutButton()
        row = ui.ActionRow()
        row.add_item(self.cash_out_button)
        self.container.add_item(row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your round!", ephemeral=True)
            return False
        return True

    def render(self, *, footer: str | None = None, color: discord.Color | None = None):
        body = f"**Bet:** {fmt(self.bet)}\n\n## {self.current_multiplier:.2f}x"
        if footer:
            body += f"\n{footer}"
        self.text.content = f"## 🚀 Crash\n{body}"
        if color:
            self.container.accent_colour = color

    async def _update_spectator(self, footer: str | None = None, *, color: discord.Color | None = None):
        if not self.spectator_message:
            return
        view = StaticView(
            "🚀 Crash — Spectator",
            _spectator_body(self.ctx.author.display_name, self.bet, self.current_multiplier, footer),
            color=color,
        )
        try:
            await limited_edit(self.spectator_message, view=view)
        except discord.HTTPException:
            pass

    async def cash_out(self, interaction: discord.Interaction):
        if self.finished:
            return
        self.finished = True
        self.cash_out_button.disabled = True

        payout = int(self.bet * self.current_multiplier)
        await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)

        footer = f"🎉 Cashed out at {self.current_multiplier:.2f}x! Payout: {fmt(payout)}"
        self.render(footer=footer, color=discord.Color.green())
        await interaction.response.edit_message(view=self)
        await self._update_spectator(footer, color=discord.Color.green())

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self.cash_out_button.disabled = True
        if self.message:
            await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, 0)
            self.render(footer="⏱️ Round timed out — treated as a crash.", color=discord.Color.red())
            await limited_edit(self.message, view=self)
            await self._update_spectator("⏱️ Round timed out.", color=discord.Color.red())


class Crash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _spectator_channel(self, ctx: commands.Context):
        if not ctx.guild:
            return None
        channel_id = await self.bot.db.get_crash_channel(ctx.guild.id)
        if not channel_id or channel_id == ctx.channel.id:
            return None
        return ctx.guild.get_channel(channel_id)

    @commands.hybrid_command(
        name="crash", description="Watch the multiplier climb and cash out before it crashes."
    )
    @app_commands.describe(bet="Bet (a number, 'half', 'all', or e.g. '50%')")
    @game_enabled("crash")
    async def crash(self, ctx: commands.Context, bet: str):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        crash_point = roll_crash_point()
        view = CrashView(self, ctx, amount)
        message = await ctx.send(view=view)
        view.message = message

        spectator_channel = await self._spectator_channel(ctx)
        if spectator_channel:
            try:
                spectator_view = StaticView("🚀 Crash — Spectator", _spectator_body(ctx.author.display_name, amount, 1.0))
                view.spectator_message = await spectator_channel.send(view=spectator_view)
            except discord.HTTPException:
                view.spectator_message = None

        start = time.monotonic()
        while not view.finished:
            await asyncio.sleep(TICK_DELAY)
            if view.finished:
                break

            elapsed = time.monotonic() - start
            multiplier = multiplier_at(elapsed)

            if multiplier >= crash_point:
                view.current_multiplier = crash_point
                view.finished = True
                view.cash_out_button.disabled = True
                view.render(
                    footer=f"💥 Crashed at {crash_point:.2f}x! You lost {fmt(amount)}.",
                    color=discord.Color.red(),
                )
                await limited_edit(message, view=view)
                await self.bot.db.record_game_result(ctx.author.id, amount, 0)
                await view._update_spectator(f"💥 Crashed at {crash_point:.2f}x!", color=discord.Color.red())
                break

            view.current_multiplier = multiplier
            view.render(footer="🚀 Climbing — cash out anytime!")
            await limited_edit(message, view=view)
            await view._update_spectator()


async def setup(bot: commands.Bot):
    await bot.add_cog(Crash(bot))
