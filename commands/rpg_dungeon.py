import asyncio
import datetime
import json
import logging
import os
import random
from typing import Literal

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.db import InsufficientFunds
from rpg.character import current_hp, full_stats, to_fighter
from rpg.combat import Fighter, simulate, simulate_team
from rpg.consumables import CONSUMABLES
from rpg.equipment import EQUIPMENT
from rpg.events import AMBUSH, CURSED, MERCHANT, TREASURE, roll_event
from rpg.leveling import apply_xp
from rpg.monsters import BOSS_SKILLS, DUNGEONS, Dungeon, scaled_monster
from rpg.primordial import HIGH_END_DUNGEONS, PRIMORDIAL_BASES, PRIMORDIAL_DROP_CHANCE, describe_affixes, generate_primordial_drop
from utils.economy import StaticView, fmt, game_container
from utils.ratelimit import limited_edit, limited_send

log = logging.getLogger("gambler")

DungeonKey = Literal[
    "forest", "cave", "crypt", "volcano", "abyss", "celestial",
    "ruins", "frostpeak", "wastes", "nightmare_realm", "sunken_city",
    "voidscar", "titan_forge", "chaos_rift", "eternal_throne", "world_ender",
]

TEAM_LOBBY_SECONDS = 30
TEAM_MAX_SIZE = 8
BOSS_BONUS_LOOT_CHANCE = 0.15
IDLE_POLL_SECONDS = 5
IDLE_MAX_MINUTES = 120
IDLE_DEFAULT_MINUTES = 30

_raw_idle_announce_channel = os.getenv("IDLE_ANNOUNCE_CHANNEL_ID", "1538948163510083605")
IDLE_ANNOUNCE_CHANNEL_ID = int(_raw_idle_announce_channel) if _raw_idle_announce_channel.isdigit() else None
IDLE_TRACKER_REPOST_AFTER = datetime.timedelta(hours=12)


def _dungeon_list_text() -> str:
    lines = []
    for d in DUNGEONS.values():
        lines.append(f"{d.emoji} **{d.name}** — recommended level {d.min_level}+")
    return "\n".join(lines)


async def _resolve_dungeon_fight(
    bot, user_id: int, display_name: str, character: dict, hp_now: int, d: Dungeon, now: datetime.datetime
) -> dict:
    event = roll_event()
    gold_find_pct = full_stats(character).get("gold_find_pct", 0.0)
    outcome = {
        "event": event, "won": None, "elite": False, "monster_name": None, "log": [],
        "hp": hp_now, "max_hp": hp_now,
        "gold": 0, "xp": 0, "levels_gained": 0, "new_level": character["level"], "loot_item": None,
    }

    if event == TREASURE:
        gold = int((random.randint(50, 150) + character["level"] * 5) * (1 + gold_find_pct))
        await bot.db.update_balance(user_id, gold)
        outcome["gold"] = gold
        return outcome

    if event == MERCHANT:
        gold = int(random.randint(30, 80) * (1 + gold_find_pct))
        await bot.db.update_balance(user_id, gold)
        outcome["gold"] = gold
        return outcome

    monster = random.choice(d.monsters)
    stats = scaled_monster(monster, character["level"], d.min_level, d.key)
    elite = event == AMBUSH
    if elite:
        for key in ("hp", "atk", "def"):
            stats[key] = int(stats[key] * 1.15)
        stats["xp"] = int(stats["xp"] * 1.4)
        stats["gold"] = (int(stats["gold"][0] * 1.4), int(stats["gold"][1] * 1.4))

    player_fighter = to_fighter(character, display_name, hp=hp_now)
    if event == CURSED:
        player_fighter.crit = max(0.0, player_fighter.crit - 0.10)

    monster_name = f"{monster.emoji} {'Elite ' if elite else ''}{monster.name}"
    monster_fighter = Fighter(
        name=monster_name, max_hp=stats["hp"], atk=stats["atk"], defense=stats["def"], crit=stats["crit"]
    )

    result = simulate(player_fighter, monster_fighter)
    won = result["winner"] is player_fighter
    await bot.db.set_character_hp(user_id, player_fighter.hp, now)

    outcome.update(
        won=won, elite=elite, monster_name=monster_name, log=result["log"],
        hp=player_fighter.hp, max_hp=player_fighter.max_hp, timed_out=result["timed_out"],
    )

    if won:
        gold = int(random.randint(*stats["gold"]) * (1 + gold_find_pct))
        await bot.db.update_balance(user_id, gold)
        new_level, new_xp, levels_gained = apply_xp(character["level"], character["xp"], stats["xp"])
        await bot.db.set_character_level(user_id, new_level, new_xp)
        await bot.db.record_game_result(user_id, 0, gold)
        outcome.update(gold=gold, xp=stats["xp"], levels_gained=levels_gained, new_level=new_level)

        if monster.loot_pool and random.random() < monster.loot_chance:
            item_key = random.choice(monster.loot_pool)
            await bot.db.add_rpg_item(user_id, item_key, 1)
            outcome["loot_item"] = item_key

    return outcome


