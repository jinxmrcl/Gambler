import asyncio
import logging
import math
import random
import time

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import BetError, HOUSE_EDGE, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit, limited_send

log = logging.getLogger("gambler")

RTP = 1 - HOUSE_EDGE
MAX_CRASH = 1_000.0
TICK_DELAY = 0.5
GROWTH_RATE = 0.20
AUTO_ERROR_BACKOFF = 10.0

BETTING_WINDOW = 20.0
BETTING_TICK = 2.0
RESULT_PAUSE = 5.0
ROUND_CYCLE = 60.0
PARTICIPANT_DISPLAY_LIMIT = 15


def roll_crash_point() -> float:
    r = random.random()
    crash_point = RTP / (1 - r)
    return min(max(1.0, crash_point), MAX_CRASH)


def multiplier_at(elapsed_seconds: float) -> float:
    return math.exp(GROWTH_RATE * elapsed_seconds)


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


class Participant:
    __slots__ = ("user_id", "name", "bet", "cashed_out", "cashout_multiplier")

    def __init__(self, user_id: int, name: str, bet: int):
        self.user_id = user_id
        self.name = name
        self.bet = bet
        self.cashed_out = False
        self.cashout_multiplier: float | None = None


class AutoRound:
    def __init__(self):
        self.phase = "betting"  # betting -> live -> result
        self.participants: dict[int, Participant] = {}
        self.crash_point = 0.0
        self.current_multiplier = 1.0
        self.betting_end = 0.0


def _participants_text(participants: dict[int, Participant]) -> str:
    if not participants:
        return "*No players yet — be the first!*"
    items = list(participants.values())
    lines = []
    for p in items[:PARTICIPANT_DISPLAY_LIMIT]:
        if p.cashed_out:
            lines.append(f"🎉 {p.name} — {fmt(p.bet)} → cashed out at {p.cashout_multiplier:.2f}x")
        else:
            lines.append(f"👤 {p.name} — {fmt(p.bet)}")
    if len(items) > PARTICIPANT_DISPLAY_LIMIT:
        lines.append(f"*+{len(items) - PARTICIPANT_DISPLAY_LIMIT} more*")
    return "\n".join(lines)


def _results_text(participants: dict[int, Participant]) -> str:
    if not participants:
        return "*Nobody played this round.*"
    items = list(participants.values())
    lines = []
    for p in items[:PARTICIPANT_DISPLAY_LIMIT]:
        if p.cashed_out:
            payout = int(p.bet * p.cashout_multiplier)
            lines.append(f"🎉 {p.name} cashed out at {p.cashout_multiplier:.2f}x — won {fmt(payout)}")
        else:
            lines.append(f"💥 {p.name} lost {fmt(p.bet)}")
    if len(items) > PARTICIPANT_DISPLAY_LIMIT:
        lines.append(f"*+{len(items) - PARTICIPANT_DISPLAY_LIMIT} more*")
    return "\n".join(lines)


class PlaceBetButton(ui.Button):
    def __init__(self, cog: "Crash", guild_id: int, *, disabled: bool = False):
        super().__init__(style=discord.ButtonStyle.success, label="Place Bet", emoji="💰", disabled=disabled)
        self.cog = cog
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BetModal(self.cog, self.guild_id))


class AutoCashOutButton(ui.Button):
    def __init__(self, cog: "Crash", guild_id: int, *, disabled: bool = False):
        super().__init__(style=discord.ButtonStyle.danger, label="Cash Out", emoji="💸", disabled=disabled)
        self.cog = cog
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        await self.cog.auto_cash_out(interaction, self.guild_id)


