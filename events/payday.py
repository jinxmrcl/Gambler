import datetime
import logging
import os
import random

import discord
from discord.ext import commands, tasks

from utils.economy import StaticView, fmt
from utils.ratelimit import limited_send

log = logging.getLogger("gambler")

PAYDAY_CHECK_INTERVAL_SECONDS = 60
PAYDAY_MIN_INTERVAL = datetime.timedelta(hours=6)
PAYDAY_MAX_INTERVAL = datetime.timedelta(hours=24)
PAYDAY_MIN_AMOUNT = int(os.getenv("PAYDAY_MIN_AMOUNT", "100"))
PAYDAY_MAX_AMOUNT = int(os.getenv("PAYDAY_MAX_AMOUNT", "10000"))


def _random_payday_interval() -> datetime.timedelta:
    seconds = random.uniform(PAYDAY_MIN_INTERVAL.total_seconds(), PAYDAY_MAX_INTERVAL.total_seconds())
    return datetime.timedelta(seconds=seconds)


class Payday(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
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

        unscheduled = await self.bot.db.get_users_needing_payday_schedule()
        for user_id in unscheduled:
            await self.bot.db.set_cooldown(user_id, "payday", now + _random_payday_interval())

        due = await self.bot.db.get_due_paydays(now)
        for user_id in due:
            amount = random.randint(PAYDAY_MIN_AMOUNT, PAYDAY_MAX_AMOUNT)
            try:
                await self.bot.db.update_balance(user_id, amount)
            except Exception:
                log.exception("[payday] failed to credit user %s", user_id)
                continue
            await self.bot.db.set_cooldown(user_id, "payday", now + _random_payday_interval())
            await self._notify(user_id, amount)

    async def _notify(self, user_id: int, amount: int) -> None:
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                return

        view = StaticView(
            "💰 Payday!",
            f"You received {fmt(amount)} out of nowhere.",
            color=discord.Color.gold(),
        )
        try:
            await limited_send(user, view=view)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Payday(bot))
