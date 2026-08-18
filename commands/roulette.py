import random

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import game_enabled
from utils.economy import StaticView, fmt, resolve_bet

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

DOZENS = {
    "1st12": set(range(1, 13)),
    "2nd12": set(range(13, 25)),
    "3rd12": set(range(25, 37)),
}

COLUMNS = {
    "col1": {n for n in range(1, 37) if (n - 1) % 3 == 0},
    "col2": {n for n in range(1, 37) if (n - 1) % 3 == 1},
    "col3": {n for n in range(1, 37) if (n - 1) % 3 == 2},
}


def color_of(number: int) -> str:
    if number == 0:
        return "green"
    return "red" if number in RED_NUMBERS else "black"


def _grid_pos(n: int) -> tuple[int, int]:
    triplet = (n - 1) // 3  # which row-of-3 (1,2,3 / 4,5,6 / ...) the number sits in
    slot = (n - 1) % 3  # position within that triplet, also its COLUMNS group
    return triplet, slot


def _parse_split(raw: str) -> tuple[int, int] | None:
    for sep in ("/", "-"):
        if sep not in raw:
            continue
        parts = raw.split(sep)
        if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
            return None
        a, b = int(parts[0]), int(parts[1])
        if a != b and 1 <= a <= 36 and 1 <= b <= 36:
            return (a, b)
        return None
    return None


def _is_split(a: int, b: int) -> bool:
    triplet_a, slot_a = _grid_pos(a)
    triplet_b, slot_b = _grid_pos(b)
    if triplet_a == triplet_b and abs(slot_a - slot_b) == 1:
        return True
    if slot_a == slot_b and abs(triplet_a - triplet_b) == 1:
        return True
    return False


class Roulette(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="roulette", description="Bet on a number, color, dozen, column, split, or even/odd."
    )
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        choice=(
            "A number (0-36), 'red', 'black', 'even', 'odd', a dozen ('1st12'/'2nd12'/'3rd12'), "
            "a column ('col1'/'col2'/'col3'), or a split of two adjacent numbers ('17/18')"
        ),
    )
    @game_enabled("roulette")
    async def roulette(self, ctx: commands.Context, bet: str, choice: str):
        raw_choice = choice.strip().lower()
        split_pair = _parse_split(raw_choice)

        if raw_choice in ("red", "black", "even", "odd"):
            bet_kind = raw_choice
        elif raw_choice.isdigit() and 0 <= int(raw_choice) <= 36:
            bet_kind = "number"
        elif raw_choice in DOZENS:
            bet_kind = "dozen"
        elif raw_choice in COLUMNS:
            bet_kind = "column"
        elif split_pair and _is_split(*split_pair):
            bet_kind = "split"
        else:
            await ctx.send(
                "⚠️ Invalid choice. Use a number (0-36), 'red', 'black', 'even', 'odd', a dozen "
                "('1st12'/'2nd12'/'3rd12'), a column ('col1'/'col2'/'col3'), or a split of two "
                "adjacent numbers (e.g. '17/18')."
            )
            return

        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        result = random.randint(0, 36)
        color = color_of(result)

        if bet_kind == "number":
            won = int(raw_choice) == result
            multiplier = 36.0
        elif bet_kind in ("red", "black"):
            won = raw_choice == color
            multiplier = 2.0
        elif bet_kind in ("even", "odd"):
            won = result != 0 and (result % 2 == 0) == (raw_choice == "even")
            multiplier = 2.0
        elif bet_kind == "dozen":
            won = result in DOZENS[raw_choice]
            multiplier = 3.0
        elif bet_kind == "column":
            won = result in COLUMNS[raw_choice]
            multiplier = 3.0
        else:  # split
            won = result in split_pair
            multiplier = 18.0

        payout = int(amount * multiplier) if won else 0
        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(ctx.author.id, amount, payout)

        emoji = {"red": "🔴", "black": "⚫", "green": "🟢"}[color]
        lines = [
            f"## {emoji} {result}",
            f"**Bet:** {fmt(amount)}  •  **Choice:** {choice.strip()}",
        ]
        if won:
            lines.append(f"🎉 **You won!** {multiplier:g}x → Payout {fmt(payout)}")
        else:
            lines.append("😢 You lost.")

        view = StaticView("🎡 Roulette", "\n".join(lines), color=discord.Color.green() if won else discord.Color.red())
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roulette(bot))