class BetModal(ui.Modal, title="Place your Crash bet"):
    amount = ui.TextInput(label="Bet amount", placeholder="e.g. 500, half, 25%, all", max_length=12)

    def __init__(self, cog: "Crash", guild_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.place_bet(interaction, self.guild_id, self.amount.value)


class AutoCrashView(ui.LayoutView):
    def __init__(
        self, cog: "Crash", guild_id: int, title: str, body: str, *,
        color: discord.Color | None = None, bet_disabled: bool = False,
        show_cashout: bool = False, cashout_disabled: bool = True,
    ):
        super().__init__(timeout=None)
        container, _ = game_container(title, body, color=color)
        row = ui.ActionRow()
        row.add_item(PlaceBetButton(cog, guild_id, disabled=bet_disabled))
        if show_cashout:
            row.add_item(AutoCashOutButton(cog, guild_id, disabled=cashout_disabled))
        container.add_item(row)
        self.add_item(container)


class Crash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._auto_tasks: dict[int, asyncio.Task] = {}
        self._rounds: dict[int, AutoRound] = {}
        self._messages: dict[int, discord.Message] = {}

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
        self._rounds.pop(guild_id, None)
        self._messages.pop(guild_id, None)

    def _render_view(self, guild_id: int, round_: AutoRound) -> AutoCrashView:
        if round_.phase == "betting":
            remaining = max(0, int(round_.betting_end - time.monotonic()) + 1)
            body = f"## 🕒 Next round in {remaining}s\n{_participants_text(round_.participants)}"
            return AutoCrashView(self, guild_id, "🚀 Crash", body, bet_disabled=False, show_cashout=False)
        elif round_.phase == "live":
            body = f"## {round_.current_multiplier:.2f}x\n🚀 Climbing — cash out anytime!\n\n{_participants_text(round_.participants)}"
            return AutoCrashView(
                self, guild_id, "🚀 Crash — LIVE", body,
                bet_disabled=True, show_cashout=True, cashout_disabled=False,
            )
        else:
            body = (
                f"## 💥 Crashed at {round_.crash_point:.2f}x!\n{_results_text(round_.participants)}\n\n"
                f"-# Next round starting soon..."
            )
            return AutoCrashView(self, guild_id, "🚀 Crash", body, color=discord.Color.red(), bet_disabled=True)

    async def _send_or_edit(self, guild_id: int, channel, view: AutoCrashView) -> None:
        message = self._messages.get(guild_id)
        if message is None:
            message = await limited_send(channel, view=view)
            self._messages[guild_id] = message
        else:
            await limited_edit(message, view=view)

    async def _refresh_message(self, guild_id: int) -> None:
        round_ = self._rounds.get(guild_id)
        message = self._messages.get(guild_id)
        if not round_ or not message:
            return
        try:
            await limited_edit(message, view=self._render_view(guild_id, round_))
        except discord.HTTPException:
            pass

    async def place_bet(self, interaction: discord.Interaction, guild_id: int, raw_amount: str):
        round_ = self._rounds.get(guild_id)
        if not round_ or round_.phase != "betting":
            await interaction.response.send_message(
                "⚠️ Betting is closed for this round — wait for the next one!", ephemeral=True
            )
            return
        if interaction.user.id in round_.participants:
            await interaction.response.send_message("⚠️ You already placed a bet this round!", ephemeral=True)
            return

        await self.bot.db.ensure_user(interaction.user.id, self.bot.starting_balance)
        try:
            amount = await resolve_bet(self.bot, interaction.user.id, raw_amount)
        except BetError as e:
            await interaction.response.send_message(f"⚠️ {e.message}", ephemeral=True)
            return

        if not round_ or round_.phase != "betting" or interaction.user.id in round_.participants:
            await interaction.response.send_message("⚠️ Betting closed just before your bet went through!", ephemeral=True)
            return

        await self.bot.db.update_balance(interaction.user.id, -amount)
        round_.participants[interaction.user.id] = Participant(interaction.user.id, interaction.user.display_name, amount)

        await interaction.response.send_message(f"✅ Bet placed: {fmt(amount)}. Good luck! 🚀", ephemeral=True)
        await self._refresh_message(guild_id)

    async def auto_cash_out(self, interaction: discord.Interaction, guild_id: int):
        round_ = self._rounds.get(guild_id)
        if not round_ or round_.phase != "live":
            await interaction.response.send_message("⚠️ There's no live round to cash out of right now.", ephemeral=True)
            return
        participant = round_.participants.get(interaction.user.id)
        if not participant:
            await interaction.response.send_message("⚠️ You didn't place a bet this round.", ephemeral=True)
            return
        if participant.cashed_out:
            await interaction.response.send_message("⚠️ You already cashed out this round!", ephemeral=True)
            return

        participant.cashed_out = True
        participant.cashout_multiplier = round_.current_multiplier
        payout = int(participant.bet * round_.current_multiplier)
        await self.bot.db.update_balance(interaction.user.id, payout)
        await self.bot.db.record_game_result(interaction.user.id, participant.bet, payout)

        await interaction.response.send_message(
            f"🎉 Cashed out at {round_.current_multiplier:.2f}x — you won {fmt(payout)}!", ephemeral=True
        )
        await self._refresh_message(guild_id)

    async def _auto_loop(self, guild_id: int, channel_id: int):
        await self.bot.wait_until_ready()

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                log.warning("[crash] auto channel %s (guild %s) not found, stopping", channel_id, guild_id)
                return

        while True:
            cycle_start = time.monotonic()
            try:
                await self._run_auto_round(guild_id, channel)
            except discord.NotFound:
                log.warning("[crash] auto message in channel %s was deleted, stopping", channel_id)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("[crash] auto round failed in channel %s", channel_id)
                await asyncio.sleep(AUTO_ERROR_BACKOFF)
                continue

            elapsed = time.monotonic() - cycle_start
            await asyncio.sleep(max(0.0, ROUND_CYCLE - elapsed))

    async def _run_auto_round(self, guild_id: int, channel):
        round_ = AutoRound()
        self._rounds[guild_id] = round_

        round_.betting_end = time.monotonic() + BETTING_WINDOW
        while time.monotonic() < round_.betting_end:
            await self._send_or_edit(guild_id, channel, self._render_view(guild_id, round_))
            await asyncio.sleep(BETTING_TICK)

        round_.phase = "live"
        round_.crash_point = roll_crash_point()
        start = time.monotonic()

        while True:
            await asyncio.sleep(TICK_DELAY)
            elapsed = time.monotonic() - start
            multiplier = multiplier_at(elapsed)

            if multiplier >= round_.crash_point:
                round_.current_multiplier = round_.crash_point
                break

            round_.current_multiplier = multiplier
            await self._send_or_edit(guild_id, channel, self._render_view(guild_id, round_))

        round_.phase = "result"
        for p in round_.participants.values():
            if not p.cashed_out:
                await self.bot.db.record_game_result(p.user_id, p.bet, 0)

        await self._send_or_edit(guild_id, channel, self._render_view(guild_id, round_))
        await asyncio.sleep(RESULT_PAUSE)
        self._rounds.pop(guild_id, None)

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Crash(bot))