async def _resolve_boss_fight(
    bot, user_id: int, display_name: str, character: dict, hp_now: int, d: Dungeon, now: datetime.datetime
) -> dict:
    stats = scaled_monster(d.boss, character["level"], d.min_level, d.key, is_boss=True)
    player_fighter = to_fighter(character, display_name, hp=hp_now)
    boss_name = f"{d.boss.emoji} {d.boss.name}"
    boss_fighter = Fighter(
        name=boss_name, max_hp=stats["hp"], atk=stats["atk"], defense=stats["def"], crit=stats["crit"],
        skill_key=BOSS_SKILLS.get(d.key),
    )

    result = simulate(player_fighter, boss_fighter)
    won = result["winner"] is player_fighter
    await bot.db.set_character_hp(user_id, player_fighter.hp, now)

    outcome = {
        "won": won, "boss_name": boss_name, "log": result["log"],
        "hp": player_fighter.hp, "max_hp": player_fighter.max_hp, "timed_out": result["timed_out"],
        "gold": 0, "xp": 0, "levels_gained": 0, "new_level": character["level"],
        "loot_item": None, "bonus_loot_item": None, "kills": None, "primordial_drop": None,
    }

    if won:
        gold_find_pct = full_stats(character).get("gold_find_pct", 0.0)
        gold = int(random.randint(*stats["gold"]) * (1 + gold_find_pct))
        await bot.db.update_balance(user_id, gold)
        new_level, new_xp, levels_gained = apply_xp(character["level"], character["xp"], stats["xp"])
        await bot.db.set_character_level(user_id, new_level, new_xp)
        await bot.db.record_game_result(user_id, 0, gold)
        await bot.db.record_boss_kill(user_id, d.key)
        kills = await bot.db.get_boss_kills(user_id, d.key)
        outcome.update(gold=gold, xp=stats["xp"], levels_gained=levels_gained, new_level=new_level, kills=kills)

        if d.boss.loot_pool and random.random() < d.boss.loot_chance:
            item_key = random.choice(d.boss.loot_pool)
            await bot.db.add_rpg_item(user_id, item_key, 1)
            outcome["loot_item"] = item_key

        if d.boss.loot_pool and random.random() < BOSS_BONUS_LOOT_CHANCE:
            bonus_key = random.choice(d.boss.loot_pool)
            await bot.db.add_rpg_item(user_id, bonus_key, 1)
            outcome["bonus_loot_item"] = bonus_key

        if d.key in HIGH_END_DUNGEONS and random.random() < PRIMORDIAL_DROP_CHANCE:
            slot = random.choice(("weapon", "armor", "accessory"))
            affixes = generate_primordial_drop(slot)
            await bot.db.add_primordial_item(user_id, slot, json.dumps(affixes))
            outcome["primordial_drop"] = {"slot": slot, "affixes": affixes}

    return outcome


class JoinButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Join", emoji="🙋")

    async def callback(self, interaction: discord.Interaction):
        await self.view.join(interaction)


class StartButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Start Now", emoji="▶️")

    async def callback(self, interaction: discord.Interaction):
        await self.view.start_now(interaction)


class UsePotionButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Use Potion", emoji="🧪")

    async def callback(self, interaction: discord.Interaction):
        await self.view.use_potion(interaction)


