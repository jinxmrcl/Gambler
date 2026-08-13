import discord
from discord import app_commands
from discord.ext import commands

from utils.economy import StaticView, fmt


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="addmoney", description="[Admin] Add or remove balance.")
    @app_commands.describe(user="Target user", amount="Amount (negative to remove)")
    @commands.has_permissions(administrator=True)
    async def addmoney(self, ctx: commands.Context, user: discord.User, amount: int):
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)
        new_balance = await self.bot.db.update_balance(user.id, amount)

        view = StaticView(
            "🛠️ Balance Changed",
            f"{fmt(amount)} applied to {user.mention}.\nNew balance: {fmt(new_balance)}",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="setbalance", description="[Admin] Set a user's balance exactly.")
    @app_commands.describe(user="Target user", amount="New balance")
    @commands.has_permissions(administrator=True)
    async def setbalance(self, ctx: commands.Context, user: discord.User, amount: app_commands.Range[int, 0]):
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)
        await self.bot.db.set_balance(user.id, amount)

        view = StaticView(
            "🛠️ Balance Set",
            f"Set {user.mention}'s balance to {fmt(amount)}.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="resetuser", description="[Admin] Fully reset a user.")
    @app_commands.describe(user="Target user")
    @commands.has_permissions(administrator=True)
    async def resetuser(self, ctx: commands.Context, user: discord.User):
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)
        await self.bot.db.reset_user(user.id, self.bot.starting_balance)

        view = StaticView(
            "🛠️ User Reset",
            f"{user.mention} was reset to {fmt(self.bot.starting_balance)} "
            f"(bank, inventory, and statistics cleared).",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
