from discord.ext import commands

from utils.achievements import check_and_announce

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
        if ctx.guild is None:
            return
        db = await self.bot.db.get(ctx.guild.id)
        await check_and_announce(db, ctx.author, ctx.channel)


async def setup(bot: commands.Bot):
    await bot.add_cog(AchievementListener(bot))
