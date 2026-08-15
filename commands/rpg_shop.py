import datetime
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from database.db import InsufficientFunds
from rpg.character import current_hp, full_stats
from rpg.consumables import CONSUMABLES
from rpg.equipment import (
    ACCESSORY_NAMES,
    ARMOR_NAMES,
    EQUIPMENT,
    ENCHANT_MAX_LEVEL,
    WEAPON_NAMES,
    enchant_cost,
    recommended_tier_for_level,
)
from rpg.primordial import PRIMORDIAL_BASES, describe_affixes
from utils.economy import StaticView, fmt
from utils.ratelimit import limited_edit

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

        if character.get(f"primordial_{slot}"):
            await interaction.response.send_message(
                f"⚠️ You have a ✨ Primordial item equipped in your {slot} slot — it can't be enchanted. "
                f"Use `/rpgunequipprimordial {slot}` first if you want to upgrade your regular gear instead."
            )
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
            await self.bot.db.upgrade_enchant(interaction.user.id, slot, cost, current_level + 1)
        except InsufficientFunds:
            await interaction.response.send_message(
                f"⚠️ Upgrading {EQUIPMENT[item_key].name} to +{current_level + 1} costs {fmt(cost)}."
            )
            return

        view = StaticView(
            "🔨 Upgraded",
            f"{EQUIPMENT[item_key].name} is now **+{current_level + 1}** for {fmt(cost)}.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpgautoupgrade", description="Repeatedly upgrade your equipped gear until you're out of gold.")
    async def rpgautoupgrade(self, interaction: discord.Interaction):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        slots: list[SlotKey] = ["weapon", "armor", "accessory"]
        equipped = {
            s: character.get(f"equipped_{s}") for s in slots if not character.get(f"primordial_{s}")
        }
        levels = {s: character[f"{s}_enchant"] for s in slots if equipped.get(s)}

        if not levels:
            await interaction.response.send_message("⚠️ You don't have anything equipped. Use `/rpgequip` first.")
            return

        await interaction.response.send_message(view=StaticView("🔨 Auto-Upgrading", "Starting…"))
        message = await interaction.original_response()

        spent = 0
        applied = {s: 0 for s in levels}
        stopped_reason = "all equipped gear reached max level"

        while True:
            candidates = {
                s: enchant_cost(equipped[s], lvl) for s, lvl in levels.items() if lvl < ENCHANT_MAX_LEVEL
            }
            if not candidates:
                break

            slot = min(candidates, key=candidates.get)
            cost = candidates[slot]
            try:
                await self.bot.db.upgrade_enchant(interaction.user.id, slot, cost, levels[slot] + 1)
            except InsufficientFunds:
                stopped_reason = f"ran out of gold (next upgrade needs {fmt(cost)})"
                break

            levels[slot] += 1
            applied[slot] += 1
            spent += cost

            progress = "\n".join(
                f"{EQUIPMENT[equipped[s]].name}: +{levels[s]} ({applied[s]} upgrade{'s' if applied[s] != 1 else ''})"
                for s in levels
            )
            await limited_edit(
                message,
                view=StaticView("🔨 Auto-Upgrading", f"{progress}\n\nSpent so far: {fmt(spent)}"),
            )

        summary_lines = [
            f"{EQUIPMENT[equipped[s]].name}: +{levels[s]} ({applied[s]} upgrade{'s' if applied[s] != 1 else ''})"
            for s in levels
        ]
        total_applied = sum(applied.values())
        body = (
            f"Applied **{total_applied}** upgrade{'s' if total_applied != 1 else ''} for {fmt(spent)}.\n"
            + "\n".join(summary_lines)
            + f"\n\nStopped: {stopped_reason}."
        )
        await limited_edit(message, view=StaticView("🔨 Auto-Upgrade Complete", body, color=discord.Color.green()))

    @app_commands.command(name="rpgautobuy", description="Buy and equip the gear tier recommended for your level, per slot.")
    async def rpgautobuy(self, interaction: discord.Interaction):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        target_tier = recommended_tier_for_level(character["level"])
        target_rank = TIER_ORDER.index(target_tier)
        name_maps = {"weapon": WEAPON_NAMES, "armor": ARMOR_NAMES, "accessory": ACCESSORY_NAMES}

        bought = []
        skipped = []
        for slot in ("weapon", "armor", "accessory"):
            if character.get(f"primordial_{slot}"):
                skipped.append(f"{slot} — ✨ Primordial item equipped")
                continue

            target_key = name_maps[slot][target_tier][0]
            current_key = character.get(f"equipped_{slot}")
            current_tier = EQUIPMENT[current_key].tier if current_key else None
            current_rank = TIER_ORDER.index(current_tier) if current_tier else -1

            if current_rank >= target_rank:
                skipped.append(f"{slot} — already {current_tier or 'nothing'} tier or better")
                continue

            price = EQUIPMENT[target_key].price
            try:
                await self.bot.db.update_balance(interaction.user.id, -price)
            except InsufficientFunds:
                skipped.append(f"{slot} — can't afford {EQUIPMENT[target_key].name} ({fmt(price)})")
                continue

            await self.bot.db.add_rpg_item(interaction.user.id, target_key, 1)
            await self.bot.db.set_equipped(interaction.user.id, slot, target_key)
            await self.bot.db.set_enchant_level(interaction.user.id, slot, 0)
            bought.append(f"{EQUIPMENT[target_key].name} — {fmt(price)}")

        lines = []
        if bought:
            lines.append("**Bought & equipped:**\n" + "\n".join(f"• {b}" for b in bought))
        if skipped:
            lines.append("**Skipped:**\n" + "\n".join(f"• {s}" for s in skipped))
        body = "\n\n".join(lines) if lines else "Nothing to do."

        view = StaticView(
            "🛒 Auto-Buy", body, color=discord.Color.green() if bought else discord.Color.greyple()
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpginventory", description="Shows your owned equipment and potions.")
    async def rpginventory(self, interaction: discord.Interaction):
        rows = await self.bot.db.get_rpg_inventory(interaction.user.id)
        primordial_items = await self.bot.db.get_primordial_items(interaction.user.id)
        if not rows and not primordial_items:
            await interaction.response.send_message("🎒 You don't own any items yet. Check out `/rpgshop`!")
            return

        lines = [f"**{_item_name(key)}** x{qty}" for key, qty in rows] if rows else ["*No regular gear or potions.*"]
        body = "\n".join(lines)

        if primordial_items:
            character = await self.bot.db.get_character(interaction.user.id)
            equipped_ids = {
                character.get("equipped_primordial_weapon_id"),
                character.get("equipped_primordial_armor_id"),
                character.get("equipped_primordial_accessory_id"),
            }
            prim_lines = []
            for item in primordial_items:
                mark = " ✅ *equipped*" if item["id"] in equipped_ids else ""
                base_name = PRIMORDIAL_BASES[item["slot"]].name
                prim_lines.append(
                    f"`#{item['id']}` {base_name} ({item['slot']}) — {describe_affixes(item['affixes'])}{mark}"
                )
            body += "\n\n**✨ Primordial Items**\n" + "\n".join(prim_lines)

        view = StaticView("🎒 Inventory", body)
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpgequipprimordial", description="Equip a ✨ Primordial item you own by its ID.")
    @app_commands.describe(item_id="The Primordial item's ID, shown in /rpginventory")
    async def rpgequipprimordial(self, interaction: discord.Interaction, item_id: int):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        items = await self.bot.db.get_primordial_items(interaction.user.id)
        item = next((i for i in items if i["id"] == item_id), None)
        if not item:
            await interaction.response.send_message(f"⚠️ You don't own a Primordial item with id `#{item_id}`.")
            return

        await self.bot.db.equip_primordial(interaction.user.id, item["slot"], item_id)
        base_name = PRIMORDIAL_BASES[item["slot"]].name
        view = StaticView(
            "✨ Equipped",
            f"Equipped {base_name} ({describe_affixes(item['affixes'])}) in your {item['slot']} slot.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpgunequipprimordial", description="Unequip a ✨ Primordial item, reverting to your regular gear in that slot.")
    @app_commands.describe(slot="Which slot to revert to regular gear")
    async def rpgunequipprimordial(self, interaction: discord.Interaction, slot: SlotKey):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        if not character.get(f"primordial_{slot}"):
            await interaction.response.send_message(f"⚠️ You don't have a Primordial item equipped in your {slot} slot.")
            return

        await self.bot.db.unequip_primordial(interaction.user.id, slot)
        view = StaticView(
            "✨ Unequipped",
            f"Reverted to your regular {slot} gear.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGShop(bot))
