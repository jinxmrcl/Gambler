import datetime
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from database.db import InsufficientFunds
from rpg.badges import prestige_badge
from rpg.character import current_hp, full_stats
from rpg.classes import CLASSES, base_stats_at_level
from rpg.equipment import EQUIPMENT
from rpg.leveling import prestige_and_level, title_for_level, xp_for_level
from utils.economy import StaticView, fmt

ClassKey = Literal["warrior", "mage", "rogue", "paladin"]
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

    @commands.hybrid_command(name="rpgstart", description="Create your RPG character.")
    @app_commands.describe(character_class="Which class to play")
    async def rpgstart(self, ctx: commands.Context, character_class: ClassKey):
        existing = await self.bot.db.get_character(ctx.author.id)
        if existing:
            c = CLASSES[existing["class_key"]]
            await ctx.send(
                f"⚠️ You already have a {c.emoji} {c.name}. Use `/character` to view your sheet."
            )
            return

        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        starting_hp = base_stats_at_level(character_class, 1)["hp"]
        await self.bot.db.create_character(ctx.author.id, character_class, starting_hp)
        c = CLASSES[character_class]
        view = StaticView(
            "⚔️ Character Created",
            f"Welcome, **{ctx.author.display_name}** the {c.emoji} {c.name}!\n{c.description}\n\n"
            f"Skill: *{c.skill_name}* — {c.skill_desc}\n\n"
            f"Head to `/dungeon` to start fighting, or `/rpgshop` to gear up.",
            color=discord.Color.gold(),
        )
        await ctx.send(view=view)

    @commands.hybrid_command(name="classes", description="Shows the available RPG classes.")
    async def classes(self, ctx: commands.Context):
        view = StaticView("📜 Classes", _class_list_text())
        await ctx.send(view=view)

    @commands.hybrid_command(name="character", aliases=["char"], description="Shows your (or another player's) character sheet.")
    @app_commands.describe(user="Optional: view another player's character")
    async def character(self, ctx: commands.Context, user: discord.User | None = None):
        target = user or ctx.author
        character = await self.bot.db.get_character(target.id)
        if not character:
            if target == ctx.author:
                await ctx.send("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            else:
                await ctx.send(f"⚠️ {target.mention} doesn't have a character yet.")
            return

        c = CLASSES[character["class_key"]]
        stats = full_stats(character)
        hp_now = current_hp(character, stats["hp"])
        title = title_for_level(character["level"])
        needed = xp_for_level(character["level"])
        prestige, level_in_prestige = prestige_and_level(character["level"])

        weapon = EQUIPMENT.get(character["equipped_weapon"])
        armor = EQUIPMENT.get(character["equipped_armor"])
        weapon_text = weapon.name if weapon else "*None*"
        armor_text = armor.name if armor else "*None*"

        total_duels = character["wins"] + character["losses"]
        winrate = f"{character['wins'] / total_duels * 100:.0f}%" if total_duels else "—"

        if prestige > 0:
            level_line = f"{prestige_badge(prestige)} **Prestige {prestige}, Level {level_in_prestige}** (total level {character['level']})"
        else:
            level_line = f"**Level {character['level']}**"

        lines = [
            f"**{title} {c.name}** {c.emoji}",
            level_line,
            f"XP: {character['xp']} / {needed}",
            "",
            f"**HP:** {hp_now} / {stats['hp']}  •  **ATK:** {stats['atk']}  •  **DEF:** {stats['def']}  •  **Crit:** {stats['crit']:.0%}",
            f"**Skill:** {c.skill_name} — {c.skill_desc}",
            "",
            f"**Weapon:** {weapon_text}",
            f"**Armor:** {armor_text}",
            "",
            f"**Duels:** {character['wins']}W / {character['losses']}L ({winrate})",
        ]

        view = StaticView(f"📖 {target.display_name}'s Character", "\n".join(lines))
        await ctx.send(view=view)

    @commands.hybrid_command(
        name="heal", description="Pay gold to restore HP instantly (also revives you from 0 HP)."
    )
    async def heal(self, ctx: commands.Context):
        character = await self.bot.db.get_character(ctx.author.id)
        if not character:
            await ctx.send("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        stats = full_stats(character)
        now = datetime.datetime.utcnow()
        hp_now = current_hp(character, stats["hp"], now)
        missing = stats["hp"] - hp_now

        if missing <= 0:
            await ctx.send("✨ You're already at full HP.")
            return

        cost = missing * HEAL_COST_PER_HP
        try:
            await self.bot.db.update_balance(ctx.author.id, -cost)
        except InsufficientFunds:
            await ctx.send(
                f"⚠️ Healing {missing} HP costs {fmt(cost)}, and you don't have enough balance."
            )
            return

        await self.bot.db.set_character_hp(ctx.author.id, stats["hp"], now)
        revived = hp_now <= 0
        view = StaticView(
            "💚 Healed" + (" & Revived" if revived else ""),
            f"Restored {missing} HP for {fmt(cost)}.\n**HP:** {stats['hp']} / {stats['hp']}",
            color=discord.Color.green(),
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGCharacter(bot))
