import datetime
import random

import discord
from discord import app_commands
from discord.ext import commands

from database.db import InsufficientFunds
from utils.economy import StaticView, fmt

WORK_JOBS = [
    "You stocked shelves at a supermarket",
    "You helped out at a pizzeria",
    "You helped a neighbor move house",
    "You walked some dogs",
    "You gave tutoring lessons",
    "You mowed a lawn",
    "You helped out at an auto shop",
    "You helped out at a farmers market",
]

CRIME_SUCCESS = [
    "You robbed a store without getting noticed",
    "You successfully printed counterfeit money",
    "You hotwired a car and sold it",
    "You escaped with a fat stack of loot",
]
CRIME_FAIL = [
    "The police caught you",
    "The alarm went off before you could flee",
    "A witness snitched on you",
    "You tripped over your own feet",
]

SLUT_SUCCESS = [
    "You sold flowers on the street and made good money",
    "You modeled for a photoshoot",
    "You worked as an entertainer at a party",
    "A generous stranger gave you a fat tip",
]
SLUT_FAIL = [
    "Security threw you out before you got paid",
    "Your client disappeared without paying",
    "You worked the whole night for nothing",
    "An argument ruined the evening",
]

ROB_SUCCESS = [
    "You lifted {target}'s wallet without them noticing",
    "You struck while {target} was distracted",
    "A perfect pickpocket on {target}",
]
ROB_FAIL = [
    "{target} caught you and raised the alarm",
    "You got caught red-handed by {target}",
    "{target} was faster than you and chased you off",
]

MIN_ROB_TARGET_BALANCE = 100
ROB_SUCCESS_CHANCE = 0.45
ROB_STEAL_RANGE = (0.10, 0.25)
ROB_FINE_RANGE = (100, 300)

WORK_COOLDOWN = 60
CRIME_COOLDOWN = 900
SLUT_COOLDOWN = 900
ROB_COOLDOWN = 1800


def _format_remaining(delta: datetime.timedelta) -> str:
    total = max(int(delta.total_seconds()), 0)
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


class Hustle(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _claim_cooldown(self, ctx: commands.Context, action: str, seconds: int) -> bool:
        now = datetime.datetime.utcnow()
        ok = await self.bot.db.try_consume_cooldown(
            ctx.author.id, action, datetime.timedelta(seconds=seconds), now
        )
        if not ok:
            until = await self.bot.db.get_cooldown(ctx.author.id, action)
            remaining = until - now if until else datetime.timedelta(0)
            await ctx.send(f"⏳ `{action}` is on cooldown. Try again in {_format_remaining(remaining)}.")
        return ok

    @commands.hybrid_command(name="work", description="Work for some balance.")
    async def work(self, ctx: commands.Context):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        if not await self._claim_cooldown(ctx, "work", WORK_COOLDOWN):
            return
        amount = random.randint(50, 200)
        new_balance = await self.bot.db.update_balance(ctx.author.id, amount)

        job = random.choice(WORK_JOBS)
        view = StaticView(
            "💼 Work",
            f"{job} and earned {fmt(amount)}.\nNew balance: {fmt(new_balance)}",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="crime", description="Commit a crime for a big payout — with risk.")
    async def crime(self, ctx: commands.Context):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        if not await self._claim_cooldown(ctx, "crime", CRIME_COOLDOWN):
            return

        if random.random() < 0.7:
            amount = random.randint(200, 500)
            new_balance = await self.bot.db.update_balance(ctx.author.id, amount)
            text = f"{random.choice(CRIME_SUCCESS)} and got away with {fmt(amount)}."
            color = discord.Color.green()
        else:
            balance = await self.bot.db.get_balance(ctx.author.id)
            fine = min(random.randint(100, 300), balance)
            new_balance = await self.bot.db.update_balance(ctx.author.id, -fine)
            text = f"{random.choice(CRIME_FAIL)} and paid a {fmt(fine)} fine."
            color = discord.Color.red()

        view = StaticView("🔫 Crime", f"{text}\nNew balance: {fmt(new_balance)}", color=color)
        await ctx.send(view=view)

    @commands.hybrid_command(name="slut", description="Make some extra cash on the side — with risk.")
    async def slut(self, ctx: commands.Context):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        if not await self._claim_cooldown(ctx, "slut", SLUT_COOLDOWN):
            return

        if random.random() < 0.65:
            amount = random.randint(150, 450)
            new_balance = await self.bot.db.update_balance(ctx.author.id, amount)
            text = f"{random.choice(SLUT_SUCCESS)} and earned {fmt(amount)}."
            color = discord.Color.green()
        else:
            balance = await self.bot.db.get_balance(ctx.author.id)
            loss = min(random.randint(75, 250), balance)
            new_balance = await self.bot.db.update_balance(ctx.author.id, -loss)
            text = f"{random.choice(SLUT_FAIL)} and lost {fmt(loss)}."
            color = discord.Color.red()

        view = StaticView("💃 Side Hustle", f"{text}\nNew balance: {fmt(new_balance)}", color=color)
        await ctx.send(view=view)

    @commands.hybrid_command(name="rob", description="Try to steal balance from another player.")
    @app_commands.describe(user="Who to rob")
    async def rob(self, ctx: commands.Context, user: discord.User):
        if user.bot:
            await ctx.send("⚠️ You can't rob bots.")
            return
        if user.id == ctx.author.id:
            await ctx.send("⚠️ You can't rob yourself.")
            return

        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)

        protected_until = await self.bot.db.get_protected_until(user.id)
        if protected_until and protected_until > datetime.datetime.utcnow():
            await ctx.send(f"🛡️ {user.mention} is currently protected by a rob shield.")
            return

        target_balance = await self.bot.db.get_balance(user.id)
        if target_balance < MIN_ROB_TARGET_BALANCE:
            await ctx.send(f"⚠️ {user.mention} doesn't have enough balance to be worth robbing.")
            return

        if not await self._claim_cooldown(ctx, "rob", ROB_COOLDOWN):
            return

        success = random.random() < ROB_SUCCESS_CHANCE
        if success:
            pct = random.uniform(*ROB_STEAL_RANGE)
            stolen = max(1, int(target_balance * pct))
            try:
                await self.bot.db.update_balance(user.id, -stolen)
            except InsufficientFunds:
                stolen = await self.bot.db.get_balance(user.id)
                await self.bot.db.update_balance(user.id, -stolen)
            new_balance = await self.bot.db.update_balance(ctx.author.id, stolen)
            await self.bot.db.record_robbed(user.id)
            text = f"{random.choice(ROB_SUCCESS).format(target=user.mention)} — stole {fmt(stolen)}."
            color = discord.Color.green()
        else:
            robber_balance = await self.bot.db.get_balance(ctx.author.id)
            fine = min(random.randint(*ROB_FINE_RANGE), robber_balance)
            new_balance = await self.bot.db.update_balance(ctx.author.id, -fine)
            if fine:
                await self.bot.db.update_balance(user.id, fine)
            text = f"{random.choice(ROB_FAIL).format(target=user.mention)} — paid a {fmt(fine)} fine to {user.mention}."
            color = discord.Color.red()

        await self.bot.db.record_rob_attempt(ctx.author.id, success)

        view = StaticView("🥷 Robbery", f"{text}\nYour balance: {fmt(new_balance)}", color=color)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Hustle(bot))
