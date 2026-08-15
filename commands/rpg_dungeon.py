import asyncio
import datetime
import random
from typing import Literal

import discord
from discord import app_commands, ui
from discord.ext import commands

from rpg.character import current_hp, full_stats, to_fighter
from rpg.combat import Fighter, simulate, simulate_team
from rpg.equipment import EQUIPMENT
from rpg.events import AMBUSH, CURSED, MERCHANT, TREASURE, roll_event
from rpg.leveling import apply_xp
from rpg.monsters import DUNGEONS, Dungeon, scaled_monster
from utils.economy import StaticView, fmt, game_container
from utils.ratelimit import limited_edit

DungeonKey = Literal[
    "forest", "cave", "crypt", "volcano", "abyss", "celestial",
    "ruins", "frostpeak", "wastes", "nightmare_realm", "sunken_city",
    "voidscar", "titan_forge", "chaos_rift", "eternal_throne", "world_ender",
]

DUNGEON_COOLDOWN = 20
BOSS_COOLDOWN = 300
TEAM_LOBBY_SECONDS = 30
TEAM_MAX_SIZE = 8
IDLE_POLL_SECONDS = 5
IDLE_MAX_MINUTES = 120
IDLE_DEFAULT_MINUTES = 30


def _dungeon_list_text() -> str:
    lines = []
    for d in DUNGEONS.values():
        lines.append(f"{d.emoji} **{d.name}** — recommended level {d.min_level}+")
    return "\n".join(lines)


