import logging

import discord
from discord.ext import commands

log = logging.getLogger("gambler")


class OnReady(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await self.bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="/blackjack 🎰")
        )
        log.info("Logged in as %s (ID: %s)", self.bot.user, self.bot.user.id)
        await self.bot.report_startup_state()


async def setup(bot: commands.Bot):
    await bot.add_cog(OnReady(bot))