class TeamLobbyView(ui.LayoutView):
    def __init__(self, cog: "RPGDungeon", starter: discord.abc.User, dungeon: Dungeon, is_boss: bool):
        super().__init__(timeout=TEAM_LOBBY_SECONDS)
        self.cog = cog
        self.starter = starter
        self.dungeon = dungeon
        self.is_boss = is_boss
        self.members: list[discord.abc.User] = [starter]
        self.finished = False
        self.message: discord.Message | None = None
        self.potion_log: list[str] = []
        self._join_lock = asyncio.Lock()

        self.heading = f"{'👑 ' if is_boss else ''}{dungeon.emoji} {dungeon.name}{' — Boss' if is_boss else ''}"
        self.container, self.text = game_container(self.heading, self._lobby_body())
        self.join_button = JoinButton()
        self.start_button = StartButton()
        self.potion_button = UsePotionButton()
        row = ui.ActionRow()
        row.add_item(self.join_button)
        row.add_item(self.start_button)
        row.add_item(self.potion_button)
        self.container.add_item(row)
        self.add_item(self.container)

    def _lobby_body(self) -> str:
        target = self.dungeon.boss.name if self.is_boss else "a monster"
        names = "\n".join(f"• {m.mention}" for m in self.members)
        body = (
            f"🤝 **Team fight!** {self.starter.mention} is gathering a party to face **{target}**.\n"
            f"Anyone with a character can **Join**. Starts automatically in {TEAM_LOBBY_SECONDS}s, "
            f"or the party leader can hit **Start Now**. Anyone can **Use Potion** to heal the "
            f"whole party before the fight.\n\n**Party ({len(self.members)}):**\n{names}"
        )
        if self.potion_log:
            body += "\n\n" + "\n".join(self.potion_log)
        return body

    def _set_body(self, body: str):
        self.text.content = f"## {self.heading}\n{body}"

    def _disable_buttons(self):
        self.join_button.disabled = True
        self.start_button.disabled = True
        self.potion_button.disabled = True

    async def _send(self, interaction: discord.Interaction | None):
        if interaction is not None:
            await interaction.response.edit_message(view=self)
        elif self.message:
            await limited_edit(self.message, view=self)

    async def join(self, interaction: discord.Interaction):
        async with self._join_lock:
            if self.finished:
                await interaction.response.send_message("This lobby has already started.", ephemeral=True)
                return
            if any(m.id == interaction.user.id for m in self.members):
                await interaction.response.send_message("You're already in this party.", ephemeral=True)
                return
            if len(self.members) >= TEAM_MAX_SIZE:
                await interaction.response.send_message("This party is full.", ephemeral=True)
                return

            character = await self.cog.bot.db.get_character(interaction.user.id)
            if not character:
                await interaction.response.send_message(
                    "⚠️ You don't have a character yet. Use `/rpgstart` to create one.", ephemeral=True
                )
                return
            if character["level"] < self.dungeon.min_level:
                await interaction.response.send_message(
                    f"⚠️ {self.dungeon.name} recommends level {self.dungeon.min_level}+. "
                    f"You're level {character['level']}.",
                    ephemeral=True,
                )
                return

            self.members.append(interaction.user)
            self._set_body(self._lobby_body())
            await interaction.response.edit_message(view=self)

    async def use_potion(self, interaction: discord.Interaction):
        async with self._join_lock:
            if self.finished:
                await interaction.response.send_message("This lobby has already started.", ephemeral=True)
                return
            if not any(m.id == interaction.user.id for m in self.members):
                await interaction.response.send_message(
                    "Join the party first before using a potion.", ephemeral=True
                )
                return

            db = self.cog.bot.db
            potion_key = None
            for key in ("minor_potion", "greater_potion", "superior_potion"):
                if await db.get_rpg_item_quantity(interaction.user.id, key) > 0:
                    potion_key = key
                    break

            if not potion_key:
                await interaction.response.send_message("⚠️ You don't own any potions.", ephemeral=True)
                return

            try:
                await db.remove_rpg_item(interaction.user.id, potion_key, 1)
            except InsufficientFunds:
                await interaction.response.send_message("⚠️ You don't own any potions.", ephemeral=True)
                return

            potion = CONSUMABLES[potion_key]
            now = datetime.datetime.utcnow()
            healed_lines = []
            for member in self.members:
                character = await db.get_character(member.id)
                if not character:
                    continue
                stats = full_stats(character)
                hp_now = current_hp(character, stats["hp"], now)
                healed = min(stats["hp"] - hp_now, int(stats["hp"] * potion.heal_pct))
                if healed <= 0:
                    continue
                new_hp = hp_now + healed
                await db.set_character_hp(member.id, new_hp, now)
                healed_lines.append(f"{member.mention} +{healed} HP")

            summary = f"🧪 {interaction.user.mention} used a {potion.name} — " + (
                ", ".join(healed_lines) if healed_lines else "the party was already at full HP."
            )
            self.potion_log.append(summary)
            self._set_body(self._lobby_body())
            await interaction.response.edit_message(view=self)

    async def start_now(self, interaction: discord.Interaction):
        if self.finished:
            await interaction.response.send_message("This lobby has already started.", ephemeral=True)
            return
        if interaction.user.id != self.starter.id:
            await interaction.response.send_message("Only the party leader can start early.", ephemeral=True)
            return
        await self._run_fight(interaction)

    async def on_timeout(self):
        if self.finished:
            return
        await self._run_fight(None)

    async def _run_fight(self, interaction: discord.Interaction | None):
        async with self._join_lock:
            if self.finished:
                return
            self.finished = True
            self._disable_buttons()

        now = datetime.datetime.utcnow()
        db = self.cog.bot.db
        d = self.dungeon

        roster: list[tuple[discord.abc.User, dict]] = []
        dropped: list[str] = []
        for member in self.members:
            character = await db.get_character(member.id)
            if character and character["level"] >= d.min_level:
                roster.append((member, character))
            elif character:
                dropped.append(f"{member.mention} (below level {d.min_level})")
            else:
                dropped.append(f"{member.mention} (no character)")

        fighters: list[Fighter] = []
        fighter_members: list[discord.abc.User] = []
        fighter_characters: list[dict] = []

        for member, character in roster:
            player_stats = full_stats(character)
            hp_now = current_hp(character, player_stats["hp"], now)
            if hp_now <= 0:
                dropped.append(f"{member.mention} (too hurt)")
                continue

            fighters.append(to_fighter(character, member.display_name, hp=hp_now))
            fighter_members.append(member)
            fighter_characters.append(character)

        if not fighters:
            body = self._lobby_body() + "\n\n😢 Nobody was able to fight. The party disbanded."
            if dropped:
                body += "\n" + "\n".join(dropped)
            self._set_body(body)
            self.container.accent_colour = discord.Color.greyple()
            self.stop()
            await self._send(interaction)
            return

        target_level = max(c["level"] for c in fighter_characters)
        party_size = len(fighters)

        if self.is_boss:
            body, color = await self._resolve_boss_fight(db, now, d, fighters, fighter_members, fighter_characters, target_level, party_size, dropped)
        else:
            body, color = await self._resolve_dungeon_fight(db, now, d, fighters, fighter_members, fighter_characters, target_level, party_size, dropped)

        self._set_body(body)
        self.container.accent_colour = color
        self.stop()
        await self._send(interaction)

    async def _resolve_boss_fight(self, db, now, d, fighters, fighter_members, fighter_characters, target_level, party_size, dropped):
        monster = d.boss
        monster_name = f"{monster.emoji} {monster.name}"
        stats = scaled_monster(monster, target_level, d.min_level, d.key, is_boss=True, party_size=party_size)
        monster_fighter = Fighter(
            name=monster_name, max_hp=stats["hp"], atk=stats["atk"], defense=stats["def"], crit=stats["crit"],
            skill_key=BOSS_SKILLS.get(d.key),
        )
        result = simulate_team(fighters, monster_fighter)
        won = result["won"]

        for member, fighter in zip(fighter_members, fighters):
            await db.set_character_hp(member.id, fighter.hp, now)

        log_tail = "\n".join(result["log"][-10:])
        header = f"👑 **Team battle vs {monster_name}!** Party: " + ", ".join(m.mention for m in fighter_members)
        if dropped:
            header += "\n⚠️ Couldn't join the fight: " + ", ".join(dropped)

        if not won:
            if result["timed_out"]:
                body = f"{header}\n\n{log_tail}\n\n😐 The fight dragged on too long and ended in a standstill. No rewards this time."
                return body, discord.Color.greyple()
            body = f"{header}\n\n{log_tail}\n\n😢 The party was defeated. No rewards this time."
            return body, discord.Color.red()

        primordial_text = ""
        if d.key in HIGH_END_DUNGEONS and random.random() < PRIMORDIAL_DROP_CHANCE:
            survivors = [m for m, f in zip(fighter_members, fighters) if f.hp > 0] or list(fighter_members)
            winner = random.choice(survivors)
            slot = random.choice(("weapon", "armor", "accessory"))
            affixes = generate_primordial_drop(slot)
            await db.add_primordial_item(winner.id, slot, json.dumps(affixes))
            base_name = PRIMORDIAL_BASES[slot].name
            primordial_text = f"\n\n💫 **PRIMORDIAL DROP!** {winner.mention} obtained {base_name} ({describe_affixes(affixes)})"

        reward_lines = []
        for member, character in zip(fighter_members, fighter_characters):
            gold_find_pct = full_stats(character).get("gold_find_pct", 0.0)
            gold = int(random.randint(*stats["gold"]) * (1 + gold_find_pct))
            await db.update_balance(member.id, gold)
            new_level, new_xp, levels_gained = apply_xp(character["level"], character["xp"], stats["xp"])
            await db.set_character_level(member.id, new_level, new_xp)
            await db.record_game_result(member.id, 0, gold)
            await db.record_boss_kill(member.id, d.key)

            line = f"{member.mention}: +{fmt(gold)} • +{stats['xp']} XP"
            if levels_gained:
                line += f" • ⬆️ Level {new_level}!"
            if monster.loot_pool and random.random() < monster.loot_chance:
                item_key = random.choice(monster.loot_pool)
                await db.add_rpg_item(member.id, item_key, 1)
                line += f" • 🎁 {EQUIPMENT[item_key].name}"
            if monster.loot_pool and random.random() < BOSS_BONUS_LOOT_CHANCE:
                bonus_key = random.choice(monster.loot_pool)
                await db.add_rpg_item(member.id, bonus_key, 1)
                line += f" • 🎁 Bonus: {EQUIPMENT[bonus_key].name}"
            reward_lines.append(line)

        footer = "\n\n👑 **BOSS DEFEATED!**\n" + "\n".join(reward_lines) + primordial_text
        body = f"{header}\n\n{log_tail}{footer}"
        return body, discord.Color.gold()

    async def _resolve_dungeon_fight(self, db, now, d, fighters, fighter_members, fighter_characters, target_level, party_size, dropped):
        monster = random.choice(d.monsters)
        event = roll_event()

        if event == TREASURE:
            lines = []
            for member, character in zip(fighter_members, fighter_characters):
                gold_find_pct = full_stats(character).get("gold_find_pct", 0.0)
                gold = int((random.randint(50, 150) + character["level"] * 5) * (1 + gold_find_pct))
                await db.update_balance(member.id, gold)
                lines.append(f"{member.mention}: +{fmt(gold)}")
            header = "💰 **Treasure Chest!** The party found loot without a fight."
            if dropped:
                header += "\n⚠️ Couldn't join: " + ", ".join(dropped)
            return f"{header}\n" + "\n".join(lines), discord.Color.gold()

        if event == MERCHANT:
            lines = []
            for member, character in zip(fighter_members, fighter_characters):
                gold_find_pct = full_stats(character).get("gold_find_pct", 0.0)
                gold = int(random.randint(30, 80) * (1 + gold_find_pct))
                await db.update_balance(member.id, gold)
                lines.append(f"{member.mention}: +{fmt(gold)}")
            header = "🧙 **A wandering merchant** pays the party for old supplies."
            if dropped:
                header += "\n⚠️ Couldn't join: " + ", ".join(dropped)
            return f"{header}\n" + "\n".join(lines), discord.Color.blue()

        elite = event == AMBUSH
        stats = scaled_monster(monster, target_level, d.min_level, d.key, party_size=party_size)
        if elite:
            for key in ("hp", "atk", "def"):
                stats[key] = int(stats[key] * 1.15)
            stats["xp"] = int(stats["xp"] * 1.4)
            stats["gold"] = (int(stats["gold"][0] * 1.4), int(stats["gold"][1] * 1.4))
        if event == CURSED:
            for f in fighters:
                f.crit = max(0.0, f.crit - 0.10)

        monster_name = f"{monster.emoji} {'Elite ' if elite else ''}{monster.name}"
        monster_fighter = Fighter(
            name=monster_name, max_hp=stats["hp"], atk=stats["atk"], defense=stats["def"], crit=stats["crit"]
        )
        result = simulate_team(fighters, monster_fighter)
        won = result["won"]

        for member, fighter in zip(fighter_members, fighters):
            await db.set_character_hp(member.id, fighter.hp, now)

        log_tail = "\n".join(result["log"][-10:])
        header_bits = []
        if elite:
            header_bits.append("⚔️ **Ambush!** A tougher foe blocks the party's path.")
        if event == CURSED:
            header_bits.append("🌑 **Cursed ground** saps the party's luck this fight.")
        header = f"**Team fight vs {monster_name}!** Party: " + ", ".join(m.mention for m in fighter_members)
        if header_bits:
            header += "\n" + "\n".join(header_bits)
        if dropped:
            header += "\n⚠️ Couldn't join the fight: " + ", ".join(dropped)

        if not won:
            if result["timed_out"]:
                body = f"{header}\n\n{log_tail}\n\n😐 The fight dragged on too long and ended in a standstill. No rewards this time."
                return body, discord.Color.greyple()
            body = f"{header}\n\n{log_tail}\n\n😢 The party was defeated. No rewards this time."
            return body, discord.Color.red()

        reward_lines = []
        for member, character in zip(fighter_members, fighter_characters):
            gold_find_pct = full_stats(character).get("gold_find_pct", 0.0)
            gold = int(random.randint(*stats["gold"]) * (1 + gold_find_pct))
            await db.update_balance(member.id, gold)
            new_level, new_xp, levels_gained = apply_xp(character["level"], character["xp"], stats["xp"])
            await db.set_character_level(member.id, new_level, new_xp)
            await db.record_game_result(member.id, 0, gold)

            line = f"{member.mention}: +{fmt(gold)} • +{stats['xp']} XP"
            if levels_gained:
                line += f" • ⬆️ Level {new_level}!"
            if monster.loot_pool and random.random() < monster.loot_chance:
                item_key = random.choice(monster.loot_pool)
                await db.add_rpg_item(member.id, item_key, 1)
                line += f" • 🎁 {EQUIPMENT[item_key].name}"
            reward_lines.append(line)

        footer = "\n\n🎉 **Victory!**\n" + "\n".join(reward_lines)
        body = f"{header}\n\n{log_tail}{footer}"
        return body, discord.Color.green()


