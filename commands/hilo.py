import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.cards import Deck
from utils.economy import HOUSE_EDGE, fmt, game_container, resolve_bet


class HigherButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Higher", emoji="⬆️")

    async def callback(self, interaction: discord.Interaction):
        await self.view.resolve_guess(interaction, True)


class LowerButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger, label="Lower", emoji="⬇️")

    async def callback(self, interaction: discord.Interaction):
        await self.view.resolve_guess(interaction, False)


class CashOutButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Cash Out", emoji="💰")

    async def callback(self, interaction: discord.Interaction):
        await self.view.end_game(interaction, won=True, footer=f"💰 Cashed out at {self.view.multiplier:.2f}x.")


class HiloView(ui.LayoutView):
    def __init__(self, cog: "Hilo", ctx: commands.Context, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.deck = Deck()
        self.current = self.deck.draw()
        self.multiplier = 1.0
        self.streak = 0
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container("🎴 Hilo", color=discord.Color.purple())
        self.higher_button = HigherButton()
        self.lower_button = LowerButton()
        self.cash_out_button = CashOutButton()
        row = ui.ActionRow()
        row.add_item(self.higher_button)
        row.add_item(self.lower_button)
        row.add_item(self.cash_out_button)
        self.container.add_item(row)
        self.add_item(self.container)

        self._update_button_states()
        self.render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    def _update_button_states(self):
        self.higher_button.disabled = self.current.rank_index == 12
        self.lower_button.disabled = self.current.rank_index == 0
        self.cash_out_button.disabled = self.streak == 0

    def render(self, footer: str | None = None):
        potential = int(self.bet * self.multiplier)
        lines = [
            "**Current card:**",
            f"### {self.current}",
            f"**Streak:** {self.streak}",
            f"**Multiplier:** {self.multiplier:.2f}x",
            f"**Current winnings:** {fmt(potential)}",
        ]
        if footer:
            lines.append(f"-# {footer}")
        self.text.content = "## 🎴 Hilo\n" + "\n".join(lines)

    async def resolve_guess(self, interaction: discord.Interaction, guess_higher: bool):
        if self.finished:
            return

        remaining = self.deck.cards
        total = len(remaining)
        higher_count = sum(1 for c in remaining if c.rank_index > self.current.rank_index)
        lower_count = sum(1 for c in remaining if c.rank_index < self.current.rank_index)
        favourable = higher_count if guess_higher else lower_count

        next_card = self.deck.draw()
        won = (next_card.rank_index > self.current.rank_index) if guess_higher else (
            next_card.rank_index < self.current.rank_index
        )

        if won and favourable > 0:
            fair_multiplier = total / favourable
            self.multiplier *= fair_multiplier * (1 - HOUSE_EDGE)
            self.streak += 1
            self.current = next_card
            self._update_button_states()
            self.render()
            await interaction.response.edit_message(view=self)
        else:
            self.current = next_card
            await self.end_game(interaction, won=False, footer="😢 Wrong guess!")

    async def end_game(self, interaction: discord.Interaction, *, won: bool, footer: str):
        self.finished = True
        for child in (self.higher_button, self.lower_button, self.cash_out_button):
            child.disabled = True

        payout = int(self.bet * self.multiplier) if won else 0
        if payout:
            await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)

        self.render(footer=footer)
        self.container.accent_colour = discord.Color.green() if won else discord.Color.red()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for child in (self.higher_button, self.lower_button, self.cash_out_button):
            child.disabled = True
        if self.message:
            payout = int(self.bet * self.multiplier)
            if payout:
                await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
            await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)
            self.render(footer="⏱️ Time's up — cashed out automatically.")
            await self.message.edit(view=self)


class Hilo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="hilo", description="Guess whether the next card is higher or lower.")
    @app_commands.describe(bet="Bet (a number, 'half', 'all', or e.g. '50%')")
    async def hilo(self, ctx: commands.Context, bet: str):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        view = HiloView(self, ctx, amount)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Hilo(bot))
