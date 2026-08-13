import datetime
import random
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from rpg.character import current_hp, full_stats, to_fighter
from rpg.combat import Fighter, simulate
from rpg.equipment import EQUIPMENT
from rpg.events import AMBUSH, CURSED, MERCHANT, TREASURE, roll_event
from rpg.leveling import apply_xp
from rpg.monsters import DUNGEONS, scaled_monster
from utils.economy import StaticView, fmt

DungeonKey = Literal["forest", "cave", "crypt", "volcano", "abyss", "celestial"]

DUNGEON_COOLDOWN = 20


def _dungeon_list_text() -> str:
    lines = []
    for d in DUNGEONS.values():
        lines.append(f"{d.emoji} **{d.name}** — recommended level {d.min_level}+")
    return "\n".join(lines)


class RPGDungeon(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="dungeons", description="Shows the available RPG dungeons.")
    async def dungeons(self, ctx: commands.Context):
        view = StaticView("🗺️ Dungeons", _dungeon_list_text())
        await ctx.send(view=view)

    @commands.hybrid_command(name="dungeon", description="Fight your way through a dungeon.")
    @app_commands.describe(dungeon="Which dungeon to enter")
    async def dungeon(self, ctx: commands.Context, dungeon: DungeonKey):
        character = await self.bot.db.get_character(ctx.author.id)
        if not character:
            await ctx.send("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        d = DUNGEONS[dungeon]
        if character["level"] < d.min_level:
            await ctx.send(f"⚠️ {d.name} recommends level {d.min_level}+. You're level {character['level']}.")
            return

        now = datetime.datetime.utcnow()
        player_stats = full_stats(character)
        hp_now = current_hp(character, player_stats["hp"], now)
        if hp_now <= 0:
            await ctx.send("💀 You're too hurt to fight. Use `/heal` or wait for your HP to regenerate.")
            return

        ok = await self.bot.db.try_consume_cooldown(
            ctx.author.id, "dungeon", datetime.timedelta(seconds=DUNGEON_COOLDOWN), now
        )
        if not ok:
            until = await self.bot.db.get_cooldown(ctx.author.id, "dungeon")
            remaining = int((until - now).total_seconds())
            await ctx.send(f"⏳ You're still resting. Try again in {remaining // 60}m {remaining % 60}s.")
            return

        event = roll_event()

        if event == TREASURE:
            gold = random.randint(50, 150) + character["level"] * 5
            await self.bot.db.update_balance(ctx.author.id, gold)
            view = StaticView(
                f"{d.emoji} {d.name}",
                f"💰 **Treasure Chest!** You found {fmt(gold)} without a fight.",
                color=discord.Color.gold(),
            )
            await ctx.send(view=view)
            return

        if event == MERCHANT:
            gold = random.randint(30, 80)
            await self.bot.db.update_balance(ctx.author.id, gold)
            view = StaticView(
                f"{d.emoji} {d.name}",
                f"🧙 **A wandering merchant** pays you {fmt(gold)} for old supplies you didn't need.",
                color=discord.Color.blue(),
            )
            await ctx.send(view=view)
            return

        monster = random.choice(d.monsters)
        stats = scaled_monster(monster, character["level"], d.min_level)
        elite = event == AMBUSH
        if elite:
            for key in ("hp", "atk", "def", "xp"):
                stats[key] = int(stats[key] * 1.4)
            stats["gold"] = (int(stats["gold"][0] * 1.4), int(stats["gold"][1] * 1.4))

        player_fighter = to_fighter(character, ctx.author.display_name, hp=hp_now)
        if event == CURSED:
            player_fighter.crit = max(0.0, player_fighter.crit - 0.10)

        monster_name = f"{monster.emoji} {'Elite ' if elite else ''}{monster.name}"
        monster_fighter = Fighter(
            name=monster_name, max_hp=stats["hp"], atk=stats["atk"], defense=stats["def"], crit=stats["crit"]
        )

        result = simulate(player_fighter, monster_fighter)
        won = result["winner"] is player_fighter

        await self.bot.db.set_character_hp(ctx.author.id, player_fighter.hp, now)
        hp_line = f"\n**HP:** {player_fighter.hp} / {player_fighter.max_hp}"

        header_bits = []
        if elite:
            header_bits.append("⚔️ **Ambush!** A tougher foe blocks your path.")
        if event == CURSED:
            header_bits.append("🌑 **Cursed ground** saps your luck this fight.")
        header = "\n".join(header_bits) + ("\n\n" if header_bits else "")

        log_tail = "\n".join(result["log"][-8:])

        if won:
            gold = random.randint(*stats["gold"])
            await self.bot.db.update_balance(ctx.author.id, gold)
            new_level, new_xp, levels_gained = apply_xp(character["level"], character["xp"], stats["xp"])
            await self.bot.db.set_character_level(ctx.author.id, new_level, new_xp)
            await self.bot.db.record_game_result(ctx.author.id, 0, gold)

            footer = f"\n\n🎉 **Victory!** +{fmt(gold)}  •  +{stats['xp']} XP"
            if levels_gained:
                footer += f"\n⬆️ **Level up!** You're now level {new_level}."

            loot_text = ""
            if monster.loot_pool and random.random() < monster.loot_chance:
                item_key = random.choice(monster.loot_pool)
                await self.bot.db.add_rpg_item(ctx.author.id, item_key, 1)
                loot_text = f"\n🎁 **Loot!** {EQUIPMENT[item_key].name} dropped."

            body = f"{header}You defeated the {monster_name}!\n\n{log_tail}{footer}{loot_text}{hp_line}"
            color = discord.Color.green()
        else:
            downed_text = "\n💀 You've been knocked out! Use `/heal` or wait to recover." if player_fighter.hp <= 0 else ""
            body = f"{header}The {monster_name} defeated you...\n\n{log_tail}\n\n😢 No rewards this time.{hp_line}{downed_text}"
            color = discord.Color.red()

        view = StaticView(f"{d.emoji} {d.name}", body, color=color)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGDungeon(bot))
