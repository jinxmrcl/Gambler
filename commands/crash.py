import asyncio
import logging
import math
import random
import time

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit, limited_send

log = logging.getLogger("gambler")

RTP = 1 - HOUSE_EDGE
MAX_CRASH = 1_000.0
TICK_DELAY = 0.5
GROWTH_RATE = 0.20
AUTO_ROUND_PAUSE = 4.0
AUTO_ERROR_BACKOFF = 10.0


def roll_crash_point() -> float:
    r = random.random()
    crash_point = RTP / (1 - r)
    return min(max(1.0, crash_point), MAX_CRASH)


def multiplier_at(elapsed_seconds: float) -> float:
    return math.exp(GROWTH_RATE * elapsed_seconds)


def _auto_body(multiplier: float, footer: str) -> str:
    return f"## {multiplier:.2f}x\n{footer}\n-# Autoplay — set with `/set-crashchannel`"


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

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self.cash_out_button.disabled = True
        if self.message:
            await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, 0)
            self.render(footer="⏱️ Round timed out — treated as a crash.", color=discord.Color.red())
            await limited_edit(self.message, view=self)


class Crash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._auto_tasks: dict[int, asyncio.Task] = {}

    async def cog_load(self):
        try:
            channels = await self.bot.db.all_crash_channels()
        except Exception:
            log.exception("[crash] failed to load configured crash channels")
            channels = []
        for guild_id, channel_id in channels:
            self.start_auto_round(guild_id, channel_id)

    def cog_unload(self):
        for task in self._auto_tasks.values():
            task.cancel()
        self._auto_tasks.clear()

    def start_auto_round(self, guild_id: int, channel_id: int):
        self.stop_auto_round(guild_id)
        self._auto_tasks[guild_id] = asyncio.create_task(self._auto_loop(guild_id, channel_id))

    def stop_auto_round(self, guild_id: int):
        task = self._auto_tasks.pop(guild_id, None)
        if task:
            task.cancel()

    async def _auto_loop(self, guild_id: int, channel_id: int):
        await self.bot.wait_until_ready()

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                log.warning("[crash] auto channel %s (guild %s) not found, stopping", channel_id, guild_id)
                return

        try:
            message = await limited_send(channel, view=_AutoCrashView(1.0, "🚀 Launching..."))
        except discord.HTTPException:
            log.warning("[crash] could not post initial auto message in channel %s", channel_id)
            return

        while True:
            try:
                await self._play_auto_round(message)
            except discord.NotFound:
                log.warning("[crash] auto message in channel %s was deleted, stopping", channel_id)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("[crash] auto round failed in channel %s", channel_id)
                await asyncio.sleep(AUTO_ERROR_BACKOFF)

            await asyncio.sleep(AUTO_ROUND_PAUSE)

    async def _play_auto_round(self, message: discord.Message):
        crash_point = roll_crash_point()
        start = time.monotonic()

        while True:
            await asyncio.sleep(TICK_DELAY)
            elapsed = time.monotonic() - start
            multiplier = multiplier_at(elapsed)

            if multiplier >= crash_point:
                view = _AutoCrashView(crash_point, f"💥 Crashed at {crash_point:.2f}x!", color=discord.Color.red())
                await limited_edit(message, view=view)
                return

            view = _AutoCrashView(multiplier, "🚀 Climbing...")
            await limited_edit(message, view=view)

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
                break

            view.current_multiplier = multiplier
            view.render(footer="🚀 Climbing — cash out anytime!")
            await limited_edit(message, view=view)


class _AutoCrashView(ui.LayoutView):
    def __init__(self, multiplier: float, footer: str, *, color: discord.Color | None = None):
        super().__init__(timeout=None)
        container, _ = game_container("🚀 Crash — Live", _auto_body(multiplier, footer), color=color)
        self.add_item(container)


async def setup(bot: commands.Bot):
    await bot.add_cog(Crash(bot))
