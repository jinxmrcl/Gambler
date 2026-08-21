import discord
from discord import app_commands
from discord.ext import commands


class GameDisabled(commands.CheckFailure):
    def __init__(self, game: str):
        self.game = game
        super().__init__(f"The `{game}` game is disabled on this server.")


class ChannelNotAllowed(commands.CheckFailure):
    def __init__(self):
        super().__init__("Games can't be played in this channel.")


class WrongGambleChannel(commands.CheckFailure):
    def __init__(self, channel_id: int):
        self.channel_id = channel_id
        super().__init__(f"This bot can only be used in <#{channel_id}>.")


def admin_only():
    async def predicate(ctx: commands.Context) -> bool:
        if await ctx.bot.is_owner(ctx.author):
            return True
        if isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator:
            return True
        raise commands.MissingPermissions(["administrator"])

    return commands.check(predicate)


def app_admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if await interaction.client.is_owner(interaction.user):
            return True
        if interaction.permissions.administrator:
            return True
        raise app_commands.MissingPermissions(["administrator"])

    return app_commands.check(predicate)


def game_enabled(game: str):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return True
        disabled, allowed_channels = await ctx.bot.db.get_guild_settings(ctx.guild.id)
        if game in disabled:
            raise GameDisabled(game)
        if allowed_channels and ctx.channel.id not in allowed_channels:
            raise ChannelNotAllowed()
        return True

    return commands.check(predicate)


async def gamble_channel_check(ctx: commands.Context) -> bool:
    if ctx.guild is None:
        return True
    if await ctx.bot.is_owner(ctx.author):
        return True
    if isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator:
        return True

    channel_id = await ctx.bot.db.get_gamble_channel(ctx.guild.id)
    if channel_id is None or ctx.channel.id == channel_id:
        return True

    raise WrongGambleChannel(channel_id)
