import random

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.db import InsufficientFunds
from utils.economy import HOUSE_EDGE, fmt, game_container
from utils.ratelimit import limited_edit


class AcceptButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Accept", emoji="✅")

    async def callback(self, interaction: discord.Interaction):
        await self.view.accept(interaction)


class DeclineButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Decline", emoji="❌")

    async def callback(self, interaction: discord.Interaction):
        await self.view.decline(interaction)


class CoinflipView(ui.LayoutView):
    def __init__(self, cog: "Coinflip", challenger: discord.abc.User, opponent: discord.abc.User, amount: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent
        self.amount = amount
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container(
            "🪙 Coinflip Challenge",
            f"{challenger.mention} challenges {opponent.mention} to a coinflip for {fmt(amount)} each!\n"
            f"{opponent.mention}, do you accept?",
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

        try:
            await self.cog.bot.db.update_balance(self.challenger.id, -self.amount)
        except InsufficientFunds:
            self.text.content = f"## 🪙 Coinflip Challenge\n⚠️ {self.challenger.mention} no longer has enough balance."
            self.container.accent_colour = discord.Color.red()
            await interaction.response.edit_message(view=self)
            self.stop()
            return

        try:
            await self.cog.bot.db.update_balance(self.opponent.id, -self.amount)
        except InsufficientFunds:
            await self.cog.bot.db.update_balance(self.challenger.id, self.amount)
            self.text.content = f"## 🪙 Coinflip Challenge\n⚠️ {self.opponent.mention} doesn't have enough balance."
            self.container.accent_colour = discord.Color.red()
            await interaction.response.edit_message(view=self)
            self.stop()
            return

        total_pot = self.amount * 2
        payout = int(total_pot * (1 - HOUSE_EDGE))
        winner = random.choice([self.challenger, self.opponent])
        loser = self.opponent if winner is self.challenger else self.challenger

        await self.cog.bot.db.update_balance(winner.id, payout)
        await self.cog.bot.db.record_game_result(winner.id, self.amount, payout)
        await self.cog.bot.db.record_game_result(loser.id, self.amount, 0)

        self.text.content = (
            f"## 🪙 Coinflip Challenge\n"
            f"The coin landed on **{winner.display_name}**!\n"
            f"{winner.mention} wins {fmt(payout)}."
        )
        self.container.accent_colour = discord.Color.green()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def decline(self, interaction: discord.Interaction):
        self.finished = True
        self._disable_buttons()
        self.text.content = f"## 🪙 Coinflip Challenge\n{self.opponent.mention} declined the challenge."
        self.container.accent_colour = discord.Color.greyple()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self._disable_buttons()
        if self.message:
            self.text.content = f"## 🪙 Coinflip Challenge\n⏱️ {self.opponent.mention} didn't respond in time."
            self.container.accent_colour = discord.Color.greyple()
            await limited_edit(self.message, view=self)


class Coinflip(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="coinflip", description="Challenge another player to a coinflip wager.")
    @app_commands.describe(user="Who to challenge", amount="Amount both players wager")
    async def coinflip(self, ctx: commands.Context, user: discord.User, amount: app_commands.Range[int, 1]):
        if user.bot:
            await ctx.send("⚠️ You can't challenge bots.")
            return
        if user.id == ctx.author.id:
            await ctx.send("⚠️ You can't challenge yourself.")
            return

        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)

        challenger_balance = await self.bot.db.get_balance(ctx.author.id)
        if challenger_balance < amount:
            await ctx.send(f"⚠️ You don't have {fmt(amount)}.")
            return

        view = CoinflipView(self, ctx.author, user, amount)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Coinflip(bot))
