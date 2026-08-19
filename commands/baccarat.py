import asyncio
import random
from typing import Literal

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.db import InsufficientFunds
from utils.cards import BACK_EMOJI, RANKS, SUITS, Deck
from utils.checks import game_enabled
from utils.economy import BetError, HOUSE_EDGE, fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

RTP = 1 - HOUSE_EDGE
REVEAL_DELAY = 0.6
_CALIBRATION_TRIALS = 80_000
_CALIBRATION_SEED = 20260814

BetChoice = Literal["player", "banker", "tie"]


def _rank_value(rank: str) -> int:
    if rank in ("10", "J", "Q", "K"):
        return 0
    if rank == "A":
        return 1
    return int(rank)


def _total(cards) -> int:
    return sum(_rank_value(c[0] if isinstance(c, tuple) else c.rank) for c in cards) % 10


def _banker_draws(banker_total: int, player_third_value: int | None) -> bool:
    if player_third_value is None:
        return banker_total <= 5
    if banker_total <= 2:
        return True
    if banker_total == 3:
        return player_third_value != 8
    if banker_total == 4:
        return player_third_value in (2, 3, 4, 5, 6, 7)
    if banker_total == 5:
        return player_third_value in (4, 5, 6, 7)
    if banker_total == 6:
        return player_third_value in (6, 7)
    return False


def _deal(draw_fn):
    """Plays a full hand using `draw_fn()` to get each card. Returns (player, banker)."""
    player = [draw_fn(), draw_fn()]
    banker = [draw_fn(), draw_fn()]

    if _total(player) >= 8 or _total(banker) >= 8:
        return player, banker

    player_third_value = None
    if _total(player) <= 5:
        card = draw_fn()
        player.append(card)
        player_third_value = _rank_value(card[0] if isinstance(card, tuple) else card.rank)

    if _banker_draws(_total(banker), player_third_value):
        banker.append(draw_fn())

    return player, banker


def _is_pair(cards) -> bool:
    rank_a = cards[0][0] if isinstance(cards[0], tuple) else cards[0].rank
    rank_b = cards[1][0] if isinstance(cards[1], tuple) else cards[1].rank
    return rank_a == rank_b


def _resolve(player_total: int, banker_total: int) -> str:
    if player_total == banker_total:
        return "tie"
    return "player" if player_total > banker_total else "banker"


def _calibrate_odds() -> dict[str, float]:
    rng = random.Random(_CALIBRATION_SEED)
    deck_template = [(r, s) for s in SUITS for r in RANKS]
    wins = {"player": 0, "banker": 0, "tie": 0}

    for _ in range(_CALIBRATION_TRIALS):
        deck = list(deck_template)
        rng.shuffle(deck)
        player, banker = _deal(deck.pop)
        wins[_resolve(_total(player), _total(banker))] += 1

    p_player = wins["player"] / _CALIBRATION_TRIALS
    p_banker = wins["banker"] / _CALIBRATION_TRIALS
    p_tie = wins["tie"] / _CALIBRATION_TRIALS

    return {
        "player": round((RTP - p_tie) / p_player, 2),
        "banker": round((RTP - p_tie) / p_banker, 2),
        "tie": round(RTP / p_tie, 2),
    }


PAYOUTS = _calibrate_odds()


class BaccaratView(ui.LayoutView):
    def __init__(self, bet: int, choice: str, side_lines: list[str] | None = None):
        super().__init__(timeout=None)
        self.bet = bet
        self.choice = choice
        self.side_lines = side_lines or []
        body = f"**Bet:** {fmt(bet)} on **{choice.capitalize()}** ({PAYOUTS[choice]:g}x)"
        if self.side_lines:
            body += "\n" + "\n".join(self.side_lines)
        body += "\n🎴 Dealing..."
        self.container, self.text = game_container("🎴 Baccarat", body)
        self.add_item(self.container)

    def update(self, player, banker, *, player_shown, banker_shown, footer=None, color=None):
        player_tokens = [c.emoji for c in player[:player_shown]] + [BACK_EMOJI] * (len(player) - player_shown)
        banker_tokens = [c.emoji for c in banker[:banker_shown]] + [BACK_EMOJI] * (len(banker) - banker_shown)
        player_total = _total(player[:player_shown])
        banker_total = _total(banker[:banker_shown])

        lines = [
            f"**Player:** {' '.join(player_tokens)}  (**{player_total}**)",
            f"**Banker:** {' '.join(banker_tokens)}  (**{banker_total}**)",
            f"**Bet:** {fmt(self.bet)} on **{self.choice.capitalize()}** ({PAYOUTS[self.choice]:g}x)",
        ]
        lines.extend(self.side_lines)
        if footer:
            lines.append(f"-# {footer}")
        self.text.content = "## 🎴 Baccarat\n" + "\n".join(lines)
        if color:
            self.container.accent_colour = color


