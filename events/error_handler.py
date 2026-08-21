import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import ChannelNotAllowed, GameDisabled, WrongGambleChannel
from utils.economy import BetError

log = logging.getLogger("gambler")

# Errors where showing the correct command syntax actually helps the user fix their input.
_SYNTAX_HINT_ERRORS = (
    commands.MissingRequiredArgument,
    commands.RangeError,
    commands.BadLiteralArgument,
    commands.UserNotFound,
    commands.MemberNotFound,
    commands.BadArgument,
)


def _usage_hint(ctx: commands.Context) -> str | None:
    if not ctx.command:
        return None
    prefix = ctx.prefix or ctx.bot.prefix
    return f"{prefix}{ctx.command.qualified_name} {ctx.command.signature}".strip()


def _friendly_message(error: Exception, ctx: commands.Context | None = None) -> str | None:
    if isinstance(error, (BetError, GameDisabled, ChannelNotAllowed, WrongGambleChannel)):
        return error.args[0] if error.args else str(error)
    if isinstance(error, commands.MissingRequiredArgument):
        text = f"Missing argument: `{error.param.name}`."
    elif isinstance(error, commands.RangeError):
        text = str(error).capitalize() + "."
    elif isinstance(error, commands.BadLiteralArgument):
        choices = ", ".join(f"`{c}`" for c in error.literals)
        text = f"Invalid value for `{error.param.name}`. Choose one of: {choices}."
    elif isinstance(error, (commands.UserNotFound, commands.MemberNotFound)):
        text = (
            f"Couldn't find a user matching `{error.argument}`. "
            "Try @mentioning them, or use their exact user ID — they need to share a "
            "server with the bot (or have interacted with it before) to be found by name."
        )
    elif isinstance(error, commands.BadArgument):
        text = "One of the provided values is invalid."
    elif isinstance(error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
        return f"That's on cooldown. Try again in {error.retry_after:.1f}s."
    elif isinstance(error, (commands.MissingPermissions, app_commands.MissingPermissions)):
        return "You're missing the required permission (Administrator)."
    elif isinstance(error, commands.CommandNotFound):
        return None
    elif isinstance(error, commands.UserInputError):
        text = "One of the provided values is invalid."
    else:
        return None

    if ctx and isinstance(error, _SYNTAX_HINT_ERRORS):
        hint = _usage_hint(ctx)
        if hint:
            text += f"\nUsage: `{hint}`"
    return text


async def _view_on_error(view: discord.ui.View, interaction: discord.Interaction, error: Exception, item) -> None:
    log.exception("Unhandled error in view %r for item %r", view, item, exc_info=error)
    message = _friendly_message(error) or "Something went wrong. Please try again later."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"⚠️ {message}", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ {message}", ephemeral=True)
    except (discord.HTTPException, aiohttp.ClientError, ConnectionError, OSError):
        log.warning("Failed to send error message for view %r", view)


class ErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.tree.on_error = self.on_app_command_error
        discord.ui.view.BaseView.on_error = _view_on_error

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        error = getattr(error, "original", error)
        message = _friendly_message(error, ctx)
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
