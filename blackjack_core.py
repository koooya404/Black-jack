"""ブラックジャックのゲームロジック(UIに依存しない)。

画面側は Game.phase を見て描画し、ボタン操作で deal / hit / stand / double を呼ぶだけ。

    phase: "betting" → "playing" → "result" → (new_round) → "betting" ...

席の順番はCPU-1, CPU-2, CPU-3, あなた(最後)。CPUは deal() の中で自動的にプレイを終える。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

NUM_DECKS = 6
START_CHIPS = 1000
MIN_BET = 10
CPU_NAMES = ["CPU-1", "CPU-2", "CPU-3"]
DEALER_STAND = 17  # ソフト17でもスタンド


class GameError(Exception):
    """不正な操作(ベット額が範囲外、今は操作できない、など)"""


# ---------------------------------------------------------------- カード
@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    @property
    def value(self) -> int:
        if self.rank == "A":
            return 11
        if self.rank in ("J", "Q", "K"):
            return 10
        return int(self.rank)

    @property
    def is_red(self) -> bool:
        return self.suit in ("♥", "♦")

    def __str__(self) -> str:
        return f"{self.suit}{self.rank}"


class Shoe:
    def __init__(self, num_decks: int = NUM_DECKS):
        self.num_decks = num_decks
        self.cards: list[Card] = []
        self.shuffle()

    def shuffle(self) -> None:
        self.cards = [Card(r, s) for _ in range(self.num_decks) for s in SUITS for r in RANKS]
        random.shuffle(self.cards)

    def needs_shuffle(self) -> bool:
        return len(self.cards) < 52 * self.num_decks * 0.25

    def draw(self) -> Card:
        if not self.cards:
            self.shuffle()
        return self.cards.pop()


def hand_value(cards: list[Card]) -> tuple[int, bool]:
    """(合計, ソフトハンドか)。Aは必要に応じて11→1に下げる。"""
    total = sum(c.value for c in cards)
    aces = sum(1 for c in cards if c.rank == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


# ---------------------------------------------------------------- CPU
def cpu_decide(cards: list[Card], upcard: Card, can_double: bool) -> str:
    """ベーシックストラテジー(スプリット無し版)。'h' / 's' / 'd' を返す。"""
    total, soft = hand_value(cards)
    up = upcard.value  # Aは11

    def dbl(fallback: str) -> str:
        return "d" if can_double else fallback

    if soft:
        if total >= 19:
            return "s"
        if total == 18:
            if up <= 6:
                return dbl("s")
            return "s" if up in (7, 8) else "h"
        if total in (15, 16, 17):
            return dbl("h") if 4 <= up <= 6 else "h"
        return dbl("h") if 5 <= up <= 6 else "h"  # ソフト13-14

    if total >= 17:
        return "s"
    if 13 <= total <= 16:
        return "s" if up <= 6 else "h"
    if total == 12:
        return "s" if 4 <= up <= 6 else "h"
    if total == 11:
        return dbl("h")
    if total == 10:
        return dbl("h") if up <= 9 else "h"
    if total == 9:
        return dbl("h") if 3 <= up <= 6 else "h"
    return "h"


def cpu_bet(chips: int) -> int:
    """チップの2〜10%程度をランダムに賭ける(MIN_BET単位)。"""
    low = max(MIN_BET, chips // 50)
    high = max(low, chips // 10)
    bet = random.randint(low, high) // MIN_BET * MIN_BET
    return max(MIN_BET, min(bet, chips))


# ---------------------------------------------------------------- 席
@dataclass
class Seat:
    name: str
    chips: int
    is_human: bool = False
    cards: list[Card] = field(default_factory=list)
    bet: int = 0
    doubled: bool = False
    outcome: str = ""  # "blackjack" / "win" / "push" / "lose" / "bust"(結果確定後)
    net: int = 0       # このラウンドの損益(負けは -bet)

    def reset(self) -> None:
        self.cards = []
        self.bet = 0
        self.doubled = False
        self.outcome = ""
        self.net = 0

    @property
    def total(self) -> int:
        return hand_value(self.cards)[0]

    @property
    def soft(self) -> bool:
        return hand_value(self.cards)[1]

    @property
    def is_blackjack(self) -> bool:
        return len(self.cards) == 2 and self.total == 21

    @property
    def is_bust(self) -> bool:
        return self.total > 21


# ---------------------------------------------------------------- ゲーム
class Game:
    def __init__(self, human_name: str, human_chips: int):
        self.shoe = Shoe()
        self.human = Seat(human_name, human_chips, is_human=True)
        self.cpus = [Seat(n, START_CHIPS) for n in CPU_NAMES]
        self.dealer_cards: list[Card] = []
        self.dealer_bj = False
        self.phase = "betting"
        self.round_no = 0
        self.events: list[str] = []  # 画面に出す一言(シャッフル、CPU補充など)

    # ---- 参照用
    @property
    def seats(self) -> list[Seat]:
        return self.cpus + [self.human]

    @property
    def dealer_up(self) -> Card:
        return self.dealer_cards[0]

    @property
    def dealer_total(self) -> int:
        return hand_value(self.dealer_cards)[0]

    @property
    def dealer_bust(self) -> bool:
        return self.dealer_total > 21

    @property
    def can_double(self) -> bool:
        h = self.human
        return self.phase == "playing" and len(h.cards) == 2 and h.chips >= h.bet

    # ---- ラウンド進行
    def new_round(self) -> None:
        """結果画面からベット画面へ戻す。"""
        self.phase = "betting"
        for s in self.seats:
            s.reset()
        self.dealer_cards = []
        self.dealer_bj = False
        self.events = []

    def deal(self, bet: int) -> None:
        if self.phase != "betting":
            raise GameError("今はベットできません。")
        if not (MIN_BET <= bet <= self.human.chips):
            raise GameError(f"ベットは {MIN_BET}〜{self.human.chips} で指定してください。")

        self.round_no += 1
        self.events = []
        if self.shoe.needs_shuffle():
            self.shoe.shuffle()
            self.events.append("シューをシャッフルしました")

        for s in self.cpus:
            if s.chips < MIN_BET:  # 破産したCPUは新しい持ち金で再参加
                s.chips = START_CHIPS
                self.events.append(f"{s.name} がチップを補充しました")
            s.bet = cpu_bet(s.chips)
            s.chips -= s.bet
        self.human.bet = bet
        self.human.chips -= bet

        for _ in range(2):
            for s in self.seats:
                s.cards.append(self.shoe.draw())
            self.dealer_cards.append(self.shoe.draw())

        # ディーラーがA/10点札を見せているときは、先にブラックジャックを確認(ピーク)
        self.dealer_bj = self.dealer_up.value in (10, 11) and self.dealer_total == 21
        if self.dealer_bj:
            self._finish()
            return

        for s in self.cpus:
            self._cpu_turn(s)
        self.phase = "playing"
        if self.human.is_blackjack:
            self._finish()

    def hit(self) -> None:
        self._require_playing()
        self.human.cards.append(self.shoe.draw())
        if self.human.total >= 21:  # バースト or 21で自動スタンド
            self._finish()

    def stand(self) -> None:
        self._require_playing()
        self._finish()

    def double(self) -> None:
        self._require_playing()
        if not self.can_double:
            raise GameError("ダブルダウンできません。")
        h = self.human
        h.chips -= h.bet
        h.bet *= 2
        h.doubled = True
        h.cards.append(self.shoe.draw())
        self._finish()

    # ---- 内部処理
    def _require_playing(self) -> None:
        if self.phase != "playing":
            raise GameError("今は操作できません。")

    def _cpu_turn(self, s: Seat) -> None:
        while not s.is_bust and s.total < 21:
            can_double = len(s.cards) == 2 and s.chips >= s.bet
            action = cpu_decide(s.cards, self.dealer_up, can_double)
            if action == "s":
                break
            if action == "d":
                s.chips -= s.bet
                s.bet *= 2
                s.doubled = True
                s.cards.append(self.shoe.draw())
                break
            s.cards.append(self.shoe.draw())

    def _finish(self) -> None:
        live = any(not s.is_bust and not s.is_blackjack for s in self.seats)
        if not self.dealer_bj and live:
            while self.dealer_total < DEALER_STAND:
                self.dealer_cards.append(self.shoe.draw())
        for s in self.seats:
            self._settle(s)
        self.phase = "result"

    def _settle(self, s: Seat) -> None:
        """損益を確定してチップに反映する(ベットは配札時に引き落とし済み)。"""
        if s.is_blackjack:
            if self.dealer_bj:
                s.outcome, s.net = "push", 0
            else:
                s.outcome, s.net = "blackjack", s.bet * 3 // 2
        elif s.is_bust:
            s.outcome, s.net = "bust", -s.bet
        elif self.dealer_bj:
            s.outcome, s.net = "lose", -s.bet
        elif self.dealer_bust or s.total > self.dealer_total:
            s.outcome, s.net = "win", s.bet
        elif s.total == self.dealer_total:
            s.outcome, s.net = "push", 0
        else:
            s.outcome, s.net = "lose", -s.bet
        s.chips += s.bet + s.net