class Baccarat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="baccarat", description="Bet on Player, Banker, or Tie in a game of Baccarat.")
    @app_commands.describe(
        bet="Bet (a number, 'half', 'all', or e.g. '50%')",
        choice="Who you think wins",
        player_pair="Optional side bet: wins 11:1 if Player's first two cards are a pair",
        banker_pair="Optional side bet: wins 11:1 if Banker's first two cards are a pair",
    )
    @game_enabled("baccarat")
    async def baccarat(
        self,
        ctx: commands.Context,
        bet: str,
        choice: BetChoice,
        player_pair: str | None = None,
        banker_pair: str | None = None,
    ):
        await self.bot.db.ensure_user(ctx.author.id, self.bot.starting_balance)
        amount = await resolve_bet(self.bot, ctx.author.id, bet)
        await self.bot.db.update_balance(ctx.author.id, -amount)

        pp_amount = 0
        bp_amount = 0
        try:
            if player_pair is not None:
                pp_amount = await resolve_bet(self.bot, ctx.author.id, player_pair)
                await self.bot.db.update_balance(ctx.author.id, -pp_amount)
            if banker_pair is not None:
                bp_amount = await resolve_bet(self.bot, ctx.author.id, banker_pair)
                await self.bot.db.update_balance(ctx.author.id, -bp_amount)
        except (BetError, InsufficientFunds):
            await self.bot.db.update_balance(ctx.author.id, amount + pp_amount)
            raise

        deck = Deck()
        player, banker = _deal(deck.draw)

        side_wagered = 0
        side_payout = 0
        side_lines = []
        if pp_amount:
            side_wagered += pp_amount
            if _is_pair(player):
                win = pp_amount * 12
                side_payout += win
                side_lines.append(f"👥 Player Pair: 🎉 (11:1) — {fmt(win)}")
            else:
                side_lines.append(f"👥 Player Pair: 😢 lost {fmt(pp_amount)}")
        if bp_amount:
            side_wagered += bp_amount
            if _is_pair(banker):
                win = bp_amount * 12
                side_payout += win
                side_lines.append(f"🏦 Banker Pair: 🎉 (11:1) — {fmt(win)}")
            else:
                side_lines.append(f"🏦 Banker Pair: 😢 lost {fmt(bp_amount)}")
        if side_payout:
            await self.bot.db.update_balance(ctx.author.id, side_payout)

        view = BaccaratView(amount, choice, side_lines)
        message = await ctx.send(view=view)

        steps = [(1, 0, None), (1, 1, None), (2, 1, None), (2, 2, None)]
        if len(player) == 3:
            steps.append((3, 2, "Player draws a third card..."))
        if len(banker) == 3:
            steps.append((len(player), 3, "Banker draws a third card..."))

        for player_shown, banker_shown, note in steps:
            await asyncio.sleep(REVEAL_DELAY)
            view.update(player, banker, player_shown=player_shown, banker_shown=banker_shown, footer=note or "🎴 Dealing...")
            await limited_edit(message, view=view)

        player_total = _total(player)
        banker_total = _total(banker)
        result = _resolve(player_total, banker_total)

        if result == choice:
            payout = int(amount * PAYOUTS[choice])
        elif result == "tie":
            payout = amount
        else:
            payout = 0

        if payout:
            await self.bot.db.update_balance(ctx.author.id, payout)
        await self.bot.db.record_game_result(
            ctx.author.id, amount + side_wagered, payout + side_payout
        )

        if result == choice:
            footer = f"🎉 **{result.capitalize()} wins ({player_total} vs {banker_total})!** {PAYOUTS[choice]:g}x → Payout {fmt(payout)}"
            color = discord.Color.green()
        elif result == "tie":
            footer = f"🤝 **Tie ({player_total} vs {banker_total}).** Bet refunded — {fmt(payout)}."
            color = discord.Color.greyple()
        else:
            footer = f"😢 **{result.capitalize()} wins ({player_total} vs {banker_total}).** You lost."
            color = discord.Color.red()

        view.update(player, banker, player_shown=len(player), banker_shown=len(banker), footer=footer, color=color)
        await limited_edit(message, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Baccarat(bot))