async def _resolve_dungeon_fight(
    bot, user_id: int, display_name: str, character: dict, hp_now: int, d: Dungeon, now: datetime.datetime
) -> dict:
    event = roll_event()
    outcome = {
        "event": event, "won": None, "elite": False, "monster_name": None, "log": [],
        "hp": hp_now, "max_hp": hp_now,
        "gold": 0, "xp": 0, "levels_gained": 0, "new_level": character["level"], "loot_item": None,
    }

    if event == TREASURE:
        gold = random.randint(50, 150) + character["level"] * 5
        await bot.db.update_balance(user_id, gold)
        outcome["gold"] = gold
        return outcome

    if event == MERCHANT:
        gold = random.randint(30, 80)
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
        hp=player_fighter.hp, max_hp=player_fighter.max_hp,
    )

    if won:
        gold = random.randint(*stats["gold"])
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
        name=boss_name, max_hp=stats["hp"], atk=stats["atk"], defense=stats["def"], crit=stats["crit"]
    )

    result = simulate(player_fighter, boss_fighter)
    won = result["winner"] is player_fighter
    await bot.db.set_character_hp(user_id, player_fighter.hp, now)

    outcome = {
        "won": won, "boss_name": boss_name, "log": result["log"],
        "hp": player_fighter.hp, "max_hp": player_fighter.max_hp,
        "gold": 0, "xp": 0, "levels_gained": 0, "new_level": character["level"],
        "loot_item": None, "kills": None,
    }

    if won:
        gold = random.randint(*stats["gold"])
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

        self.heading = f"{'👑 ' if is_boss else ''}{dungeon.emoji} {dungeon.name}{' — Boss' if is_boss else ''}"
        self.container, self.text = game_container(self.heading, self._lobby_body())
        self.join_button = JoinButton()
        self.start_button = StartButton()
        row = ui.ActionRow()
        row.add_item(self.join_button)
        row.add_item(self.start_button)
        self.container.add_item(row)
        self.add_item(self.container)

    def _lobby_body(self) -> str:
        target = self.dungeon.boss.name if self.is_boss else "a monster"
        names = "\n".join(f"• {m.mention}" for m in self.members)
        return (
            f"🤝 **Team fight!** {self.starter.mention} is gathering a party to face **{target}**.\n"
            f"Anyone with a character can **Join**. Starts automatically in {TEAM_LOBBY_SECONDS}s, "
            f"or the party leader can hit **Start Now**.\n\n**Party ({len(self.members)}):**\n{names}"
        )

    def _set_body(self, body: str):
        self.text.content = f"## {self.heading}\n{body}"

    def _disable_buttons(self):
        self.join_button.disabled = True
        self.start_button.disabled = True

    async def _send(self, interaction: discord.Interaction | None):
        if interaction is not None:
            await interaction.response.edit_message(view=self)
        elif self.message:
            await limited_edit(self.message, view=self)

    async def join(self, interaction: discord.Interaction):
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
        if self.finished:
            return
        self.finished = True
        self._disable_buttons()

        now = datetime.datetime.utcnow()
        db = self.cog.bot.db
        d = self.dungeon

        roster: list[tuple[discord.abc.User, dict]] = []
        for member in self.members:
            character = await db.get_character(member.id)
            if character and character["level"] >= d.min_level:
                roster.append((member, character))

        cooldown_key = f"boss_{d.key}" if self.is_boss else "dungeon"
        cooldown_seconds = BOSS_COOLDOWN if self.is_boss else DUNGEON_COOLDOWN
        fighters: list[Fighter] = []
        fighter_members: list[discord.abc.User] = []
        fighter_characters: list[dict] = []
        dropped: list[str] = []

        for member, character in roster:
            ok = await db.try_consume_cooldown(
                member.id, cooldown_key, datetime.timedelta(seconds=cooldown_seconds), now
            )
            if not ok:
                dropped.append(f"{member.mention} (on cooldown)")
                continue

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
            name=monster_name, max_hp=stats["hp"], atk=stats["atk"], defense=stats["def"], crit=stats["crit"]
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
            body = f"{header}\n\n{log_tail}\n\n😢 The party was defeated. No rewards this time."
            return body, discord.Color.red()

        reward_lines = []
        for member, character in zip(fighter_members, fighter_characters):
            gold = random.randint(*stats["gold"])
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
            reward_lines.append(line)

        footer = "\n\n👑 **BOSS DEFEATED!**\n" + "\n".join(reward_lines)
        body = f"{header}\n\n{log_tail}{footer}"
        return body, discord.Color.gold()

    async def _resolve_dungeon_fight(self, db, now, d, fighters, fighter_members, fighter_characters, target_level, party_size, dropped):
        monster = random.choice(d.monsters)
        event = roll_event()

        if event == TREASURE:
            lines = []
            for member, character in zip(fighter_members, fighter_characters):
                gold = random.randint(50, 150) + character["level"] * 5
                await db.update_balance(member.id, gold)
                lines.append(f"{member.mention}: +{fmt(gold)}")
            header = "💰 **Treasure Chest!** The party found loot without a fight."
            if dropped:
                header += "\n⚠️ Couldn't join: " + ", ".join(dropped)
            return f"{header}\n" + "\n".join(lines), discord.Color.gold()

        if event == MERCHANT:
            lines = []
            for member in fighter_members:
                gold = random.randint(30, 80)
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
            body = f"{header}\n\n{log_tail}\n\n😢 The party was defeated. No rewards this time."
            return body, discord.Color.red()

        reward_lines = []
        for member, character in zip(fighter_members, fighter_characters):
            gold = random.randint(*stats["gold"])
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

    def cog_unload(self):
        for task in self._idle_tasks.values():
            task.cancel()

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

        ok = await self.bot.db.try_consume_cooldown(
            interaction.user.id, "dungeon", datetime.timedelta(seconds=DUNGEON_COOLDOWN), now
        )
        if not ok:
            until = await self.bot.db.get_cooldown(interaction.user.id, "dungeon")
            remaining = int((until - now).total_seconds())
            await interaction.response.send_message(
                f"⏳ You're still resting. Try again in {remaining // 60}m {remaining % 60}s."
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

        cooldown_key = f"boss_{dungeon}"
        ok = await self.bot.db.try_consume_cooldown(
            interaction.user.id, cooldown_key, datetime.timedelta(seconds=BOSS_COOLDOWN), now
        )
        if not ok:
            until = await self.bot.db.get_cooldown(interaction.user.id, cooldown_key)
            remaining = int((until - now).total_seconds())
            await interaction.response.send_message(
                f"⏳ {d.boss.name} isn't ready to be challenged again yet. Try again in "
                f"{remaining // 60}m {remaining % 60}s."
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

            body = f"You defeated **{boss_name}**!\n\n{log_tail}{footer}{loot_text}{hp_line}"
            color = discord.Color.gold()
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

        if interaction.user.id in self._idle_tasks:
            await interaction.response.send_message("⚠️ You're already idle farming. Wait for it to finish.")
            return

        await interaction.response.send_message(
            view=StaticView(
                f"🏕️ Idle Farming — {d.name}",
                f"Farming quietly for {minutes} minute(s). You'll get a summary when it's done.",
            )
        )
        message = await interaction.original_response()

        task = asyncio.create_task(
            self._run_idle(interaction.user.id, interaction.user.display_name, d, minutes, message)
        )
        self._idle_tasks[interaction.user.id] = task
        task.add_done_callback(lambda _t: self._idle_tasks.pop(interaction.user.id, None))

    async def _run_idle(
        self, user_id: int, display_name: str, d: Dungeon, minutes: int, message: discord.Message
    ):
        stats = {
            "dungeon_attempts": 0, "dungeon_wins": 0, "boss_attempts": 0, "boss_wins": 0,
            "gold": 0, "xp": 0, "levels_gained": 0, "loot": [],
        }
        deadline = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)

        try:
            while datetime.datetime.utcnow() < deadline:
                now = datetime.datetime.utcnow()
                character = await self.bot.db.get_character(user_id)
                if not character:
                    break

                player_stats = full_stats(character)
                hp_now = current_hp(character, player_stats["hp"], now)

                if hp_now > 0:
                    ok = await self.bot.db.try_consume_cooldown(
                        user_id, "dungeon", datetime.timedelta(seconds=DUNGEON_COOLDOWN), now
                    )
                    if ok:
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
                            if outcome["loot_item"]:
                                stats["loot"].append(outcome["loot_item"])

                now = datetime.datetime.utcnow()
                character = await self.bot.db.get_character(user_id)
                if character:
                    player_stats = full_stats(character)
                    hp_now = current_hp(character, player_stats["hp"], now)
                    if hp_now > 0:
                        ok = await self.bot.db.try_consume_cooldown(
                            user_id, f"boss_{d.key}", datetime.timedelta(seconds=BOSS_COOLDOWN), now
                        )
                        if ok:
                            outcome = await _resolve_boss_fight(
                                self.bot, user_id, display_name, character, hp_now, d, now
                            )
                            stats["boss_attempts"] += 1
                            stats["gold"] += outcome["gold"]
                            stats["xp"] += outcome["xp"]
                            stats["levels_gained"] += outcome["levels_gained"]
                            if outcome["won"]:
                                stats["boss_wins"] += 1
                            if outcome["loot_item"]:
                                stats["loot"].append(outcome["loot_item"])

                await asyncio.sleep(IDLE_POLL_SECONDS)
        except asyncio.CancelledError:
            pass

        character = await self.bot.db.get_character(user_id)
        final_level = character["level"] if character else None

        loot_text = ""
        if stats["loot"]:
            counts: dict[str, int] = {}
            for key in stats["loot"]:
                counts[key] = counts.get(key, 0) + 1
            loot_text = "\n🎁 **Loot:** " + ", ".join(f"{EQUIPMENT[k].name} x{c}" for k, c in counts.items())

        lines = [f"**{stats['dungeon_attempts']}** fight(s), **{stats['dungeon_wins']}** won"]
        if stats["boss_attempts"]:
            lines.append(f"**{stats['boss_attempts']}** boss attempt(s), **{stats['boss_wins']}** won")
        lines.append(f"💰 **+{fmt(stats['gold'])}**  •  **+{stats['xp']} XP**")
        if stats["levels_gained"] and final_level is not None:
            lines.append(f"⬆️ Leveled up to **{final_level}**!")

        body = "\n".join(lines) + loot_text
        await limited_edit(
            message,
            view=StaticView(f"🏕️ Idle Farming Complete — {d.name}", body, color=discord.Color.green()),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGDungeon(bot))
