import logging
from collections import defaultdict
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.economy import StaticView
from utils.checks import admin_only

log = logging.getLogger("gambler")

GAMES = (
    "blackjack", "mines", "hilo", "plinko", "limbo", "keno", "slots", "roulette", "dice", "soloflip",
    "scratchcard", "horserace", "baccarat",
)
GameName = Literal[
    "blackjack", "mines", "hilo", "plinko", "limbo", "keno", "slots", "roulette", "dice", "soloflip",
    "scratchcard", "horserace", "baccarat",
]

GAMBLE_CHANNEL_SLOWMODE_LOW = 2
GAMBLE_CHANNEL_SLOWMODE_HIGH = 5
GAMBLE_TRAFFIC_WINDOW_SECONDS = 60
GAMBLE_HIGH_TRAFFIC_PER_MIN = 20
_MANAGED_SLOWMODES = {0, GAMBLE_CHANNEL_SLOWMODE_LOW, GAMBLE_CHANNEL_SLOWMODE_HIGH}


async def _set_managed_slowmode(channel: discord.TextChannel, seconds: int, reason: str) -> bool:
    """Only ever adjusts a slowmode value this feature itself set previously (or an
    unset channel) — an admin's own custom slowmode is never touched."""
    if channel.slowmode_delay == seconds:
        return False
    if channel.slowmode_delay not in _MANAGED_SLOWMODES:
        return False
    try:
        await channel.edit(slowmode_delay=seconds, reason=reason)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


async def _apply_gamble_channel_slowmode(channel: discord.TextChannel) -> bool:
    return await _set_managed_slowmode(
        channel, GAMBLE_CHANNEL_SLOWMODE_LOW, "Gambler: auto slowmode for the restricted gamble channel"
    )


