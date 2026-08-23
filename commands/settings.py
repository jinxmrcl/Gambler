from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from utils.economy import StaticView
from utils.checks import admin_only

GAMES = (
    "blackjack", "mines", "hilo", "plinko", "limbo", "keno", "slots", "roulette", "dice", "soloflip",
    "scratchcard", "horserace", "baccarat",
)
GameName = Literal[
    "blackjack", "mines", "hilo", "plinko", "limbo", "keno", "slots", "roulette", "dice", "soloflip",
    "scratchcard", "horserace", "baccarat",
]


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
            await db.clear_gamble_channel()
            view = StaticView(
                "🛠️ Gamble Channel Cleared",
                "The bot can now be used in any channel again.",
                color=discord.Color.blue(),
            )
            await ctx.send(view=view)
            return

        target = channel or ctx.channel
        await db.set_gamble_channel(target.id)
        view = StaticView(
            "🛠️ Gamble Channel Set",
            f"The bot can now only be used in {target.mention}.\n"
            f"-# Administrators are exempt from this restriction.",
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
