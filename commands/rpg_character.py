import datetime
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from database.db import InsufficientFunds
from rpg.badges import prestige_badge
from rpg.character import current_hp, full_stats
from rpg.classes import CLASSES, base_stats_at_level
from rpg.equipment import EQUIPMENT, SHIELD_CLASS_KEY
from rpg.leveling import prestige_and_level, title_for_level, xp_for_level
from rpg.primordial import PRIMORDIAL_BASES, describe_affixes
from utils.economy import StaticView, fmt

ClassKey = Literal["warrior", "mage", "rogue", "paladin", "necromancer", "ranger", "berserker", "monk", "druid"]
HEAL_COST_PER_HP = 3


def _class_list_text() -> str:
    lines = []
    for c in CLASSES.values():
        lines.append(
            f"{c.emoji} **{c.name}** — {c.description}\n"
            f"-# HP {c.base_hp} • ATK {c.base_atk} • DEF {c.base_def} • Crit {c.base_crit:.0%} "
            f"• Skill: *{c.skill_name}* ({c.skill_desc})"
        )
    return "\n\n".join(lines)


class RPGCharacter(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rpgstart", description="Create your RPG character.")
    @app_commands.describe(character_class="Which class to play")
    async def rpgstart(self, interaction: discord.Interaction, character_class: ClassKey):
        existing = await self.bot.db.get_character(interaction.user.id)
        if existing:
            c = CLASSES[existing["class_key"]]
            await interaction.response.send_message(
                f"⚠️ You already have a {c.emoji} {c.name}. Use `/character` to view your sheet."
            )
            return

        await self.bot.db.ensure_user(interaction.user.id, self.bot.starting_balance)
        starting_hp = base_stats_at_level(character_class, 1)["hp"]
        await self.bot.db.create_character(interaction.user.id, character_class, starting_hp)
        c = CLASSES[character_class]
        view = StaticView(
            "⚔️ Character Created",
            f"Welcome, **{interaction.user.display_name}** the {c.emoji} {c.name}!\n{c.description}\n\n"
            f"Skill: *{c.skill_name}* — {c.skill_desc}\n\n"
            f"Head to `/dungeon` to start fighting, or `/rpgshop` to gear up.",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(view=view)

    @app_commands.command(name="rpgswitchclass", description="Switch to your other class, or unlock a second one. Both classes' progress is kept.")
    @app_commands.describe(character_class="Which class to switch to")
    async def rpgswitchclass(self, interaction: discord.Interaction, character_class: ClassKey):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        if character_class == character["class_key"]:
            await interaction.response.send_message(f"⚠️ You're already playing {CLASSES[character_class].name}.")
            return

        backup = await self.bot.db.get_character_backup(interaction.user.id)
        if backup and character_class != backup["class_key"]:
            active_name = CLASSES[character["class_key"]].name
            backup_name = CLASSES[backup["class_key"]].name
            await interaction.response.send_message(
                f"⚠️ You can only hold 2 classes at once: {active_name} and {backup_name}. "
                f"Use `/rpgswitchclass` with one of those two."
            )
            return

        is_new = not (backup and backup["class_key"] == character_class)
        starting_hp = base_stats_at_level(character_class, 1)["hp"]
        await self.bot.db.swap_character_slot(interaction.user.id, character_class, starting_hp)

        c = CLASSES[character_class]
        if is_new:
            body = (
                f"Unlocked a second class: {c.emoji} **{c.name}**!\n{c.description}\n\n"
                f"Skill: *{c.skill_name}* — {c.skill_desc}\n\n"
                f"Your {CLASSES[character['class_key']].name} is saved — switch back anytime with "
                f"`/rpgswitchclass {character['class_key']}`."
            )
        else:
            body = f"Switched back to your {c.emoji} **{c.name}**. Use `/character` to see where you left off."

        view = StaticView("🔄 Class Switched", body, color=discord.Color.gold())
        await interaction.response.send_message(view=view)

    @app_commands.command(name="classes", description="Shows the available RPG classes.")
    async def classes(self, interaction: discord.Interaction):
        view = StaticView("📜 Classes", _class_list_text())
        await interaction.response.send_message(view=view)

    @app_commands.command(name="character", description="Shows your (or another player's) character sheet.")
    @app_commands.describe(user="Optional: view another player's character")
    async def character(self, interaction: discord.Interaction, user: discord.User | None = None):
        target = user or interaction.user
        character = await self.bot.db.get_character(target.id)
        if not character:
            if target == interaction.user:
                await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            else:
                await interaction.response.send_message(f"⚠️ {target.mention} doesn't have a character yet.")
            return

        c = CLASSES[character["class_key"]]
        stats = full_stats(character)
        hp_now = current_hp(character, stats["hp"])
        title = title_for_level(character["level"])
        needed = xp_for_level(character["level"])
        prestige, level_in_prestige = prestige_and_level(character["level"])

        weapon = EQUIPMENT.get(character["equipped_weapon"])
        armor = EQUIPMENT.get(character["equipped_armor"])
        accessory = EQUIPMENT.get(character.get("equipped_accessory"))

        if character.get("primordial_weapon"):
            weapon_text = f"{PRIMORDIAL_BASES['weapon'].name} ({describe_affixes(character['primordial_weapon']['affixes'])})"
        else:
            weapon_text = f"{weapon.name} (+{character['weapon_enchant']})" if weapon else "*None*"

        if character.get("primordial_armor"):
            armor_text = f"{PRIMORDIAL_BASES['armor'].name} ({describe_affixes(character['primordial_armor']['affixes'])})"
        else:
            armor_text = f"{armor.name} (+{character['armor_enchant']})" if armor else "*None*"

        if character.get("primordial_accessory"):
            accessory_text = f"{PRIMORDIAL_BASES['accessory'].name} ({describe_affixes(character['primordial_accessory']['affixes'])})"
        else:
            accessory_text = f"{accessory.name} (+{character['accessory_enchant']})" if accessory else "*None*"

        shield = EQUIPMENT.get(character.get("equipped_shield"))
        shield_text = f"{shield.name} (+{character['shield_enchant']})" if shield else "*None*"

        total_duels = character["wins"] + character["losses"]
        winrate = f"{character['wins'] / total_duels * 100:.0f}%" if total_duels else "—"
        boss_kills = await self.bot.db.total_boss_kills(target.id)
        backup = await self.bot.db.get_character_backup(target.id)

        if prestige > 0:
            level_line = f"{prestige_badge(prestige)} **Prestige {prestige}, Level {level_in_prestige}** (total level {character['level']})"
        else:
            level_line = f"**Level {character['level']}**"

        stat_line = (
            f"**HP:** {hp_now} / {stats['hp']}  •  **ATK:** {stats['atk']}  •  **DEF:** {stats['def']}  •  "
            f"**Crit:** {stats['crit']:.0%}"
        )
        if stats["damage_reduction_pct"] or stats["block_chance"]:
            stat_line += (
                f"  •  **DR:** {stats['damage_reduction_pct']:.0%}  •  **Block:** {stats['block_chance']:.0%}"
            )

        lines = [
            f"**{title} {c.name}** {c.emoji}",
            level_line,
            f"XP: {character['xp']} / {needed}",
            "",
            stat_line,
            f"**Skill:** {c.skill_name} — {c.skill_desc}",
            "",
            f"**Weapon:** {weapon_text}",
            f"**Armor:** {armor_text}",
            f"**Accessory:** {accessory_text}",
        ]
        if character["class_key"] == SHIELD_CLASS_KEY:
            lines.append(f"**Shield:** {shield_text}")
        lines.extend([
            "",
            f"**Duels:** {character['wins']}W / {character['losses']}L ({winrate})",
            f"**Boss Kills:** {boss_kills}",
        ])
        if backup:
            backup_class = CLASSES[backup["class_key"]]
            lines.append(f"**Also playing:** {backup_class.emoji} {backup_class.name} (Level {backup['level']}) — `/rpgswitchclass {backup['class_key']}`")

        view = StaticView(f"📖 {target.display_name}'s Character", "\n".join(lines))
        await interaction.response.send_message(view=view)

    @app_commands.command(name="heal", description="Pay gold to restore HP instantly (also revives you from 0 HP).")
    async def heal(self, interaction: discord.Interaction):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        stats = full_stats(character)
        now = datetime.datetime.utcnow()
        hp_now = current_hp(character, stats["hp"], now)
        missing = stats["hp"] - hp_now

        if missing <= 0:
            await interaction.response.send_message("✨ You're already at full HP.")
            return

        cost = missing * HEAL_COST_PER_HP
        try:
            await self.bot.db.update_balance(interaction.user.id, -cost)
        except InsufficientFunds:
            await interaction.response.send_message(
                f"⚠️ Healing {missing} HP costs {fmt(cost)}, and you don't have enough balance."
            )
            return

        await self.bot.db.set_character_hp(interaction.user.id, stats["hp"], now)
        revived = hp_now <= 0
        view = StaticView(
            "💚 Healed" + (" & Revived" if revived else ""),
            f"Restored {missing} HP for {fmt(cost)}.\n**HP:** {stats['hp']} / {stats['hp']}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGCharacter(bot))
