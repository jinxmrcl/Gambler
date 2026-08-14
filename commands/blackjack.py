import asyncio

import discord
from discord import app_commands, ui
from discord.ext import commands

from database.db import InsufficientFunds
from utils.cards import BACK_EMOJI, Deck, hand_str, hand_value, is_blackjack
from utils.checks import game_enabled
from utils.economy import fmt, game_container, resolve_bet
from utils.ratelimit import limited_edit

DEAL_DELAY = 0.5
DRAW_DELAY = 0.5
RESOLVE_PAUSE = 0.6


class Hand:
    def __init__(self, cards: list, bet: int):
        self.cards = cards
        self.bet = bet
        self.finished = False


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


class SplitButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Split", emoji="✂️")

    async def callback(self, interaction: discord.Interaction):
        await self.view.split(interaction)


class BlackjackView(ui.LayoutView):
    def __init__(self, cog: "Blackjack", ctx: commands.Context, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.deck = Deck()
        self.hands = [Hand([self.deck.draw(), self.deck.draw()], bet)]
        self.dealer = [self.deck.draw(), self.deck.draw()]
        self.active_hand = 0
        self.finished = False
        self.message: discord.Message | None = None

        self.container, self.text = game_container("🃏 Blackjack", color=discord.Color.dark_green())
        self.hit_button = HitButton()
        self.stand_button = StandButton()
        self.double_button = DoubleButton()
        self.split_button = SplitButton()
        row = ui.ActionRow()
        row.add_item(self.hit_button)
        row.add_item(self.stand_button)
        row.add_item(self.double_button)
        row.add_item(self.split_button)
        self.container.add_item(row)
        self.add_item(self.container)

        self._set_action_buttons_disabled(True)
        self._render_dealing(0, 0)

    @property
    def current_hand(self) -> Hand:
        return self.hands[self.active_hand]

    def _can_split(self) -> bool:
        if len(self.hands) > 1:
            return False
        cards = self.hands[0].cards
        return len(cards) == 2 and cards[0].rank == cards[1].rank

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return False
        return True

    def _set_action_buttons_disabled(self, disabled: bool):
        self.hit_button.disabled = disabled
        self.stand_button.disabled = disabled
        self.double_button.disabled = disabled
        self.split_button.disabled = disabled

    def _set_initial_button_states(self):
        self.hit_button.disabled = False
        self.stand_button.disabled = False
        self.double_button.disabled = False
        self.split_button.disabled = not self._can_split()

    def _update_button_states(self):
        self.hit_button.disabled = False
        self.stand_button.disabled = False
        self.double_button.disabled = len(self.current_hand.cards) != 2
        self.split_button.disabled = True

    def _render_dealing(self, player_shown: int, dealer_shown: int):
        hand = self.hands[0]
        player_tokens = [c.emoji for c in hand.cards[:player_shown]]
        player_tokens += [BACK_EMOJI] * (len(hand.cards) - player_shown)
        dealer_tokens = [c.emoji for c in self.dealer[:dealer_shown]]
        dealer_tokens += [BACK_EMOJI] * (len(self.dealer) - dealer_shown)
        player_total = hand_value(hand.cards[:player_shown])

        lines = [
            f"**Your hand:** {' '.join(player_tokens)}  (**{player_total}**)  •  Bet: {fmt(hand.bet)}",
            f"**Dealer's hand:** {' '.join(dealer_tokens)}",
            "-# 🎴 Dealing...",
        ]
        self.text.content = "## 🃏 Blackjack\n" + "\n".join(lines)

    async def animate_deal(self):
        for player_shown, dealer_shown in ((1, 0), (1, 1), (2, 1)):
            await asyncio.sleep(DEAL_DELAY)
            self._render_dealing(player_shown, dealer_shown)
            await limited_edit(self.message, view=self)
        await asyncio.sleep(0.3)

    def render(self, *, reveal_dealer: bool = False, footer: str | None = None, pending_hand: int | None = None):
        lines = []
        multi = len(self.hands) > 1
        for i, hand in enumerate(self.hands):
            total = hand_value(hand.cards)
            cards_text = hand_str(hand.cards)
            if pending_hand == i:
                cards_text += f" {BACK_EMOJI}"
            marker = "▶️ " if (not self.finished and multi and i == self.active_hand) else ""
            label = f"Hand {i + 1}" if multi else "Your hand"
            lines.append(f"**{marker}{label}:** {cards_text}  (**{total}**)  •  Bet: {fmt(hand.bet)}")

        if reveal_dealer:
            dealer_total = hand_value(self.dealer)
            lines.append(f"**Dealer's hand:** {hand_str(self.dealer)}  (**{dealer_total}**)")
        else:
            lines.append(f"**Dealer's hand:** {self.dealer[0].emoji} {BACK_EMOJI}")

        if footer:
            lines.append(f"-# {footer}")

        self.text.content = "## 🃏 Blackjack\n" + "\n".join(lines)

    def _render_dealer_progress(self, *, pending: bool = False, footer: str | None = None):
        lines = []
        multi = len(self.hands) > 1
        for i, hand in enumerate(self.hands):
            total = hand_value(hand.cards)
            label = f"Hand {i + 1}" if multi else "Your hand"
            lines.append(f"**{label}:** {hand_str(hand.cards)}  (**{total}**)  •  Bet: {fmt(hand.bet)}")

        dealer_tokens = [c.emoji for c in self.dealer]
        if pending:
            dealer_tokens.append(BACK_EMOJI)
        lines.append(f"**Dealer's hand:** {' '.join(dealer_tokens)}  (**{hand_value(self.dealer)}**)")

        if footer:
            lines.append(f"-# {footer}")
        self.text.content = "## 🃏 Blackjack\n" + "\n".join(lines)

    async def _advance_or_finish(self):
        if self.active_hand + 1 < len(self.hands):
            self.active_hand += 1
            self._update_button_states()
            self.render()
            await limited_edit(self.message, view=self)
        else:
            await self._resolve_dealer_and_finish()

    async def _resolve_dealer_and_finish(self, *, extra_note: str | None = None):
        self.finished = True
        self._set_action_buttons_disabled(True)

        any_hand_alive = any(hand_value(h.cards) <= 21 for h in self.hands)

        self._render_dealer_progress(footer="🎴 Revealing dealer's hand...")
        await limited_edit(self.message, view=self)
        await asyncio.sleep(DEAL_DELAY)

        if any_hand_alive:
            while hand_value(self.dealer) < 17:
                self._render_dealer_progress(pending=True, footer="🎴 Dealer draws...")
                await limited_edit(self.message, view=self)
                await asyncio.sleep(DRAW_DELAY)

                self.dealer.append(self.deck.draw())
                self._render_dealer_progress(footer="🎴 Dealer draws...")
                await limited_edit(self.message, view=self)
                await asyncio.sleep(0.4)

        dealer_total = hand_value(self.dealer)

        total_payout = 0
        total_wagered = 0
        result_lines = []
        multi = len(self.hands) > 1
        for i, hand in enumerate(self.hands):
            total = hand_value(hand.cards)
            total_wagered += hand.bet
            label = f"Hand {i + 1}" if multi else "Result"

            if total > 21:
                payout = 0
                result_lines.append(f"{label}: 💥 Bust ({total}) — lost {fmt(hand.bet)}")
            elif dealer_total > 21 or total > dealer_total:
                payout = hand.bet * 2
                result_lines.append(f"{label}: 🎉 Win ({total} vs {dealer_total}) — {fmt(payout)}")
            elif dealer_total > total:
                payout = 0
                result_lines.append(f"{label}: 😢 Lost ({total} vs {dealer_total})")
            else:
                payout = hand.bet
                result_lines.append(f"{label}: 🤝 Push ({total}) — refunded")

            total_payout += payout

        if total_payout:
            await self.cog.bot.db.update_balance(self.ctx.author.id, total_payout)
        await self.cog.bot.db.record_game_result(self.ctx.author.id, total_wagered, total_payout)

        net = total_payout - total_wagered
        color = discord.Color.green() if net > 0 else (discord.Color.greyple() if net == 0 else discord.Color.red())

        footer = "\n".join(result_lines)
        if multi:
            footer += f"\n**Total:** {'+' if net >= 0 else ''}{fmt(net)}"
        if extra_note:
            footer += f"\n{extra_note}"

        self.render(reveal_dealer=True, footer=footer)
        self.container.accent_colour = color
        await limited_edit(self.message, view=self)
        self.stop()

    async def hit(self, interaction: discord.Interaction):
        if self.finished:
            return
        hand = self.current_hand
        self.double_button.disabled = True
        self.split_button.disabled = True
        self.render(footer="🎴 Drawing...", pending_hand=self.active_hand)
        await interaction.response.edit_message(view=self)
        await asyncio.sleep(DRAW_DELAY)

        hand.cards.append(self.deck.draw())
        if hand_value(hand.cards) > 21:
            hand.finished = True
            self.render(footer="💥 Bust!")
            await limited_edit(self.message, view=self)
            await asyncio.sleep(RESOLVE_PAUSE)
            await self._advance_or_finish()
        else:
            self.render()
            await limited_edit(self.message, view=self)

    async def stand(self, interaction: discord.Interaction):
        if self.finished:
            return
        self.current_hand.finished = True
        self._set_action_buttons_disabled(True)
        self.render()
        await interaction.response.edit_message(view=self)
        await self._advance_or_finish()

    async def double(self, interaction: discord.Interaction):
        if self.finished:
            return
        hand = self.current_hand
        try:
            await self.cog.bot.db.update_balance(self.ctx.author.id, -hand.bet)
        except InsufficientFunds:
            await interaction.response.send_message(
                "⚠️ You don't have enough balance to double down.", ephemeral=True
            )
            return

        hand.bet *= 2
        self._set_action_buttons_disabled(True)
        self.render(footer="🎴 Drawing...", pending_hand=self.active_hand)
        await interaction.response.edit_message(view=self)
        await asyncio.sleep(DRAW_DELAY)

        hand.cards.append(self.deck.draw())
        hand.finished = True
        busted = hand_value(hand.cards) > 21
        self.render(footer="💥 Bust!" if busted else None)
        await limited_edit(self.message, view=self)
        if busted:
            await asyncio.sleep(RESOLVE_PAUSE)
        await self._advance_or_finish()

    async def split(self, interaction: discord.Interaction):
        if self.finished or not self._can_split():
            return
        hand = self.hands[0]
        try:
            await self.cog.bot.db.update_balance(self.ctx.author.id, -hand.bet)
        except InsufficientFunds:
            await interaction.response.send_message("⚠️ You don't have enough balance to split.", ephemeral=True)
            return

        card_a, card_b = hand.cards
        is_aces = card_a.rank == "A"
        hand_a = Hand([card_a], hand.bet)
        hand_b = Hand([card_b], hand.bet)
        self.hands = [hand_a, hand_b]
        self.active_hand = 0

        self._set_action_buttons_disabled(True)
        self.render(footer="🎴 Splitting...", pending_hand=0)
        await interaction.response.edit_message(view=self)
        await asyncio.sleep(DRAW_DELAY)

        hand_a.cards.append(self.deck.draw())
        self.render(footer="🎴 Splitting...", pending_hand=1)
        await limited_edit(self.message, view=self)
        await asyncio.sleep(DRAW_DELAY)

        hand_b.cards.append(self.deck.draw())

        if is_aces:
            hand_a.finished = True
            hand_b.finished = True
            self.render(footer="Split Aces draw one card each and auto-stand.")
            await limited_edit(self.message, view=self)
            await asyncio.sleep(RESOLVE_PAUSE)
            await self._advance_or_finish()
        else:
            self._update_button_states()
            self.render()
            await limited_edit(self.message, view=self)

    async def on_timeout(self):
        if self.finished:
            return
        for hand in self.hands:
            hand.finished = True
        if self.message:
            await self._resolve_dealer_and_finish(extra_note="⏱️ Time's up — resolved automatically.")


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
        message = await ctx.send(view=view)
        view.message = message
        await view.animate_deal()

        hand = view.hands[0]
        if is_blackjack(hand.cards):
            view.render(footer="🎴 Revealing dealer's hand...")
            await limited_edit(message, view=view)
            await asyncio.sleep(DEAL_DELAY)

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
            view.render(reveal_dealer=True, footer=footer)
            view.container.accent_colour = color
            await limited_edit(message, view=view)
            view.stop()
            return

        view._set_initial_button_states()
        view.render()
        await limited_edit(message, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Blackjack(bot))
