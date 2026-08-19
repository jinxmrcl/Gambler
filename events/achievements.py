from discord.ext import commands

from utils.achievements import check_and_announce

# Cogs whose commands can move the needle on a tracked achievement metric
# (net worth, total wagered, robs succeeded, games played, daily streak).
RELEVANT_COGS = {
    "Blackjack", "Mines", "Hilo", "Plinko", "Limbo", "Keno", "Slots", "Roulette", "Dice",
    "Coinflip", "Scratchcard", "HorseRace", "Baccarat", "Hustle", "Economy",
}


class AchievementListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if not ctx.cog or ctx.cog.qualified_name not in RELEVANT_COGS:
            return
        await check_and_announce(self.bot, ctx.author, ctx.channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(AchievementListener(bot))
