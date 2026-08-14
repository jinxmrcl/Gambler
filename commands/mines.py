import random

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import HOUSE_EDGE, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

DEFAULT_COLS = 5
DEFAULT_ROWS = 4
MIN_COLS, MAX_COLS = 2, 5
MIN_ROWS, MAX_ROWS = 2, 5


def compute_total_tiles(rows: int, cols: int) -> int:
    if rows < MAX_ROWS:
        return rows * cols
    last_row_cols = cols - 1 if cols == MAX_COLS else cols
    return (rows - 1) * cols + last_row_cols


MAX_TOTAL_TILES = compute_total_tiles(MAX_ROWS, MAX_COLS)


def multiplier_for(safe_revealed: int, mines: int, total_tiles: int) -> float:
    if safe_revealed == 0:
        return 1.0
    safe_tiles = total_tiles - mines
    probability = 1.0
    for i in range(safe_revealed):
        probability *= (safe_tiles - i) / (total_tiles - i)
    fair_multiplier = 1 / probability
    return fair_multiplier * (1 - HOUSE_EDGE)


class TileButton(ui.Button):
    def __init__(self, index: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❔")
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.view.reveal(interaction, self)


class CashOutButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Cash Out", emoji="💰")

    async def callback(self, interaction: discord.Interaction):
        await self.view.cash_out(interaction)


class MinesView(ui.LayoutView):
    def __init__(self, cog: "Mines", ctx: commands.Context, bet: int, mines: int, rows: int, cols: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.bet = bet
        self.mines = mines
        self.rows = rows
        self.cols = cols
        self.total_tiles = compute_total_tiles(rows, cols)
        self.mine_positions = set(random.sample(range(self.total_tiles), mines))
        self.revealed = 0
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container("💣 Mines", color=discord.Color.dark_gold())
        self.cash_out_button = CashOutButton()
        self.cash_out_button.disabled = True

        needs_shared_row = rows >= MAX_ROWS
        self.tile_buttons: list[TileButton] = []
        index = 0
        for r in range(rows):
            row = ui.ActionRow()
            row_cols = cols - 1 if (needs_shared_row and r == rows - 1 and cols == MAX_COLS) else cols
            for c in range(row_cols):
                button = TileButton(index)
                self.tile_buttons.append(button)
                row.add_item(button)
                index += 1
            if needs_shared_row and r == rows - 1:
                row.add_item(self.cash_out_button)
            self.container.add_item(row)

        if not needs_shared_row:
            cash_row = ui.ActionRow()
            cash_row.add_item(self.cash_out_button)
            self.container.add_item(cash_row)

        self.add_item(self.container)
        self.render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    def current_multiplier(self) -> float:
        return multiplier_for(self.revealed, self.mines, self.total_tiles)

    def render(self, footer: str | None = None):
        mult = self.current_multiplier()
        potential = int(self.bet * mult)
        lines = [
            f"**Bet:** {fmt(self.bet)}",
            f"**Grid:** {self.cols}x{self.rows}",
            f"**Mines:** {self.mines}",
            f"**Multiplier:** {mult:.2f}x",
            f"**Current winnings:** {fmt(potential)}",
        ]
        if footer:
            lines.append(f"-# {footer}")
        self.text.content = "## 💣 Mines\n" + "\n".join(lines)

    async def end_game(self, interaction: discord.Interaction, *, won: bool, footer: str):
        if self.finished:
            return
        self.finished = True
        for i, button in enumerate(self.tile_buttons):
            button.disabled = True
            if i in self.mine_positions:
                button.label = "💣"
                button.style = discord.ButtonStyle.danger
            elif button.label != "💎":
                button.label = "·"
        self.cash_out_button.disabled = True

        payout = int(self.bet * self.current_multiplier()) if won else 0
        if payout:
            await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)

        self.render(footer=footer)
        self.container.accent_colour = discord.Color.green() if won else discord.Color.red()
        await interaction.response.edit_message(view=self)
        self.stop()

    async def reveal(self, interaction: discord.Interaction, button: TileButton):
        if self.finished or button.disabled:
            return

        if button.index in self.mine_positions:
            button.label = "💣"
            button.style = discord.ButtonStyle.danger
            await self.end_game(interaction, won=False, footer="💥 Boom! You hit a mine.")
            return

        button.label = "💎"
        button.style = discord.ButtonStyle.success
        button.disabled = True
        self.revealed += 1

        if self.revealed == self.total_tiles - self.mines:
            await self.end_game(interaction, won=True, footer="🎉 All safe tiles revealed!")
            return

        self.cash_out_button.disabled = False
        self.render()
        await interaction.response.edit_message(view=self)

    async def cash_out(self, interaction: discord.Interaction):
        if self.finished or self.revealed == 0:
            return
        await self.end_game(
            interaction, won=True, footer=f"💰 Cashed out at {self.current_multiplier():.2f}x."
        )

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for button in self.tile_buttons:
            button.disabled = True
        self.cash_out_button.disabled = True
        if self.message:
            payout = int(self.bet * self.current_multiplier()) if self.revealed else 0
            if payout:
                await self.cog.bot.db.update_balance(self.ctx.author.id, payout)
            await self.cog.bot.db.record_game_result(self.ctx.author.id, self.bet, payout)
            self.render(footer="⏱️ Time's up — cashed out automatically.")
            await limited_edit(self.message, view=self)


class Mines(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="mines", description="Play a round of Mines.")
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        mines=f"Number of mines on the grid (1-{MAX_TOTAL_TILES - 1}, default: 3)",
        cols=f"Grid columns ({MIN_COLS}-{MAX_COLS}, default: {DEFAULT_COLS})",
        rows=f"Grid rows ({MIN_ROWS}-{MAX_ROWS}, default: {DEFAULT_ROWS})",
    )
    @game_enabled("mines")
    async def mines(
        self,
        ctx: commands.Context,
        bet: str,
        mines: commands.Range[int, 1, MAX_TOTAL_TILES - 1] = 3,
        cols: commands.Range[int, MIN_COLS, MAX_COLS] = DEFAULT_COLS,
        rows: commands.Range[int, MIN_ROWS, MAX_ROWS] = DEFAULT_ROWS,
    ):
        total_tiles = compute_total_tiles(rows, cols)
        if mines >= total_tiles:
            await ctx.send(
                f"⚠️ Too many mines for a {cols}x{rows} grid ({total_tiles} tiles). "
                f"Pick at most {total_tiles - 1}."
            )
            return

        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        view = MinesView(self, ctx, amount, mines, rows, cols)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Mines(bot))
