from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from utils.economy import StaticView

GAMES = ("blackjack", "mines", "hilo", "plinko", "limbo", "keno", "slots", "roulette", "dice")
GameName = Literal["blackjack", "mines", "hilo", "plinko", "limbo", "keno", "slots", "roulette", "dice"]


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="settings", description="[Admin] Shows the current server settings.")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def settings(self, ctx: commands.Context):
        disabled, allowed_channels = await self.bot.db.get_guild_settings(ctx.guild.id)
        gamble_channel_id = await self.bot.db.get_gamble_channel(ctx.guild.id)

        disabled_text = ", ".join(f"`{g}`" for g in sorted(disabled)) or "none"
        if allowed_channels:
            channels_text = ", ".join(f"<#{c}>" for c in allowed_channels)
        else:
            channels_text = "all channels"
        gamble_channel_text = f"<#{gamble_channel_id}>" if gamble_channel_id else "*not restricted*"

        view = StaticView(
            "🛠️ Server Settings",
            f"**Disabled games:** {disabled_text}\n**Allowed game channels:** {channels_text}\n"
            f"**Bot restricted to:** {gamble_channel_text}",
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="togglegame", description="[Admin] Enable or disable a game on this server.")
    @app_commands.describe(game="Which game", enabled="Whether the game should be enabled")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def togglegame(self, ctx: commands.Context, game: GameName, enabled: bool):
        await self.bot.db.set_game_disabled(ctx.guild.id, game, not enabled)

        state = "enabled" if enabled else "disabled"
        view = StaticView("🛠️ Game Toggled", f"`{game}` is now **{state}** on this server.", color=discord.Color.blue())
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="togglechannel", description="[Admin] Restrict or unrestrict games to this channel."
    )
    @app_commands.describe(action="Add this channel to the allow-list, remove it, or clear the whole list")
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def togglechannel(self, ctx: commands.Context, action: Literal["add", "remove", "clear"]):
        _, allowed_channels = await self.bot.db.get_guild_settings(ctx.guild.id)

        if action == "clear":
            allowed_channels = set()
            text = "Channel restrictions cleared — games can be played anywhere."
        elif action == "add":
            allowed_channels.add(ctx.channel.id)
            text = f"Games can now be played in {ctx.channel.mention}."
        else:
            allowed_channels.discard(ctx.channel.id)
            text = f"{ctx.channel.mention} removed from the allow-list."

        await self.bot.db.set_allowed_channels(ctx.guild.id, allowed_channels)

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
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def set_gamblechannel(
        self, ctx: commands.Context, channel: discord.TextChannel | None = None, clear: bool = False
    ):
        if clear:
            await self.bot.db.clear_gamble_channel(ctx.guild.id)
            view = StaticView(
                "🛠️ Gamble Channel Cleared",
                "The bot can now be used in any channel again.",
                color=discord.Color.blue(),
            )
            await ctx.send(view=view)
            return

        target = channel or ctx.channel
        await self.bot.db.set_gamble_channel(ctx.guild.id, target.id)
        view = StaticView(
            "🛠️ Gamble Channel Set",
            f"The bot can now only be used in {target.mention}.\n"
            f"-# Administrators are exempt from this restriction.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))
