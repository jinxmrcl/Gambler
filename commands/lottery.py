import datetime
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.economy import HOUSE_EDGE, StaticView, fmt

TICKET_PRICE = 100
DRAW_INTERVAL = datetime.timedelta(days=7)


class Lottery(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.draw_loop.start()

    def cog_unload(self):
        self.draw_loop.cancel()

    @tasks.loop(hours=1)
    async def draw_loop(self):
        state = await self.bot.db.get_lottery_state()
        if datetime.datetime.utcnow() < state["next_draw"]:
            return

        tickets = await self.bot.db.all_lottery_tickets()
        next_draw = datetime.datetime.utcnow() + DRAW_INTERVAL

        if not tickets:
            await self.bot.db.reset_lottery(next_draw)
            return

        winner_id = random.choices(
            [user_id for user_id, _ in tickets], weights=[qty for _, qty in tickets], k=1
        )[0]
        payout = int(state["pot"] * (1 - HOUSE_EDGE))

        await self.bot.db.ensure_user(winner_id, self.bot.starting_balance)
        await self.bot.db.update_balance(winner_id, payout)
        await self.bot.db.reset_lottery(next_draw)

        if state["channel_id"]:
            channel = self.bot.get_channel(state["channel_id"])
            if channel:
                view = StaticView(
                    "🎟️ Lottery Draw",
                    f"<@{winner_id}> won the lottery and takes home {fmt(payout)}! A new round has started.",
                    color=discord.Color.gold(),
                )
                await channel.send(view=view)

    @draw_loop.before_loop
    async def before_draw_loop(self):
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="lottery", description="Shows the current lottery pot and your tickets.")
    async def lottery(self, ctx: commands.Context):
        state = await self.bot.db.get_lottery_state()
        my_tickets = await self.bot.db.get_lottery_tickets(ctx.author.id)
        remaining = state["next_draw"] - datetime.datetime.utcnow()
        days, hours = divmod(int(max(remaining.total_seconds(), 0)) // 3600, 24)

        view = StaticView(
            "🎟️ Lottery",
            f"**Pot:** {fmt(state['pot'])}\n**Your tickets:** {my_tickets}\n"
            f"**Ticket price:** {fmt(TICKET_PRICE)}\n**Next draw in:** {days}d {hours}h\n\n"
            f"Buy tickets with `/lottery_buy <quantity>`.",
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="lottery_buy", description="Buy lottery tickets.")
    @app_commands.describe(quantity="How many tickets to buy")
    async def lottery_buy(self, ctx: commands.Context, quantity: commands.Range[int, 1, 1000] = 1):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        cost = TICKET_PRICE * quantity
        balance = await self.bot.db.get_balance(ctx.author.id)
        if balance < cost:
            await ctx.send(f"⚠️ You need {fmt(cost)} for {quantity} ticket(s).")
            return

        await self.bot.db.buy_lottery_tickets(ctx.author.id, quantity, cost)
        my_tickets = await self.bot.db.get_lottery_tickets(ctx.author.id)

        view = StaticView(
            "🎟️ Tickets Bought",
            f"Bought {quantity} ticket(s) for {fmt(cost)}.\nYou now have {my_tickets} ticket(s).",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="lottery_setchannel", description="[Admin] Set this channel for lottery draw announcements.")
    @commands.has_permissions(administrator=True)
    async def lottery_setchannel(self, ctx: commands.Context):
        await self.bot.db.set_lottery_channel(ctx.channel.id)
        view = StaticView(
            "🎟️ Lottery Channel Set",
            f"Draw results will be announced in {ctx.channel.mention}.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Lottery(bot))