async def _clear_gamble_channel_slowmode(channel: discord.TextChannel) -> None:
    await _set_managed_slowmode(channel, 0, "Gambler: gamble channel restriction removed")


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._gamble_channel_msg_counts: dict[int, int] = defaultdict(int)
        self.gamble_traffic_loop.start()

    def cog_unload(self):
        self.gamble_traffic_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        db = await self.bot.db.get(message.guild.id)
        gamble_channel_id = await db.get_gamble_channel()
        if gamble_channel_id and message.channel.id == gamble_channel_id:
            self._gamble_channel_msg_counts[message.guild.id] += 1

    @tasks.loop(seconds=GAMBLE_TRAFFIC_WINDOW_SECONDS)
    async def gamble_traffic_loop(self):
        counts = self._gamble_channel_msg_counts
        self._gamble_channel_msg_counts = defaultdict(int)
        for guild_id, count in counts.items():
            try:
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    continue
                db = await self.bot.db.get(guild_id)
                channel_id = await db.get_gamble_channel()
                if not channel_id:
                    continue
                channel = guild.get_channel(channel_id)
                if not isinstance(channel, discord.TextChannel):
                    continue

                per_minute = count * (60 / GAMBLE_TRAFFIC_WINDOW_SECONDS)
                if per_minute >= GAMBLE_HIGH_TRAFFIC_PER_MIN:
                    target, label = GAMBLE_CHANNEL_SLOWMODE_HIGH, "high"
                else:
                    target, label = GAMBLE_CHANNEL_SLOWMODE_LOW, "slow"
                await _set_managed_slowmode(channel, target, f"Gambler: auto slowmode ({label} traffic)")
            except Exception:
                log.exception("[gamble-traffic] failed to evaluate slowmode for guild %s", guild_id)

    @gamble_traffic_loop.before_loop
    async def before_gamble_traffic_loop(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="settings", description="[Admin] Shows the current server settings.")
    @admin_only()
    @commands.guild_only()
    async def settings(self, ctx: commands.Context):
        db = await self.bot.db.get(ctx.guild.id)
        disabled, allowed_channels = await db.get_guild_settings()
        gamble_channel_id = await db.get_gamble_channel()
        updates_channel_id = await db.get_updates_channel()

        disabled_text = ", ".join(f"`{g}`" for g in sorted(disabled)) or "none"
        if allowed_channels:
            channels_text = ", ".join(f"<#{c}>" for c in allowed_channels)
        else:
            channels_text = "all channels"
        gamble_channel_text = f"<#{gamble_channel_id}>" if gamble_channel_id else "*not restricted*"
        updates_channel_text = f"<#{updates_channel_id}>" if updates_channel_id else "*not set*"

        view = StaticView(
            "🛠️ Server Settings",
            f"**Disabled games:** {disabled_text}\n**Allowed game channels:** {channels_text}\n"
            f"**Bot restricted to:** {gamble_channel_text}\n"
            f"**Updates channel:** {updates_channel_text}",
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="togglegame", description="[Admin] Enable or disable a game on this server.")
    @app_commands.describe(game="Which game", enabled="Whether the game should be enabled")
    @admin_only()
    @commands.guild_only()
    async def togglegame(self, ctx: commands.Context, game: GameName, enabled: bool):
        db = await self.bot.db.get(ctx.guild.id)
        await db.set_game_disabled(game, not enabled)

        state = "enabled" if enabled else "disabled"
        view = StaticView("🛠️ Game Toggled", f"`{game}` is now **{state}** on this server.", color=discord.Color.blue())
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="togglechannel", description="[Admin] Restrict or unrestrict games to this channel."
    )
    @app_commands.describe(action="Add this channel to the allow-list, remove it, or clear the whole list")
    @admin_only()
    @commands.guild_only()
    async def togglechannel(self, ctx: commands.Context, action: Literal["add", "remove", "clear"]):
        db = await self.bot.db.get(ctx.guild.id)
        _, allowed_channels = await db.get_guild_settings()

        if action == "clear":
            allowed_channels = set()
            text = "Channel restrictions cleared — games can be played anywhere."
        elif action == "add":
            allowed_channels.add(ctx.channel.id)
            text = f"Games can now be played in {ctx.channel.mention}."
        else:
            allowed_channels.discard(ctx.channel.id)
            text = f"{ctx.channel.mention} removed from the allow-list."

        await db.set_allowed_channels(allowed_channels)

        view = StaticView("🛠️ Channel Settings", text, color=discord.Color.blue())
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="set-gamblechannel",
        description="[Admin] Restrict the entire bot to one channel (admins are always exempt).",
    )
    @app_commands.describe(
        channel="Channel to restrict the bot to (defaults to this channel)",
        clear="Remove the restriction so the bot works everywhere again",
    )
    @admin_only()
    @commands.guild_only()
    async def set_gamblechannel(
        self, ctx: commands.Context, channel: discord.TextChannel | None = None, clear: bool = False
    ):
        db = await self.bot.db.get(ctx.guild.id)
        if clear:
            old_channel_id = await db.get_gamble_channel()
            await db.clear_gamble_channel()
            if old_channel_id:
                old_channel = ctx.guild.get_channel(old_channel_id)
                if isinstance(old_channel, discord.TextChannel):
                    await _clear_gamble_channel_slowmode(old_channel)
            view = StaticView(
                "🛠️ Gamble Channel Cleared",
                "The bot can now be used in any channel again.",
                color=discord.Color.blue(),
            )
            await ctx.send(view=view)
            return

        target = channel or ctx.channel
        await db.set_gamble_channel(target.id)
        slowmode_note = ""
        if isinstance(target, discord.TextChannel) and await _apply_gamble_channel_slowmode(target):
            slowmode_note = (
                f"\n-# 🐢 Also enabled a {GAMBLE_CHANNEL_SLOWMODE_LOW}s channel slowmode there "
                f"(auto-raises to {GAMBLE_CHANNEL_SLOWMODE_HIGH}s if traffic gets heavy)."
            )
        view = StaticView(
            "🛠️ Gamble Channel Set",
            f"The bot can now only be used in {target.mention}.\n"
            f"-# Administrators are exempt from this restriction.{slowmode_note}",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="set-updateschannel",
        description="[Admin] Set a channel where new bot features get announced after a restart.",
    )
    @app_commands.describe(
        channel="Channel for feature announcements (defaults to this channel)",
        clear="Remove the updates channel so announcements stop",
    )
    @admin_only()
    @commands.guild_only()
    async def set_updateschannel(
        self, ctx: commands.Context, channel: discord.TextChannel | None = None, clear: bool = False
    ):
        db = await self.bot.db.get(ctx.guild.id)
        if clear:
            await db.clear_updates_channel()
            view = StaticView(
                "🆕 Updates Channel Cleared",
                "New feature announcements will no longer be posted anywhere.",
                color=discord.Color.blue(),
            )
            await ctx.send(view=view)
            return

        target = channel or ctx.channel
        await db.set_updates_channel(target.id)
        view = StaticView(
            "🆕 Updates Channel Set",
            f"When new commands/game modes are detected after a restart, they'll be announced in "
            f"{target.mention}.\n-# This is separate from git-pull and restart-health notifications.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
