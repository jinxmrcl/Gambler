import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import ChannelNotAllowed, GameDisabled, WrongGambleChannel
from utils.economy import BetError

log = logging.getLogger("gambler")


def _friendly_message(error: Exception) -> str | None:
    if isinstance(error, (BetError, GameDisabled, ChannelNotAllowed, WrongGambleChannel)):
        return error.args[0] if error.args else str(error)
    if isinstance(error, commands.MissingRequiredArgument):
        return f"Missing argument: `{error.param.name}`."
    if isinstance(error, commands.BadLiteralArgument):
        choices = ", ".join(f"`{c}`" for c in error.literals)
        return f"Invalid value for `{error.param.name}`. Choose one of: {choices}."
    if isinstance(error, (commands.UserNotFound, commands.MemberNotFound)):
        return (
            f"Couldn't find a user matching `{error.argument}`. "
            "Try @mentioning them, or use their exact user ID — they need to share a "
            "server with the bot (or have interacted with it before) to be found by name."
        )
    if isinstance(error, commands.BadArgument):
        return "One of the provided values is invalid."
    if isinstance(error, commands.CommandOnCooldown):
        return f"That's on cooldown. Try again in {error.retry_after:.1f}s."
    if isinstance(error, (commands.MissingPermissions, app_commands.MissingPermissions)):
        return "You're missing the required permission (Administrator)."
    if isinstance(error, commands.CommandNotFound):
        return None
    if isinstance(error, commands.UserInputError):
        return "One of the provided values is invalid."
    return None


class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.tree.on_error = self.on_app_command_error

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        error = getattr(error, "original", error)
        message = _friendly_message(error)
        if message is None and not isinstance(error, commands.CommandNotFound):
            log.exception("Unexpected error in command %s", ctx.command, exc_info=error)
            message = "Something went wrong. Please try again later."
        if message:
            try:
                await ctx.send(f"⚠️ {message}")
            except (discord.HTTPException, aiohttp.ClientError, ConnectionError, OSError):
                log.warning("Failed to send error message for command %s", ctx.command)

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        error = getattr(error, "original", error)
        message = _friendly_message(error)
        if message is None:
            log.exception("Unexpected error in app command", exc_info=error)
            message = "Something went wrong. Please try again later."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"⚠️ {message}", ephemeral=True)
            else:
                await interaction.response.send_message(f"⚠️ {message}", ephemeral=True)
        except (discord.HTTPException, aiohttp.ClientError, ConnectionError, OSError):
            log.warning("Failed to send error message for app command")


async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
