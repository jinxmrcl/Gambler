from discord.ext import commands


class GameDisabled(commands.CheckFailure):
    def __init__(self, game: str):
        self.game = game
        super().__init__(f"The `{game}` game is disabled on this server.")


class ChannelNotAllowed(commands.CheckFailure):
    def __init__(self):
        super().__init__("Games can't be played in this channel.")


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
