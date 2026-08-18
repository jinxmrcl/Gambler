import datetime
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from database.db import InsufficientFunds
from utils.economy import StaticView, fmt
from utils.items import ITEMS, SHIELD_DURATION

ItemKey = Literal["shield", "cooldown_reset"]
LIMITED_ITEMS = ("shield", "cooldown_reset")
ITEM_DAILY_USE_LIMIT = 2
ITEM_USE_WINDOW = datetime.timedelta(hours=24)


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="shop", description="Shows all purchasable items.")
    async def shop(self, ctx: commands.Context):
        lines = [
            f"**{item['name']}** — {fmt(item['price'])}\n-# {item['description']}"
            for item in ITEMS.values()
        ]
        view = StaticView("🛒 Shop", "\n\n".join(lines) + "\n\nBuy with `/buy <item>`.")
        await ctx.send(view=view)

    @commands.hybrid_command(name="buy", description="Buy an item from the shop.")
    @app_commands.describe(item="Which item", quantity="How many (default: 1)")
    async def buy(self, ctx: commands.Context, item: ItemKey, quantity: commands.Range[int, 1, 99] = 1):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        info = ITEMS[item]
        cost = info["price"] * quantity

        try:
            await self.bot.db.update_balance(ctx.author.id, -cost)
        except InsufficientFunds:
            await ctx.send(f"⚠️ You don't have enough balance. Costs {fmt(cost)}.")
            return

        await self.bot.db.add_item(ctx.author.id, item, quantity)

        view = StaticView(
            "🛒 Purchase",
            f"Bought {quantity}x {info['name']} for {fmt(cost)}.",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="inventory", aliases=["inv"], description="Shows your inventory.")
    async def inventory(self, ctx: commands.Context):
        rows = await self.bot.db.get_inventory(ctx.author.id)
        if not rows:
            await ctx.send("🎒 Your inventory is empty. Check out `/shop`!")
            return

        lines = [f"**{ITEMS.get(key, {'name': key})['name']}** x{qty}" for key, qty in rows]
        view = StaticView("🎒 Inventory", "\n".join(lines))
        await ctx.send(view=view)

    @commands.hybrid_command(name="use", description="Use an item from your inventory.")
    @app_commands.describe(item="Which item")
    async def use(self, ctx: commands.Context, item: ItemKey):
        now = datetime.datetime.utcnow()

        try:
            await self.bot.db.remove_item(ctx.author.id, item, 1)
        except InsufficientFunds:
            await ctx.send(f"⚠️ You don't own a {ITEMS[item]['name']}.")
            return

        if item in LIMITED_ITEMS:
            claimed = await self.bot.db.try_record_item_use(
                ctx.author.id, item, ITEM_DAILY_USE_LIMIT, ITEM_USE_WINDOW, now
            )
            if not claimed:
                await self.bot.db.add_item(ctx.author.id, item, 1)
                reset_at = await self.bot.db.get_item_use_reset(ctx.author.id, item, ITEM_USE_WINDOW)
                remaining = reset_at - now
                hours, rem = divmod(max(int(remaining.total_seconds()), 0), 3600)
                minutes = rem // 60
                await ctx.send(
                    f"⚠️ You've already used {ITEMS[item]['name']} {ITEM_DAILY_USE_LIMIT}x in the last "
                    f"24h. Try again in {hours}h {minutes}m."
                )
                return

        if item == "shield":
            until = datetime.datetime.utcnow() + SHIELD_DURATION
            await self.bot.db.set_protected_until(ctx.author.id, until)
            text = f"🛡️ You're now protected from `rob` until {until.strftime('%H:%M UTC')}."
        else:
            await self.bot.db.clear_cooldowns(ctx.author.id, ("work", "crime", "slut", "rob", "duel"))
            text = "⏩ All cooldowns have been reset."

        view = StaticView("✨ Item Used", text, color=discord.Color.green())
        await ctx.send(view=view)

    @commands.hybrid_command(name="gift", description="Gift an item from your inventory.")
    @app_commands.describe(user="Recipient", item="Which item", quantity="How many (default: 1)")
    async def gift(
        self, ctx: commands.Context, user: discord.User, item: ItemKey, quantity: commands.Range[int, 1, 99] = 1
    ):
        if user.bot:
            await ctx.send("⚠️ You can't gift items to a bot.")
            return
        if user.id == ctx.author.id:
            await ctx.send("⚠️ You can't gift items to yourself.")
            return

        try:
            await self.bot.db.remove_item(ctx.author.id, item, quantity)
        except InsufficientFunds:
            await ctx.send(f"⚠️ You don't own {quantity}x {ITEMS[item]['name']}.")
            return

        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)
        await self.bot.db.add_item(user.id, item, quantity)

        view = StaticView(
            "🎁 Gift",
            f"{ctx.author.mention} gifted {quantity}x {ITEMS[item]['name']} to {user.mention}.",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
