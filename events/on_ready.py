import logging

import discord
from discord.ext import commands, tasks

log = logging.getLogger("gambler")

STATUS_ROTATION_SECONDS = 30

STATUS_MESSAGES = [
    "🎰 /help for commands",
    "👥 {member_count} players",
    "🗳️ /vote for rewards",
]


class OnReady(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._presence_set = False
        self._status_index = 0

    def cog_unload(self):
        self.rotate_status.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._presence_set:
            self._presence_set = True
            self.rotate_status.start()
        log.info("Logged in as %s (ID: %s)", self.bot.user, self.bot.user.id)
        await self.bot.report_startup_state()

    @tasks.loop(seconds=STATUS_ROTATION_SECONDS)
    async def rotate_status(self):
        messages = STATUS_MESSAGES
        if not (self.bot.topgg_bot_id and self.bot.topgg_token):
            messages = [m for m in STATUS_MESSAGES if "/vote" not in m]

        member_count = sum(guild.member_count or 0 for guild in self.bot.guilds)
        text = messages[self._status_index % len(messages)].format(member_count=member_count)
        self._status_index += 1
        try:
            await self.bot.change_presence(activity=discord.CustomActivity(name=text))
        except Exception:
            log.exception("[presence] failed to update status")


async def setup(bot: commands.Bot):
    await bot.add_cog(OnReady(bot))
