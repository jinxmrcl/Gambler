import random
from dataclasses import dataclass

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["♠", "♥", "♦", "♣"]


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def rank_index(self) -> int:
        """0 (2) through 12 (Ace) — ascending order, used by Hilo."""
        return RANKS.index(self.rank)

    @property
    def blackjack_value(self) -> int:
        if self.rank == "A":
            return 11
        if self.rank in ("J", "Q", "K"):
            return 10
        return int(self.rank)


class Deck:
    def __init__(self):
        self.cards: list[Card] = [Card(r, s) for s in SUITS for r in RANKS]
        random.shuffle(self.cards)

    def draw(self) -> Card:
        if not self.cards:
            self.cards = [Card(r, s) for s in SUITS for r in RANKS]
            random.shuffle(self.cards)
        return self.cards.pop()


def hand_value(cards: list[Card]) -> int:
    total = sum(c.blackjack_value for c in cards)
    aces = sum(1 for c in cards if c.rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def hand_str(cards: list[Card]) -> str:
    return " ".join(str(c) for c in cards)


def is_blackjack(cards: list[Card]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21
