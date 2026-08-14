import datetime
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from database.db import InsufficientFunds
from rpg.character import current_hp, full_stats
from rpg.consumables import CONSUMABLES
from rpg.equipment import EQUIPMENT, ENCHANT_MAX_LEVEL, enchant_cost
from utils.economy import StaticView, fmt

EquipmentKey = Literal[
    "wooden_sword", "iron_sword", "flame_blade", "dragon_fang", "void_reaver", "worldbreaker",
    "leather_armor", "chainmail", "plate_armor", "dragonscale_armor", "void_plate", "worldguard",
    "lucky_charm", "hawk_eye_ring", "assassins_pendant", "phoenix_feather", "void_sigil", "crown_of_fate",
]
ItemKey = Literal[
    "wooden_sword", "iron_sword", "flame_blade", "dragon_fang", "void_reaver", "worldbreaker",
    "leather_armor", "chainmail", "plate_armor", "dragonscale_armor", "void_plate", "worldguard",
    "lucky_charm", "hawk_eye_ring", "assassins_pendant", "phoenix_feather", "void_sigil", "crown_of_fate",
    "minor_potion", "greater_potion", "superior_potion",
]
SlotKey = Literal["weapon", "armor", "accessory"]

TIER_ORDER = ["common", "rare", "epic", "legendary", "mythic", "ancient"]
SELL_FRACTION = 0.4


def _item_name(key: str) -> str:
    if key in EQUIPMENT:
        return EQUIPMENT[key].name
    if key in CONSUMABLES:
        return CONSUMABLES[key].name
    return key


def _item_price(key: str) -> int:
    if key in EQUIPMENT:
        return EQUIPMENT[key].price
    if key in CONSUMABLES:
        return CONSUMABLES[key].price
    return 0


def _shop_text() -> str:
    weapons = sorted(
        (i for i in EQUIPMENT.values() if i.slot == "weapon"), key=lambda i: TIER_ORDER.index(i.tier)
    )
    armors = sorted(
        (i for i in EQUIPMENT.values() if i.slot == "armor"), key=lambda i: TIER_ORDER.index(i.tier)
    )
    accessories = sorted(
        (i for i in EQUIPMENT.values() if i.slot == "accessory"), key=lambda i: TIER_ORDER.index(i.tier)
    )
    lines = ["**⚔️ Weapons**"]
    for item in weapons:
        lines.append(f"`{item.key}` — {item.name} — {fmt(item.price)} (+{item.atk_pct:.0%} ATK)")
    lines.append("\n**🛡️ Armor**")
    for item in armors:
        lines.append(
            f"`{item.key}` — {item.name} — {fmt(item.price)} (+{item.def_pct:.0%} DEF, +{item.hp_pct:.0%} HP)"
        )
    lines.append("\n**💍 Accessories**")
    for item in accessories:
        lines.append(f"`{item.key}` — {item.name} — {fmt(item.price)} (+{item.crit_pct:.0%} Crit)")
    lines.append("\n**🧪 Potions**")
    for c in CONSUMABLES.values():
        lines.append(f"`{c.key}` — {c.name} — {fmt(c.price)} (restores {c.heal_pct:.0%} HP)")
    return "\n".join(lines)


