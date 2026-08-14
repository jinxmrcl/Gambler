import random
from dataclasses import dataclass

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["♠", "♥", "♦", "♣"]

BACK_EMOJI = "<:7426playingcardbackside:1537551988689211412>"
JOKER_EMOJI = "<:7882playingcardjoker:1537551990513475686>"

CARD_EMOJIS = {
    ("2", "♠"): "<:8524playingcardspadestwo:1537552011774664854>",
    ("2", "♥"): "<:7102playingcardheartstwo:1537551919101247599>",
    ("2", "♦"): "<:7165playingcarddiamondstwo:1537551921706041394>",
    ("2", "♣"): "<:8842playingcardclubstwo:1537552012953002055>",
    ("3", "♠"): "<:1367playingcardspadesthree:1537551971102367774>",
    ("3", "♥"): "<:9383playingcardheartsthree:1537551929360515132>",
    ("3", "♦"): "<:5772playingcarddiamondsthree:1537551916094193714>",
    ("3", "♣"): "<:4263playingcardclubsthree:1537551976731123914>",
    ("4", "♠"): "<:9806playingcardspadesfour:1537551996758794301>",
    ("4", "♥"): "<:5715playingcardheartsfour:1537551913141276692>",
    ("4", "♦"): "<:1497playingcarddiamondsfour:1537551901476917320>",
    ("4", "♣"): "<:3948playingcardclubsfour:1537552004711194685>",
    ("5", "♠"): "<:5162playingcardspadesfive:1537551981747372143>",
    ("5", "♥"): "<:8796playingcardheartsfive:1537551927758295101>",
    ("5", "♦"): "<:4065playingcarddiamondsfive:1537551907063865344>",
    ("5", "♣"): "<:5269playingcardclubsfive:1537551983181963436>",
    ("6", "♠"): "<:4160playingcardspadessix:1537551975510573177>",
    ("6", "♥"): "<:7193playingcardheartssix:1537551922846892073>",
    ("6", "♦"): "<:1169playingcarddiamondssix:1537551900424011878>",
    ("6", "♣"): "<:7348playingcardclubssix:1537552007525703710>",
    ("7", "♠"): "<:9649playingcardspadesseven:1537551995936841860>",
    ("7", "♥"): "<:5765playingcardheartsseven:1537551914386989096>",
    ("7", "♦"): "<:2336playingcarddiamondsseven:1537551902848319588>",
    ("7", "♣"): "<:9858playingcardclubsseven:1537552015910244382>",
    ("8", "♠"): "<:5501playingcardspadeseight:1537551984280997998>",
    ("8", "♥"): "<:3572playingcardheartseight:1537551905935458364>",
    ("8", "♦"): "<:9921playingcarddiamondseight:1537551933211021422>",
    ("8", "♣"): "<:8965playingcardclubseight:1537551994212851802>",
    ("9", "♠"): "<:5071playingcardspadesnine:1537551980137029822>",
    ("9", "♥"): "<:5451playingcardheartsnine:1537551911715082402>",
    ("9", "♦"): "<:9976playingcarddiamondsnine:1537551935161376908>",
    ("9", "♣"): "<:2529playingcardclubsnine:1537551972448870460>",
    ("10", "♠"): "<:8896playingcardspadesten:1537551992812077156>",
    ("10", "♥"): "<:7963playingcardheartsten:1537551925908873249>",
    ("10", "♦"): "<:2715playingcarddiamondsten:1537551904274522152>",
    ("10", "♣"): "<:7160playingcardclubsten:1537551987401298001>",
    ("J", "♠"): "<:7377playingcardspadesjack:1537552008792383538>",
    ("J", "♦"): "<:9562playingcarddiamondsjack:1537551930761683086>",
    ("J", "♣"): "<:6968playingcardclubsjack:1537551985388027969>",
    ("Q", "♠"): "<:4328playingcardspadesqueen:1537551978744520754>",
    ("Q", "♥"): "<:4703playingcardheartsqueen:1537551908221493349>",
    ("Q", "♦"): "<:5305playingcarddiamondsqueen:1537551910213787688>",
    ("Q", "♣"): "<:7744playingcardclubsqueen:1537552010235089016>",
    ("K", "♠"): "<:9846playingcardspadesking:1537551998348697810>",
    ("K", "♥"): "<:7669playingcardheartsking:1537551924683997194>",
    ("K", "♦"): "<:7596playingcarddiamondsking:1537551899182637106>",
    ("K", "♣"): "<:9978playingcardclubsking:1537552001347616918>",
    ("A", "♠"): "<:3606playingcardspadesace:1537552003302039613>",
    ("A", "♥"): "<:7039playingcardheartsace:1537551917566140576>",
    ("A", "♦"): "<:1454playingcarddiamondsace:1537551897924337674>",
    ("A", "♣"): "<:2918playingcardclubsace:1537551974000623686>",
}


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    @property
    def emoji(self) -> str:
        return CARD_EMOJIS.get((self.rank, self.suit), str(self))

    @property
    def rank_index(self) -> int:
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
    return " ".join(c.emoji for c in cards)


def is_blackjack(cards: list[Card]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21
