import datetime
import random

import discord
from discord import app_commands, ui
from discord.ext import commands

from rpg.character import to_fighter
from rpg.combat import simulate
from rpg.leveling import apply_xp
from utils.economy import StaticView, fmt, game_container, resolve_display_name
from utils.ratelimit import limited_edit

DUEL_GOLD_REWARD = (75, 150)
DUEL_XP_REWARD = 40
DUEL_COOLDOWN = 60


class AcceptButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Accept", emoji="⚔️")

    async def callback(self, interaction: discord.Interaction):
        await self.view.accept(interaction)


class DeclineButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Decline", emoji="❌")

    async def callback(self, interaction: discord.Interaction):
        await self.view.decline(interaction)


class DuelView(ui.LayoutView):
    def __init__(self, cog: "RPGArena", challenger: discord.abc.User, opponent: discord.abc.User):
        super().__init__(timeout=60)
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container(
            "⚔️ Duel Challenge",
            f"{challenger.mention} challenges {opponent.mention} to a duel!\n{opponent.mention}, do you accept?",
        )
        self.accept_button = AcceptButton()
        self.decline_button = DeclineButton()
        row = ui.ActionRow()
        row.add_item(self.accept_button)
        row.add_item(self.decline_button)
        self.container.add_item(row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Only the challenged player can respond to this.", ephemeral=True)
            return False
        return True

    def _disable_buttons(self):
        self.accept_button.disabled = True
        self.decline_button.disabled = True

    async def accept(self, interaction: discord.Interaction):
        if self.finished:
            return
        self.finished = True
        self._disable_buttons()

        challenger_char = await self.cog.bot.db.get_character(self.challenger.id)
        opponent_char = await self.cog.bot.db.get_character(self.opponent.id)
        if challenger_char is None or opponent_char is None:
            self.text.content = "## ⚔️ Duel Challenge\n⚠️ One of you no longer has a character."
            self.container.accent_colour = discord.Color.red()
            await interaction.response.edit_message(view=self)
            self.stop()
            return

        fighter_a = to_fighter(challenger_char, self.challenger.display_name)
        fighter_b = to_fighter(opponent_char, self.opponent.display_name)
        result = simulate(fighter_a, fighter_b)

        if result["winner"] is None:
            log_tail = "\n".join(result["log"][-8:])
            self.text.content = (
                f"## ⚔️ Duel Result\n{log_tail}\n\n"
                "🤝 The duel dragged on too long and ended in a draw. No rewards this time."
            )
            self.container.accent_colour = discord.Color.greyple()
            await interaction.response.edit_message(view=self)
            self.stop()
            return

        winner_user, loser_user = (
            (self.challenger, self.opponent) if result["winner"] is fighter_a else (self.opponent, self.challenger)
        )

        await self.cog.bot.db.record_duel_result(winner_user.id, loser_user.id)
        gold = random.randint(*DUEL_GOLD_REWARD)
        await self.cog.bot.db.update_balance(winner_user.id, gold)

        winner_char = challenger_char if winner_user is self.challenger else opponent_char
        new_level, new_xp, levels_gained = apply_xp(winner_char["level"], winner_char["xp"], DUEL_XP_REWARD)
        await self.cog.bot.db.set_character_level(winner_user.id, new_level, new_xp)

        log_tail = "\n".join(result["log"][-8:])
        footer = f"🏆 **{winner_user.display_name} wins!** +{fmt(gold)}  •  +{DUEL_XP_REWARD} XP"
        if levels_gained:
            footer += f"\n⬆️ {winner_user.display_name} leveled up to {new_level}!"

        self.text.content = f"## ⚔️ Duel Result\n{log_tail}\n\n{footer}"
        self.container.accent_colour = discord.Color.gold()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def decline(self, interaction: discord.Interaction):
        if self.finished:
            return
        self.finished = True
        self._disable_buttons()
        self.text.content = f"## ⚔️ Duel Challenge\n{self.opponent.mention} declined the duel."
        self.container.accent_colour = discord.Color.greyple()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self._disable_buttons()
        if self.message:
            self.text.content = f"## ⚔️ Duel Challenge\n⏱️ {self.opponent.mention} didn't respond in time."
            self.container.accent_colour = discord.Color.greyple()
            await limited_edit(self.message, view=self)


class RPGArena(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="duel", description="Challenge another player to a PvP duel.")
    @app_commands.describe(user="Who to challenge")
    async def duel(self, interaction: discord.Interaction, user: discord.User):
        if user.bot or user.id == interaction.user.id:
            await interaction.response.send_message("⚠️ Invalid duel target.")
            return

        challenger_char = await self.bot.db.get_character(interaction.user.id)
        if not challenger_char:
            await interaction.response.send_message("⚠️ You don't have a character yet. Use `/rpgstart` to create one.")
            return

        opponent_char = await self.bot.db.get_character(user.id)
        if not opponent_char:
            await interaction.response.send_message(f"⚠️ {user.mention} doesn't have a character yet.")
            return

        now = datetime.datetime.utcnow()
        ok = await self.bot.db.try_consume_cooldown(
            interaction.user.id, "duel", datetime.timedelta(seconds=DUEL_COOLDOWN), now
        )
        if not ok:
            until = await self.bot.db.get_cooldown(interaction.user.id, "duel")
            remaining = int((until - now).total_seconds())
            await interaction.response.send_message(
                f"⏳ You're still cooling down from your last duel. Try again in {remaining}s."
            )
            return

        view = DuelView(self, interaction.user, user)
        await interaction.response.send_message(view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="arena", description="Shows the top duelists.")
    @app_commands.describe(limit="Number of players (default: 10)")
    async def arena(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 25] = 10):
        rows = await self.bot.db.top_arena(limit * 3)
        if not rows:
            await interaction.response.send_message("There are no duelists yet.")
            return

        lines = []
        for user_id, wins, losses in rows:
            name = await resolve_display_name(self.bot, interaction.guild, user_id)
            if name is None:
                continue
            lines.append(f"**{len(lines) + 1}.** {name} — {wins}W / {losses}L")
            if len(lines) == limit:
                break

        if not lines:
            await interaction.response.send_message("There are no duelists yet.")
            return

        view = StaticView("🏆 Arena Leaderboard", "\n".join(lines))
        await interaction.response.send_message(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPGArena(bot))
