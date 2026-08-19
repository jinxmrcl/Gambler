import datetime
import logging
import os
import random

import discord
from discord.ext import commands, tasks

from utils.economy import StaticView, fmt
from utils.ratelimit import limited_send
from utils.role_blacklist import is_blacklisted

log = logging.getLogger("gambler")

PAYDAY_CHECK_INTERVAL_SECONDS = 60
PAYDAY_MIN_GAP = datetime.timedelta(hours=2)
PAYDAY_MAX_GAP = datetime.timedelta(hours=4)
PAYDAY_MIN_AMOUNT = int(os.getenv("PAYDAY_MIN_AMOUNT", "100"))
PAYDAY_MAX_AMOUNT = int(os.getenv("PAYDAY_MAX_AMOUNT", "10000"))
_raw_payday_channel = os.getenv("PAYDAY_CHANNEL_ID", "1537694458815053865")
PAYDAY_CHANNEL_ID = int(_raw_payday_channel) if _raw_payday_channel.isdigit() else None


def _random_gap() -> datetime.timedelta:
    seconds = random.uniform(PAYDAY_MIN_GAP.total_seconds(), PAYDAY_MAX_GAP.total_seconds())
    return datetime.timedelta(seconds=seconds)


class Payday(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._guild: discord.Guild | None = None
        self.payday_loop.start()

    def cog_unload(self):
        self.payday_loop.cancel()

    @tasks.loop(seconds=PAYDAY_CHECK_INTERVAL_SECONDS)
    async def payday_loop(self):
        try:
            await self._check()
        except Exception:
            log.exception("[payday] check failed")

    @payday_loop.before_loop
    async def before_payday_loop(self):
        await self.bot.wait_until_ready()

    async def _check(self):
        now = datetime.datetime.utcnow()

        next_at = await self.bot.db.get_payday_next()
        if next_at is None:
            await self.bot.db.set_payday_next(now + _random_gap())
            return
        if now < next_at:
            return

        await self.bot.db.set_payday_next(now + _random_gap())

        user_id = await self.bot.db.get_random_user_id()
        if user_id is None:
            return
        if not await self._should_pay(user_id):
            return

        amount = random.randint(PAYDAY_MIN_AMOUNT, PAYDAY_MAX_AMOUNT)
        try:
            await self.bot.db.update_balance(user_id, amount)
        except Exception:
            log.exception("[payday] failed to credit user %s", user_id)
            return

        await self._notify(user_id, amount)

    async def _get_guild(self) -> discord.Guild | None:
        if self._guild is not None:
            return self._guild
        if not PAYDAY_CHANNEL_ID:
            return None
        channel = self.bot.get_channel(PAYDAY_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(PAYDAY_CHANNEL_ID)
            except discord.HTTPException:
                return None
        self._guild = getattr(channel, "guild", None)
        return self._guild

    async def _should_pay(self, user_id: int) -> bool:
        guild = await self._get_guild()
        if guild is None:
            return True
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                return False
            except discord.HTTPException:
                return True
        return not is_blacklisted(member)

    async def _notify(self, user_id: int, amount: int) -> None:
        if not PAYDAY_CHANNEL_ID:
            return
        channel = self.bot.get_channel(PAYDAY_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(PAYDAY_CHANNEL_ID)
            except discord.HTTPException:
                return

        view = StaticView(
            "💰 Payday!",
            f"<@{user_id}> received {fmt(amount)} out of nowhere.",
            color=discord.Color.gold(),
        )
        try:
            await limited_send(channel, view=view)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Payday(bot))
