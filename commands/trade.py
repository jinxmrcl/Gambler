from typing import Literal

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.db import InsufficientFunds
from utils.economy import fmt, game_container
from utils.items import ITEMS

TradeAsset = Literal["money", "shield", "cooldown_reset"]


def asset_label(asset: str, quantity: int) -> str:
    if asset == "money":
        return fmt(quantity)
    return f"{quantity}x {ITEMS[asset]['name']}"


async def _take(bot: commands.Bot, user_id: int, asset: str, quantity: int) -> None:
    if asset == "money":
        await bot.db.update_balance(user_id, -quantity)
    else:
        await bot.db.remove_item(user_id, asset, quantity)


async def _give(bot: commands.Bot, user_id: int, asset: str, quantity: int) -> None:
    if asset == "money":
        await bot.db.update_balance(user_id, quantity)
    else:
        await bot.db.add_item(user_id, asset, quantity)


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


class TradeView(ui.LayoutView):
    def __init__(
        self,
        cog: "Trade",
        proposer: discord.abc.User,
        target: discord.abc.User,
        give_asset: str,
        give_qty: int,
        want_asset: str,
        want_qty: int,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.proposer = proposer
        self.target = target
        self.give_asset = give_asset
        self.give_qty = give_qty
        self.want_asset = want_asset
        self.want_qty = want_qty
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container(
            "🤝 Trade Offer",
            f"{proposer.mention} offers **{asset_label(give_asset, give_qty)}** "
            f"in exchange for **{asset_label(want_asset, want_qty)}** from {target.mention}.\n"
            f"{target.mention}, do you accept?",
        )
        self.accept_button = AcceptButton()
        self.decline_button = DeclineButton()
        row = ui.ActionRow()
        row.add_item(self.accept_button)
        row.add_item(self.decline_button)
        self.container.add_item(row)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("Only the recipient can respond to this trade.", ephemeral=True)
            return False
        return True

    def _disable_buttons(self):
        self.accept_button.disabled = True
        self.decline_button.disabled = True

    async def accept(self, interaction: discord.Interaction):
        self.finished = True
        self._disable_buttons()

        try:
            await _take(self.cog.bot, self.proposer.id, self.give_asset, self.give_qty)
        except InsufficientFunds:
            self.text.content = f"## 🤝 Trade Offer\n⚠️ {self.proposer.mention} no longer has {asset_label(self.give_asset, self.give_qty)}."
            self.container.accent_colour = discord.Color.red()
            await interaction.response.edit_message(view=self)
            self.stop()
            return

        try:
            await _take(self.cog.bot, self.target.id, self.want_asset, self.want_qty)
        except InsufficientFunds:
            await _give(self.cog.bot, self.proposer.id, self.give_asset, self.give_qty)
            self.text.content = f"## 🤝 Trade Offer\n⚠️ You no longer have {asset_label(self.want_asset, self.want_qty)}."
            self.container.accent_colour = discord.Color.red()
            await interaction.response.edit_message(view=self)
            self.stop()
            return

        await _give(self.cog.bot, self.target.id, self.give_asset, self.give_qty)
        await _give(self.cog.bot, self.proposer.id, self.want_asset, self.want_qty)

        self.text.content = (
            f"## 🤝 Trade Offer\n✅ Trade completed! {self.proposer.mention} and {self.target.mention} "
            f"exchanged their goods."
        )
        self.container.accent_colour = discord.Color.green()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def decline(self, interaction: discord.Interaction):
        self.finished = True
        self._disable_buttons()
        self.text.content = f"## 🤝 Trade Offer\n{self.target.mention} declined the trade."
        self.container.accent_colour = discord.Color.greyple()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        self._disable_buttons()
        if self.message:
            self.text.content = f"## 🤝 Trade Offer\n⏱️ {self.target.mention} didn't respond in time."
            self.container.accent_colour = discord.Color.greyple()
            await self.message.edit(view=self)


class Trade(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="trade", description="Offer money or an item in exchange for money or an item.")
    @app_commands.describe(
        user="Who to trade with",
        give="What you give: 'money' or an item key",
        give_quantity="How much/many you give",
        want="What you want: 'money' or an item key",
        want_quantity="How much/many you want",
    )
    async def trade(
        self,
        ctx: commands.Context,
        user: discord.User,
        give: TradeAsset,
        give_quantity: app_commands.Range[int, 1],
        want: TradeAsset,
        want_quantity: app_commands.Range[int, 1],
    ):
        if user.bot or user.id == ctx.author.id:
            await ctx.send("⚠️ Invalid trade partner.")
            return

        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        await self.bot.db.ensure_user(user.id, self.bot.starting_balance)

        if give == "money":
            owned = await self.bot.db.get_balance(ctx.author.id)
        else:
            owned = await self.bot.db.get_item_quantity(ctx.author.id, give)
        if owned < give_quantity:
            await ctx.send(f"⚠️ You don't have {asset_label(give, give_quantity)}.")
            return

        view = TradeView(self, ctx.author, user, give, give_quantity, want, want_quantity)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Trade(bot))
