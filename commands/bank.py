import discord
from discord import app_commands
from discord.ext import commands

from database.db import InsufficientFunds
from utils.economy import StaticView, fmt, resolve_bet


class Bank(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="bank", description="Shows your bank balance. Money there is safe from rob.")
    async def bank(self, ctx: commands.Context):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        wallet = await self.bot.db.get_balance(ctx.author.id)
        bank_balance = await self.bot.db.get_bank_balance(ctx.author.id)

        view = StaticView(
            "🏦 Bank",
            f"**Cash:** {fmt(wallet)}\n**Bank:** {fmt(bank_balance)}\n\n"
            f"-# Money in the bank can't be stolen with `rob`.",
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="deposit", description="Move cash safely into the bank.")
    @app_commands.describe(amount="Amount (number, 'half', or 'all')")
    async def deposit(self, ctx: commands.Context, amount: str):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        value = await resolve_bet(self.bot, ctx.author.id, amount)

        try:
            wallet, bank_balance = await self.bot.db.deposit_to_bank(ctx.author.id, value)
        except InsufficientFunds:
            await ctx.send("⚠️ You don't have enough cash for that.")
            return

        view = StaticView(
            "🏦 Deposit",
            f"Deposited {fmt(value)}.\n**Cash:** {fmt(wallet)}\n**Bank:** {fmt(bank_balance)}",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="withdraw", description="Move money from the bank back to cash.")
    @app_commands.describe(amount="Amount (number, 'half', or 'all')")
    async def withdraw(self, ctx: commands.Context, amount: str):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)

        raw = amount.strip().lower()
        bank_balance = await self.bot.db.get_bank_balance(ctx.author.id)
        if raw in ("all", "max"):
            value = bank_balance
        elif raw == "half":
            value = bank_balance // 2
        else:
            try:
                value = int(raw.replace(",", ""))
            except ValueError:
                await ctx.send(f"⚠️ `{raw}` is not a valid amount.")
                return

        if value <= 0:
            await ctx.send("⚠️ The amount must be greater than 0.")
            return

        try:
            wallet, bank_balance = await self.bot.db.withdraw_from_bank(ctx.author.id, value)
        except InsufficientFunds:
            await ctx.send("⚠️ You don't have enough balance in the bank.")
            return

        view = StaticView(
            "🏦 Withdrawal",
            f"Withdrew {fmt(value)}.\n**Cash:** {fmt(wallet)}\n**Bank:** {fmt(bank_balance)}",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Bank(bot))
