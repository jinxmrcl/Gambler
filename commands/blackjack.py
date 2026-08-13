import discord
from discord import app_commands, ui
from discord.ext import commands

from database.db import InsufficientFunds
from utils.cards import BACK_EMOJI, Deck, hand_str, hand_value, is_blackjack
from utils.checks import game_enabled
from utils.economy import fmt, game_container, resolve_bet


class HitButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Hit", emoji="🃏")

    async def callback(self, interaction: discord.Interaction):
        await self.view.hit(interaction)


class StandButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Stand", emoji="✋")

    async def callback(self, interaction: discord.Interaction):
        await self.view.stand(interaction)


class DoubleButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Double", emoji="⏫")

    async def callback(self, interaction: discord.Interaction):
        await self.view.double(interaction)


class BlackjackView(ui.LayoutView):
    def __init__(self, cog: "Blackjack", ctx: commands.Context, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.deck = Deck()
        self.player: list = [self.deck.draw(), self.deck.draw()]
        self.dealer: list = [self.deck.draw(), self.deck.draw()]
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container("🃏 Blackjack", color=discord.Color.dark_green())
        self.hit_button = HitButton()
        self.stand_button = StandButton()
        self.double_button = DoubleButton()
        row = ui.ActionRow()
        row.add_item(self.hit_button)
        row.add_item(self.stand_button)
        row.add_item(self.double_button)
        self.container.add_item(row)
        self.add_item(self.container)

        self.render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    def render(self, *, reveal: bool = False, footer: str | None = None):
        player_total = hand_value(self.player)
        lines = [f"**Your hand:** {hand_str(self.player)}  (**{player_total}**)"]

        if reveal:
            dealer_total = hand_value(self.dealer)
            lines.append(f"**Dealer's hand:** {hand_str(self.dealer)}  (**{dealer_total}**)")
        else:
            lines.append(f"**Dealer's hand:** {self.dealer[0].emoji} {BACK_EMOJI}")

        lines.append(f"**Bet:** {fmt(self.bet)}")
        if footer:
            lines.append(f"-# {footer}")

        self.text.content = "## 🃏 Blackjack\n" + "\n".join(lines)

    async def finish(self, interaction: discord.Interaction, outcome: str):
        if self.finished:
            return
        self.finished = True
        for child in (self.hit_button, self.stand_button, self.double_button):
            child.disabled = True

        player_total = hand_value(self.player)

        if outcome == "player_blackjack":
            payout = int(self.bet * 2.5)
            result = f"🎉 Blackjack! You win {fmt(payout)}."
            color = discord.Color.gold()
        elif outcome == "bust":
            payout = 0
            result = f"💥 Busted with {player_total}! You lose {fmt(self.bet)}."
            color = discord.Color.red()
        else:
            while hand_value(self.dealer) < 17:
                self.dealer.append(self.deck.draw())
            dealer_total = hand_value(self.dealer)

            if dealer_total > 21 or player_total > dealer_total:
                payout = self.bet * 2
                result = f"🎉 You win with {player_total} against {dealer_total}! Payout: {fmt(payout)}."
                color = discord.Color.green()
            elif dealer_total > player_total:
                payout = 0
                result = f"😢 Lost: {player_total} against {dealer_total}."
                color = discord.Color.red()
            else:
                payout = self.bet
                result = f"🤝 Push ({player_total}). Bet refunded."
                color = discord.Color.greyple()

        if payout:
            await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)

        self.render(reveal=True, footer=result)
        self.container.accent_colour = color
        await interaction.response.edit_message(view=self)
        self.stop()

    async def hit(self, interaction: discord.Interaction):
        if self.finished:
            return
        self.player.append(self.deck.draw())
        if hand_value(self.player) > 21:
            await self.finish(interaction, "bust")
            return

        self.double_button.disabled = True
        self.render()
        await interaction.response.edit_message(view=self)

    async def stand(self, interaction: discord.Interaction):
        if self.finished:
            return
        await self.finish(interaction, "stand")

    async def double(self, interaction: discord.Interaction):
        if self.finished:
            return
        self.finished = True
        try:
            await self.cog.bot.db.update_balance(self.ctx.author.id, -self.bet)
        except InsufficientFunds:
            self.finished = False
            await interaction.response.send_message(
                "⚠️ You don't have enough balance to double down.", ephemeral=True
            )
            return

        self.bet *= 2
        self.finished = False
        self.player.append(self.deck.draw())
        if hand_value(self.player) > 21:
            await self.finish(interaction, "bust")
        else:
            await self.finish(interaction, "stand")

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for child in (self.hit_button, self.stand_button, self.double_button):
            child.disabled = True
        if self.message:
            while hand_value(self.dealer) < 17:
                self.dealer.append(self.deck.draw())
            player_total = hand_value(self.player)
            dealer_total = hand_value(self.dealer)
            if dealer_total > 21 or player_total > dealer_total:
                payout = self.bet * 2
            elif dealer_total == player_total:
                payout = self.bet
            else:
                payout = 0
            if payout:
                await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
            await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)
            self.render(reveal=True, footer="⏱️ Time's up — resolved automatically.")
            await self.message.edit(view=self)


class Blackjack(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="blackjack", aliases=["bj"], description="Play a round of Blackjack.")
    @app_commands.describe(bet="Bet (a number, 'half', 'all', or e.g. '50%')")
    @game_enabled("blackjack")
    async def blackjack(self, ctx: commands.Context, bet: str):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        view = BlackjackView(self, ctx, amount)

        if is_blackjack(view.player):
            for child in (view.hit_button, view.stand_button, view.double_button):
                child.disabled = True

            if is_blackjack(view.dealer):
                payout = amount
                footer = f"🤝 Both have Blackjack! Bet refunded ({fmt(payout)})."
                color = discord.Color.greyple()
            else:
                payout = int(amount * 2.5)
                footer = f"🎉 Blackjack! You win {fmt(payout)}."
                color = discord.Color.gold()

            if payout:
                await self.bot.db.update_balance(ctx.author.id, payout)
            await self.bot.db.record_game_result(ctx.author.id, amount, payout)

            view.finished = True
            view.render(reveal=True, footer=footer)
            view.container.accent_colour = color
            message = await ctx.send(view=view)
            view.message = message
            view.stop()
            return

        view.double_button.disabled = amount > await self.bot.db.get_balance(ctx.author.id)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Blackjack(bot))