class RPGDungeon(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._idle_tasks: dict[int, asyncio.Task] = {}
        self._idle_sessions: dict[int, dict] = {}
        self._idle_tracker_message: discord.Message | None = None
        self._idle_tracker_posted_at: datetime.datetime | None = None

    def cog_unload(self):
        for task in self._idle_tasks.values():
            task.cancel()

    async def cog_load(self):
        try:
            sessions = await self.bot.db.get_all_idle_sessions()
        except Exception:
            log.exception("[idle] failed to load persisted idle sessions")
            return

        for row in sessions:
            user_id = row["user_id"]
            d = DUNGEONS.get(row["dungeon_key"])
            if d is None:
                await self.bot.db.delete_idle_session(user_id)
                continue

            try:
                stats = json.loads(row["stats_json"])
            except (TypeError, ValueError):
                stats = None

            task = asyncio.create_task(
                self._run_idle(user_id, row["display_name"], d, row["channel_id"], row["deadline"], stats)
            )
            self._idle_tasks[user_id] = task
            task.add_done_callback(lambda _t, uid=user_id: self._idle_tasks.pop(uid, None))
            self._idle_sessions[user_id] = {"dungeon_name": d.name, "deadline": row["deadline"]}

        if sessions:
            log.info("[idle] resumed %d idle session(s) after reload", len(sessions))
            try:
                await self._update_idle_tracker()
            except Exception:
                log.exception("[idle] failed to update tracker after resuming idle sessions")

    async def _get_idle_tracker_channel(self) -> discord.abc.Messageable | None:
        channel = self.bot.get_channel(IDLE_ANNOUNCE_CHANNEL_ID)
        if channel is None:
            channel = await self.bot.fetch_channel(IDLE_ANNOUNCE_CHANNEL_ID)
        return channel

    async def _post_new_idle_tracker(self, view: StaticView) -> None:
        channel = await self._get_idle_tracker_channel()
        self._idle_tracker_message = await limited_send(channel, view=view)
        self._idle_tracker_posted_at = datetime.datetime.utcnow()
        await self.bot.db.set_idle_tracker_message(self._idle_tracker_message.id, self._idle_tracker_posted_at)

    async def _update_idle_tracker(self):
        if not IDLE_ANNOUNCE_CHANNEL_ID:
            return

        if not self._idle_sessions:
            body = "No one is currently idle farming."
        else:
            now = datetime.datetime.utcnow()
            lines = []
            for user_id, info in self._idle_sessions.items():
                remaining = max(datetime.timedelta(0), info["deadline"] - now)
                remaining_min = int(remaining.total_seconds() // 60)
                lines.append(f"• <@{user_id}> — {info['dungeon_name']} ({remaining_min}m left)")
            body = "\n".join(lines)

        view = StaticView("🏕️ Active Idle Farmers", body)
        now = datetime.datetime.utcnow()

        try:
            if self._idle_tracker_message is None:
                saved = await self.bot.db.get_idle_tracker_message()
                if saved:
                    saved_id, saved_posted_at = saved
                    if saved_posted_at and now - saved_posted_at >= IDLE_TRACKER_REPOST_AFTER:
                        await self._post_new_idle_tracker(view)
                    else:
                        try:
                            channel = await self._get_idle_tracker_channel()
                            self._idle_tracker_message = await channel.fetch_message(saved_id)
                            self._idle_tracker_posted_at = saved_posted_at
                            await limited_edit(self._idle_tracker_message, view=view)
                        except discord.NotFound:
                            await self._post_new_idle_tracker(view)
                else:
                    await self._post_new_idle_tracker(view)
            elif self._idle_tracker_posted_at and now - self._idle_tracker_posted_at >= IDLE_TRACKER_REPOST_AFTER:
                await self._post_new_idle_tracker(view)
            else:
                await limited_edit(self._idle_tracker_message, view=view)
        except discord.NotFound:
            self._idle_tracker_message = None
            await self._post_new_idle_tracker(view)
        except discord.HTTPException:
            log.exception("[idle] failed to update the idle-tracker message")

    @app_commands.command(name="dungeons", description="Shows the available RPG dungeons.")
    async def dungeons(self, interaction: discord.Interaction):
        view = StaticView("🗺️ Dungeons", _dungeon_list_text())
        await interaction.response.send_message(view=view)

    @app_commands.command(name="dungeon", description="Fight your way through a dungeon.")
    @app_commands.describe(dungeon="Which dungeon to enter", team="Start an open team-fight lobby instead of fighting solo")
    async def dungeon(self, interaction: discord.Interaction, dungeon: DungeonKey, team: bool = False):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        d = DUNGEONS[dungeon]
        if character["level"] < d.min_level:
            await interaction.response.send_message(
                f"⚠️ {d.name} recommends level {d.min_level}+. You're level {character['level']}."
            )
            return

        if team:
            view = TeamLobbyView(self, interaction.user, d, is_boss=False)
            await interaction.response.send_message(view=view)
            view.message = await interaction.original_response()
            return

        now = datetime.datetime.utcnow()
        player_stats = full_stats(character)
        hp_now = current_hp(character, player_stats["hp"], now)
        if hp_now <= 0:
            await interaction.response.send_message(
                "💀 You're too hurt to fight. Use `/heal` or wait for your HP to regenerate."
            )
            return

        outcome = await _resolve_dungeon_fight(
            self.bot, interaction.user.id, interaction.user.display_name, character, hp_now, d, now
        )

        if outcome["event"] == TREASURE:
            view = StaticView(
                f"{d.emoji} {d.name}",
                f"💰 **Treasure Chest!** You found {fmt(outcome['gold'])} without a fight.",
                color=discord.Color.gold(),
            )
            await interaction.response.send_message(view=view)
            return

        if outcome["event"] == MERCHANT:
            view = StaticView(
                f"{d.emoji} {d.name}",
                f"🧙 **A wandering merchant** pays you {fmt(outcome['gold'])} for old supplies you didn't need.",
                color=discord.Color.blue(),
            )
            await interaction.response.send_message(view=view)
            return

        hp_line = f"\n**HP:** {outcome['hp']} / {outcome['max_hp']}"
        header_bits = []
        if outcome["elite"]:
            header_bits.append("⚔️ **Ambush!** A tougher foe blocks your path.")
        if outcome["event"] == CURSED:
            header_bits.append("🌑 **Cursed ground** saps your luck this fight.")
        header = "\n".join(header_bits) + ("\n\n" if header_bits else "")

        log_tail = "\n".join(outcome["log"][-8:])
        monster_name = outcome["monster_name"]

        if outcome["won"]:
            footer = f"\n\n🎉 **Victory!** +{fmt(outcome['gold'])}  •  +{outcome['xp']} XP"
            if outcome["levels_gained"]:
                footer += f"\n⬆️ **Level up!** You're now level {outcome['new_level']}."

            loot_text = ""
            if outcome["loot_item"]:
                loot_text = f"\n🎁 **Loot!** {EQUIPMENT[outcome['loot_item']].name} dropped."

            body = f"{header}You defeated the {monster_name}!\n\n{log_tail}{footer}{loot_text}{hp_line}"
            color = discord.Color.green()
        elif outcome["timed_out"]:
            body = f"{header}You and the {monster_name} fought to a standstill...\n\n{log_tail}\n\n😐 No rewards this time.{hp_line}"
            color = discord.Color.greyple()
        else:
            downed_text = "\n💀 You've been knocked out! Use `/heal` or wait to recover." if outcome["hp"] <= 0 else ""
            body = f"{header}The {monster_name} defeated you...\n\n{log_tail}\n\n😢 No rewards this time.{hp_line}{downed_text}"
            color = discord.Color.red()

        view = StaticView(f"{d.emoji} {d.name}", body, color=color)
        await interaction.response.send_message(view=view)

    @app_commands.command(name="dungeonboss", description="Challenge a dungeon's boss for big rewards.")
    @app_commands.describe(dungeon="Which dungeon's boss to fight", team="Start an open team-fight lobby instead of fighting solo")
    async def dungeonboss(self, interaction: discord.Interaction, dungeon: DungeonKey, team: bool = False):
        character = await self.bot.db.get_character(interaction.user.id)
        if not character:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        d = DUNGEONS[dungeon]
        if character["level"] < d.min_level:
            await interaction.response.send_message(
                f"⚠️ {d.name} recommends level {d.min_level}+. You're level {character['level']}."
            )
            return

        if team:
            view = TeamLobbyView(self, interaction.user, d, is_boss=True)
            await interaction.response.send_message(view=view)
            view.message = await interaction.original_response()
            return

        now = datetime.datetime.utcnow()
        player_stats = full_stats(character)
        hp_now = current_hp(character, player_stats["hp"], now)
        if hp_now <= 0:
            await interaction.response.send_message(
                "💀 You're too hurt to fight. Use `/heal` or wait for your HP to regenerate."
            )
            return

        outcome = await _resolve_boss_fight(
            self.bot, interaction.user.id, interaction.user.display_name, character, hp_now, d, now
        )

        hp_line = f"\n**HP:** {outcome['hp']} / {outcome['max_hp']}"
        log_tail = "\n".join(outcome["log"][-10:])
        boss_name = outcome["boss_name"]

        if outcome["won"]:
            footer = f"\n\n👑 **BOSS DEFEATED!** +{fmt(outcome['gold'])}  •  +{outcome['xp']} XP  •  Kills: {outcome['kills']}"
            if outcome["levels_gained"]:
                footer += f"\n⬆️ **Level up!** You're now level {outcome['new_level']}."

            loot_text = ""
            if outcome["loot_item"]:
                loot_text = f"\n🎁 **Loot!** {EQUIPMENT[outcome['loot_item']].name} dropped."
            if outcome["bonus_loot_item"]:
                loot_text += f"\n🎁 **Bonus Loot!** {EQUIPMENT[outcome['bonus_loot_item']].name} also dropped!"
            if outcome["primordial_drop"]:
                pd = outcome["primordial_drop"]
                base_name = PRIMORDIAL_BASES[pd["slot"]].name
                loot_text += f"\n💫 **PRIMORDIAL DROP!** {base_name} ({describe_affixes(pd['affixes'])})"

            body = f"You defeated **{boss_name}**!\n\n{log_tail}{footer}{loot_text}{hp_line}"
            color = discord.Color.gold()
        elif outcome["timed_out"]:
            body = f"You and **{boss_name}** fought to a standstill...\n\n{log_tail}\n\n😐 No rewards this time.{hp_line}"
            color = discord.Color.greyple()
        else:
            downed_text = "\n💀 You've been knocked out! Use `/heal` or wait to recover." if outcome["hp"] <= 0 else ""
            body = f"**{boss_name}** was too strong...\n\n{log_tail}\n\n😢 No rewards this time.{hp_line}{downed_text}"
            color = discord.Color.red()

        view = StaticView(f"👑 {d.name} — Boss", body, color=color)
        await interaction.response.send_message(view=view)

    @app_commands.command(name="idle", description="Auto-farm a dungeon (and its boss) in the background for a set duration.")
    @app_commands.describe(dungeon="Which dungeon to farm", minutes="How long to farm for (default 30, max 120)")
    async def idle(
        self,
        interaction: discord.Interaction,
        dungeon: DungeonKey,
        minutes: app_commands.Range[int, 1, IDLE_MAX_MINUTES] = IDLE_DEFAULT_MINUTES,
    ):
        if interaction.user.id in self._idle_tasks:
            await interaction.response.send_message("⚠️ You're already idle farming. Wait for it to finish.")
            return
        self._idle_tasks[interaction.user.id] = None
        started = False
        try:
            character = await self.bot.db.get_character(interaction.user.id)
            if not character:
                await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
                return

            d = DUNGEONS[dungeon]
            if character["level"] < d.min_level:
                await interaction.response.send_message(
                    f"⚠️ {d.name} recommends level {d.min_level}+. You're level {character['level']}."
                )
                return

            await interaction.response.send_message(
                view=StaticView(
                    f"🏕️ Idle Farming — {d.name}",
                    f"Farming quietly for {minutes} minute(s). You'll get a summary when it's done.",
                )
            )
            deadline = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)

            task = asyncio.create_task(
                self._run_idle(interaction.user.id, interaction.user.display_name, d, interaction.channel_id, deadline)
            )
            self._idle_tasks[interaction.user.id] = task
            task.add_done_callback(lambda _t: self._idle_tasks.pop(interaction.user.id, None))
            started = True

            self._idle_sessions[interaction.user.id] = {
                "dungeon_name": d.name,
                "deadline": deadline,
            }
            await self._update_idle_tracker()
        finally:
            if not started:
                self._idle_tasks.pop(interaction.user.id, None)

    async def _run_idle(
        self,
        user_id: int, display_name: str, d: Dungeon, channel_id: int,
        deadline: datetime.datetime, stats: dict | None = None,
    ):
        if stats is None:
            stats = {
                "dungeon_attempts": 0, "dungeon_wins": 0, "boss_attempts": 0, "boss_wins": 0,
                "gold": 0, "xp": 0, "levels_gained": 0, "loot": [], "primordial_drops": [], "kills": {},
            }
        stats.setdefault("kills", {})

        async def _persist():
            try:
                await self.bot.db.save_idle_session(
                    user_id, d.key, display_name, deadline, channel_id, 0, json.dumps(stats)
                )
            except Exception:
                log.exception("[idle] failed to persist session state for user %s", user_id)

        await _persist()

        had_error = False
        try:
            while datetime.datetime.utcnow() < deadline:
                now = datetime.datetime.utcnow()
                character = await self.bot.db.get_character(user_id)
                if not character:
                    break

                player_stats = full_stats(character)
                hp_now = current_hp(character, player_stats["hp"], now)

                if hp_now > 0:
                    outcome = await _resolve_dungeon_fight(
                        self.bot, user_id, display_name, character, hp_now, d, now
                    )
                    if outcome["event"] in (TREASURE, MERCHANT):
                        stats["gold"] += outcome["gold"]
                    else:
                        stats["dungeon_attempts"] += 1
                        stats["gold"] += outcome["gold"]
                        stats["xp"] += outcome["xp"]
                        stats["levels_gained"] += outcome["levels_gained"]
                        if outcome["won"]:
                            stats["dungeon_wins"] += 1
                            name = outcome["monster_name"]
                            stats["kills"][name] = stats["kills"].get(name, 0) + 1
                        if outcome["loot_item"]:
                            stats["loot"].append(outcome["loot_item"])

                now = datetime.datetime.utcnow()
                character = await self.bot.db.get_character(user_id)
                if character:
                    player_stats = full_stats(character)
                    hp_now = current_hp(character, player_stats["hp"], now)
                    if hp_now > 0:
                        outcome = await _resolve_boss_fight(
                            self.bot, user_id, display_name, character, hp_now, d, now
                        )
                        stats["boss_attempts"] += 1
                        stats["gold"] += outcome["gold"]
                        stats["xp"] += outcome["xp"]
                        stats["levels_gained"] += outcome["levels_gained"]
                        if outcome["won"]:
                            stats["boss_wins"] += 1
                            name = outcome["boss_name"]
                            stats["kills"][name] = stats["kills"].get(name, 0) + 1
                        if outcome["loot_item"]:
                            stats["loot"].append(outcome["loot_item"])
                        if outcome["bonus_loot_item"]:
                            stats["loot"].append(outcome["bonus_loot_item"])
                        if outcome["primordial_drop"]:
                            stats["primordial_drops"].append(outcome["primordial_drop"])

                await _persist()
                await asyncio.sleep(IDLE_POLL_SECONDS)
        except asyncio.CancelledError:
            return
        except Exception:
            had_error = True
            log.exception("[idle] unexpected error during idle farming for user %s", user_id)

        await asyncio.shield(self._finish_idle(user_id, d, channel_id, stats, had_error))

    async def _finish_idle(
        self,
        user_id: int, d: Dungeon, channel_id: int,
        stats: dict, had_error: bool,
    ):
        try:
            character = await self.bot.db.get_character(user_id)
        except Exception:
            character = None
            log.exception("[idle] failed to fetch final character state for user %s", user_id)
        final_level = character["level"] if character else None

        loot_text = ""
        if stats["loot"]:
            counts: dict[str, int] = {}
            for key in stats["loot"]:
                counts[key] = counts.get(key, 0) + 1
            loot_text = "\n🎁 **Loot:** " + ", ".join(f"{EQUIPMENT[k].name} x{c}" for k, c in counts.items())
        if stats["primordial_drops"]:
            drop_lines = [
                f"{PRIMORDIAL_BASES[pd['slot']].name} ({describe_affixes(pd['affixes'])})"
                for pd in stats["primordial_drops"]
            ]
            loot_text += "\n💫 **Primordial Drops:** " + "; ".join(drop_lines)

        lines = [f"**{stats['dungeon_attempts']}** fight(s), **{stats['dungeon_wins']}** won"]
        if stats["boss_attempts"]:
            lines.append(f"**{stats['boss_attempts']}** boss attempt(s), **{stats['boss_wins']}** won")
        if stats["kills"]:
            kill_lines = ", ".join(f"{name} x{count}" for name, count in stats["kills"].items())
            lines.append(f"⚔️ **Kills:** {kill_lines}")
        lines.append(f"💰 **+{fmt(stats['gold'])}**  •  **+{stats['xp']} XP**")
        if stats["levels_gained"] and final_level is not None:
            lines.append(f"⬆️ Leveled up to **{final_level}**!")
        if had_error:
            lines.append("\n⚠️ *Something went wrong partway through — this is partial progress.*")

        body = "\n".join(lines) + loot_text
        title = f"🏕️ Idle Farming {'Interrupted' if had_error else 'Complete'} — {d.name}"
        color = discord.Color.orange() if had_error else discord.Color.green()

        try:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(channel_id)
            await limited_send(channel, content=f"<@{user_id}>", view=StaticView(title, body, color=color))
        except Exception:
            log.exception("[idle] failed to send final summary for user %s", user_id)

        if IDLE_ANNOUNCE_CHANNEL_ID:
            try:
                tracker_channel = await self._get_idle_tracker_channel()
                await limited_send(tracker_channel, content=f"<@{user_id}>", view=StaticView(title, body, color=color))
            except discord.HTTPException:
                log.exception("[idle] failed to send completion ping for user %s", user_id)

        self._idle_sessions.pop(user_id, None)
        try:
            await self.bot.db.delete_idle_session(user_id)
        except Exception:
            log.exception("[idle] failed to delete persisted session for user %s", user_id)
        try:
            await self._update_idle_tracker()
        except Exception:
            log.exception("[idle] failed to update the idle-tracker message for user %s", user_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGDungeon(bot))
