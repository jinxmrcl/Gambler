import random
from typing import Literal

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.db import InsufficientFunds
from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, StaticView, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

BASE_WIN_CHANCE = (1 - HOUSE_EDGE) / 2
WIN_CHANCE_JITTER = 0.02


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
            await self.cog.bot.db.debit_both(self.challenger.id, self.opponent.id, self.amount)
        except InsufficientFunds as exc:
            if getattr(exc, "user_id", None) == self.opponent.id:
                text = f"⚠️ {self.opponent.mention} doesn't have enough balance."
            else:
                text = f"⚠️ {self.challenger.mention} no longer has enough balance."
            self.text.content = f"## 🪙 Coinflip Challenge\n{text}"
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
        if self.finished:
            return
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
    async def coinflip(self, ctx: commands.Context, user: discord.User, amount: commands.Range[int, 1]):
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

    @commands.hybrid_command(name="soloflip", aliases=["cf"], description="Flip a coin against the house.")
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        call="Call it: heads or tails",
    )
    @game_enabled("soloflip")
    async def soloflip(self, ctx: commands.Context, bet: str, call: Literal["heads", "tails"] = "heads"):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        win_chance = random.uniform(BASE_WIN_CHANCE - WIN_CHANCE_JITTER, BASE_WIN_CHANCE + WIN_CHANCE_JITTER)
        won = random.random() < win_chance
        result = call if won else ("tails" if call == "heads" else "heads")
        payout = amount * 2 if won else 0
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        emoji = "🪙" if result == "heads" else "🥈"
        lines = [
            f"**Bet:** {fmt(amount)}  •  **Call:** {call.capitalize()}  •  **Result:** {result.capitalize()} {emoji}",
        ]
        if won:
            lines.append(f"🎉 **You won!** Payout: {fmt(payout)}")
        else:
            lines.append("😢 You lost.")

        view = StaticView(
            "🪙 Solo Coinflip", "\n".join(lines), color=discord.Color.green() if won else discord.Color.red()
        )
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Coinflip(bot))