class RPGShop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rpgshop", description="Shows the RPG equipment and potion shop.")
    async def rpgshop(self, interaction: discord.Interaction):
        view = StaticView("🛒 Equipment Shop", _shop_text() + "\n\nBuy with `/rpgbuy <item>`.")
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpgbuy", description="Buy a piece of equipment or a potion.")
    @app_commands.describe(item="Which item to buy", quantity="How many (default: 1, potions only)")
    async def rpgbuy(self, interaction: discord.Interaction, item: ItemKey, quantity: app_commands.Range[int, 1, 99] = 1):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        is_equipment = item in EQUIPMENT
        if is_equipment:
            quantity = 1  # equipment is unique-per-slot; only potions stack meaningfully
        price = _item_price(item)
        cost = price * quantity

        try:
            await self.bot.db.update_balance(interaction.user.id, -cost)
        except InsufficientFunds:
            await interaction.response.send_message(f"⚠️ You don't have enough balance. Costs {fmt(cost)}.")
            return

        await self.bot.db.add_rpg_item(interaction.user.id, item, quantity)
        followup = f"Equip it with `/rpgequip {item}`." if is_equipment else f"Use it with `/rpguse {item}`."
        view = StaticView(
            "🛒 Purchase",
            f"Bought {quantity}x {_item_name(item)} for {fmt(cost)}.\n{followup}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpgequip", description="Equip a weapon, armor, or accessory you own.")
    @app_commands.describe(item="Which item to equip")
    async def rpgequip(self, interaction: discord.Interaction, item: EquipmentKey):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        owned = await self.bot.db.get_rpg_item_quantity(interaction.user.id, item)
        if owned < 1:
            await interaction.response.send_message(
                f"⚠️ You don't own {EQUIPMENT[item].name}. Buy it with `/rpgbuy {item}`."
            )
            return

        info = EQUIPMENT[item]
        await self.bot.db.set_equipped(interaction.user.id, info.slot, item)
        await self.bot.db.set_enchant_level(interaction.user.id, info.slot, 0)
        view = StaticView("✨ Equipped", f"Equipped {info.name}.", color=discord.Color.green())
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpguse", description="Use a potion from your inventory.")
    @app_commands.describe(item="Which potion to use")
    async def rpguse(self, interaction: discord.Interaction, item: Literal["minor_potion", "greater_potion", "superior_potion"]):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        try:
            await self.bot.db.remove_rpg_item(interaction.user.id, item, 1)
        except InsufficientFunds:
            await interaction.response.send_message(f"⚠️ You don't own a {CONSUMABLES[item].name}.")
            return

        stats = full_stats(character)
        now_hp = current_hp(character, stats["hp"])
        potion = CONSUMABLES[item]
        healed = min(stats["hp"] - now_hp, int(stats["hp"] * potion.heal_pct))
        new_hp = now_hp + healed
        await self.bot.db.set_character_hp(interaction.user.id, new_hp, datetime.datetime.utcnow())

        view = StaticView(
            "🧪 Potion Used",
            f"Restored {healed} HP.\n**HP:** {new_hp} / {stats['hp']}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpgsell", description="Sell an owned item back for gold.")
    @app_commands.describe(item="Which item to sell", quantity="How many (default: 1)")
    async def rpgsell(self, interaction: discord.Interaction, item: ItemKey, quantity: app_commands.Range[int, 1, 99] = 1):
        owned = await self.bot.db.get_rpg_item_quantity(interaction.user.id, item)
        if owned < quantity:
            await interaction.response.send_message(f"⚠️ You don't own {quantity}x {_item_name(item)}.")
            return

        proceeds = int(_item_price(item) * SELL_FRACTION) * quantity
        await self.bot.db.remove_rpg_item(interaction.user.id, item, quantity)
        await self.bot.db.update_balance(interaction.user.id, proceeds)

        view = StaticView(
            "💰 Sold",
            f"Sold {quantity}x {_item_name(item)} for {fmt(proceeds)}.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpgupgrade", description="Spend gold to upgrade your equipped gear in a slot.")
    @app_commands.describe(slot="Which equipped slot to upgrade")
    async def rpgupgrade(self, interaction: discord.Interaction, slot: SlotKey):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        item_key = character.get(f"equipped_{slot}")
        if not item_key:
            await interaction.response.send_message(f"⚠️ You don't have anything equipped in your {slot} slot.")
            return

        current_level = character[f"{slot}_enchant"]
        if current_level >= ENCHANT_MAX_LEVEL:
            await interaction.response.send_message(f"⚠️ {EQUIPMENT[item_key].name} is already at max upgrade level.")
            return

        cost = enchant_cost(item_key, current_level)
        try:
            await self.bot.db.update_balance(interaction.user.id, -cost)
        except InsufficientFunds:
            await interaction.response.send_message(
                f"⚠️ Upgrading {EQUIPMENT[item_key].name} to +{current_level + 1} costs {fmt(cost)}."
            )
            return

        await self.bot.db.set_enchant_level(interaction.user.id, slot, current_level + 1)
        view = StaticView(
            "🔨 Upgraded",
            f"{EQUIPMENT[item_key].name} is now **+{current_level + 1}** for {fmt(cost)}.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpginventory", description="Shows your owned equipment and potions.")
    async def rpginventory(self, interaction: discord.Interaction):
        rows = await self.bot.db.get_rpg_inventory(interaction.user.id)
        if not rows:
            await interaction.response.send_message("🎒 You don't own any items yet. Check out `/rpgshop`!")
            return

        lines = [f"**{_item_name(key)}** x{qty}" for key, qty in rows]
        view = StaticView("🎒 Inventory", "\n".join(lines))
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGShop(bot))
