from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from database.db import InsufficientFunds
from rpg.equipment import EQUIPMENT
from utils.economy import StaticView, fmt

ItemKey = Literal[
    "wooden_sword", "iron_sword", "flame_blade", "dragon_fang", "void_reaver", "worldbreaker",
    "leather_armor", "chainmail", "plate_armor", "dragonscale_armor", "void_plate", "worldguard",
]

TIER_ORDER = ["common", "rare", "epic", "legendary", "mythic", "ancient"]


def _shop_text() -> str:
    weapons = sorted(
        (i for i in EQUIPMENT.values() if i.slot == "weapon"), key=lambda i: TIER_ORDER.index(i.tier)
    )
    armors = sorted(
        (i for i in EQUIPMENT.values() if i.slot == "armor"), key=lambda i: TIER_ORDER.index(i.tier)
    )
    lines = ["**⚔️ Weapons**"]
    for item in weapons:
        lines.append(f"`{item.key}` — {item.name} — {fmt(item.price)} (+{item.atk_pct:.0%} ATK)")
    lines.append("\n**🛡️ Armor**")
    for item in armors:
        lines.append(
            f"`{item.key}` — {item.name} — {fmt(item.price)} (+{item.def_pct:.0%} DEF, +{item.hp_pct:.0%} HP)"
        )
    return "\n".join(lines)


class RPGShop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="rpgshop", description="Shows the RPG equipment shop.")
    async def rpgshop(self, ctx: commands.Context):
        view = StaticView("🛒 Equipment Shop", _shop_text() + "\n\nBuy with `/rpgbuy <item>`.")
        await ctx.send(view=view)

    @commands.hybrid_command(name="rpgbuy", description="Buy a piece of equipment.")
    @app_commands.describe(item="Which item to buy")
    async def rpgbuy(self, ctx: commands.Context, item: ItemKey):
        character = await self.bot.db.get_character(ctx.author.id)
        if not character:
            await ctx.send("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        info = EQUIPMENT[item]
        try:
            await self.bot.db.update_balance(ctx.author.id, -info.price)
        except InsufficientFunds:
            await ctx.send(f"⚠️ You don't have enough balance. Costs {fmt(info.price)}.")
            return

        await self.bot.db.add_rpg_item(ctx.author.id, item, 1)
        view = StaticView(
            "🛒 Purchase",
            f"Bought {info.name} for {fmt(info.price)}.\nEquip it with `/rpgequip {item}`.",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="rpgequip", description="Equip a weapon or armor you own.")
    @app_commands.describe(item="Which item to equip")
    async def rpgequip(self, ctx: commands.Context, item: ItemKey):
        character = await self.bot.db.get_character(ctx.author.id)
        if not character:
            await ctx.send("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        owned = await self.bot.db.get_rpg_item_quantity(ctx.author.id, item)
        if owned < 1:
            await ctx.send(f"⚠️ You don't own {EQUIPMENT[item].name}. Buy it with `/rpgbuy {item}`.")
            return

        info = EQUIPMENT[item]
        await self.bot.db.set_equipped(ctx.author.id, info.slot, item)
        view = StaticView("✨ Equipped", f"Equipped {info.name}.", color=discord.Color.green())
        await ctx.send(view=view)

    @commands.hybrid_command(name="rpginventory", aliases=["rpginv"], description="Shows your owned equipment.")
    async def rpginventory(self, ctx: commands.Context):
        rows = await self.bot.db.get_rpg_inventory(ctx.author.id)
        if not rows:
            await ctx.send("🎒 You don't own any equipment yet. Check out `/rpgshop`!")
            return

        lines = [f"**{EQUIPMENT[key].name}** x{qty}" for key, qty in rows if key in EQUIPMENT]
        view = StaticView("🎒 Equipment Inventory", "\n".join(lines))
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGShop(bot))
