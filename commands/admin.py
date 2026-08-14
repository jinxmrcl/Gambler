from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from rpg.consumables import CONSUMABLES
from rpg.equipment import EQUIPMENT
from rpg.leveling import MAX_LEVEL, xp_for_level
from utils.economy import StaticView, fmt

RPGItemKey = Literal[
    "wooden_sword", "iron_sword", "flame_blade", "dragon_fang", "void_reaver", "worldbreaker",
    "leather_armor", "chainmail", "plate_armor", "dragonscale_armor", "void_plate", "worldguard",
    "lucky_charm", "hawk_eye_ring", "assassins_pendant", "phoenix_feather", "void_sigil", "crown_of_fate",
    "minor_potion", "greater_potion", "superior_potion",
]


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
    async def setbalance(self, ctx: commands.Context, user: discord.User, amount: commands.Range[int, 0]):
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)
        await self.bot.db.set_balance(user.id, amount)

        view = StaticView(
            "🛠️ Balance Set",
            f"Set {user.mention}'s balance to {fmt(amount)}.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="giveall", description="[Admin] Give (or take) balance from every player at once.")
    @app_commands.describe(amount="Amount to give every player (negative to remove, floored at 0)")
    @commands.has_permissions(administrator=True)
    async def giveall(self, ctx: commands.Context, amount: int):
        count = await self.bot.db.give_all_users(amount)

        view = StaticView(
            "🛠️ Balance Given to Everyone",
            f"{fmt(amount)} applied to **{count}** player(s).",
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

    @commands.hybrid_command(name="restart", description="[Admin] Restart the bot process.")
    @commands.has_permissions(administrator=True)
    async def restart(self, ctx: commands.Context):
        view = StaticView(
            "<:restart:1537866127835799572> Restarting",
            "Restarting the bot now — back online in a few seconds.",
            color=discord.Color.blue(),
        )
        await ctx.send(view=view)
        await self.bot.graceful_shutdown()

    @app_commands.command(name="rpgsetlevel", description="[Admin] Set a player's RPG level (and optionally XP).")
    @app_commands.describe(user="Target user", level="New level (1-1500)", xp="XP toward the next level (default: 0)")
    @app_commands.checks.has_permissions(administrator=True)
    async def rpgsetlevel(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        level: app_commands.Range[int, 1, MAX_LEVEL],
        xp: app_commands.Range[int, 0] = 0,
    ):
        character = await self.bot.db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        capped_xp = min(xp, max(xp_for_level(level) - 1, 0)) if level < MAX_LEVEL else 0
        await self.bot.db.set_character_level(user.id, level, capped_xp)

        view = StaticView(
            "🛠️ Level Set",
            f"Set {user.mention}'s RPG level to **{level}** (XP: {capped_xp}).",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpggive", description="[Admin] Give a player a piece of equipment for free.")
    @app_commands.describe(user="Target user", item="Which item to give", quantity="How many (default: 1)")
    @app_commands.checks.has_permissions(administrator=True)
    async def rpggive(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        item: RPGItemKey,
        quantity: app_commands.Range[int, 1, 99] = 1,
    ):
        character = await self.bot.db.get_character(user.id)
        if not character:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        await self.bot.db.add_rpg_item(user.id, item, quantity)
        info = EQUIPMENT.get(item) or CONSUMABLES[item]
        followup = f"They can equip it with `/rpgequip {item}`." if item in EQUIPMENT else f"They can use it with `/rpguse {item}`."

        view = StaticView(
            "🛠️ Equipment Given",
            f"Gave {quantity}x {info.name} to {user.mention}.\n{followup}",
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
