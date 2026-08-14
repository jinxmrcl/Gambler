import discord
from discord import ui
from discord.ext import commands

CURRENCY = "🪙"
HOUSE_EDGE = 0.03


def fmt(amount: int) -> str:
    return f"{amount:,} {CURRENCY}"


class BetError(commands.CheckFailure):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def resolve_bet(bot: commands.Bot, user_id: int, raw: str, *, min_bet: int = 1) -> int:
    balance = await bot.db.get_balance(user_id)
    raw = raw.strip().lower()

    if raw in ("all", "max"):
        amount = balance
    elif raw == "half":
        amount = balance // 2
    elif raw.endswith("%"):
        try:
            pct = float(raw[:-1])
        except ValueError:
            raise BetError(f"`{raw}` is not a valid bet.")
        if pct <= 0 or pct > 100:
            raise BetError("Percentage must be between 0 and 100.")
        amount = int(balance * (pct / 100))
    else:
        try:
            amount = int(raw.replace(",", ""))
        except ValueError:
            raise BetError(f"`{raw}` is not a valid bet.")

    if amount < min_bet:
        raise BetError(f"The minimum bet is {fmt(min_bet)}.")
    if amount > balance:
        raise BetError(f"You don't have enough balance. Current: {fmt(balance)}.")

    return amount


async def resolve_display_name(bot: commands.Bot, guild: discord.Guild | None, user_id: int) -> str:
    if guild:
        member = guild.get_member(user_id)
        if member:
            return member.display_name

    user = bot.get_user(user_id)
    if user:
        return user.display_name

    try:
        user = await bot.fetch_user(user_id)
        return user.display_name
    except discord.NotFound:
        return f"<@{user_id}>"
    except discord.HTTPException:
        return f"<@{user_id}>"


def game_container(title: str, body: str = "", *, color: discord.Color | None = None) -> tuple[ui.Container, ui.TextDisplay]:
    heading = f"## {title}"
    text = ui.TextDisplay(f"{heading}\n{body}" if body else heading)
    container = ui.Container(text, accent_colour=color or discord.Color.blurple())
    return container, text


class StaticView(ui.LayoutView):

    def __init__(self, title: str, body: str = "", *, color: discord.Color | None = None):
        super().__init__(timeout=None)
        container, _ = game_container(title, body, color=color)
        self.add_item(container)
