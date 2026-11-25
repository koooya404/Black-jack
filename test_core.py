import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import blackjack_core as bj  # noqa: E402


def C(rank: str, suit: str = "♠") -> bj.Card:
    return bj.Card(rank, suit)


def rigged(order: list[str], human_chips: int = 1000) -> bj.Game:
    """order の順にカードが配られる山札を持つGame。以降は '2' が続く。
    配札順: CPU-1, CPU-2, CPU-3, あなた, ディーラー を2周。"""
    g = bj.Game("0001", human_chips)
    g.shoe.cards = [C("2")] * 300 + [C(r) for r in reversed(order)]
    return g


# CPUは全員18(ハードハンドでスタンド)にして、余計にカードを引かせない
CPU18_UP = ["10", "10", "10"]
CPU18_DOWN = ["8", "8", "8"]


class HandValueTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual(bj.hand_value([C("A"), C("K")]), (21, True))
        self.assertEqual(bj.hand_value([C("A"), C("A"), C("9")]), (21, True))
        self.assertEqual(bj.hand_value([C("10"), C("6"), C("9")]), (25, False))
        self.assertEqual(bj.hand_value([C("A"), C("5"), C("K")]), (16, False))
        self.assertEqual(bj.hand_value([C("A"), C("6")]), (17, True))


class RiggedRoundTests(unittest.TestCase):
    def test_player_blackjack_pays_3_to_2(self):
        g = rigged(["10", "10", "10", "A", "9"] + ["7", "7", "7", "K", "7"])  # ディーラー 9+7=16 → 2を引いて18
        g.deal(50)
        self.assertEqual(g.phase, "result")  # BJは即決着
        self.assertEqual((g.human.outcome, g.human.net), ("blackjack", 75))
        self.assertEqual(g.human.chips, 1075)
        self.assertEqual(g.dealer_total, 18)

    def test_dealer_blackjack(self):
        g = rigged(["10", "10", "10", "10", "K"] + ["7", "7", "7", "9", "A"])
        g.deal(50)
        self.assertEqual(g.phase, "result")
        self.assertTrue(g.dealer_bj)
        self.assertEqual((g.human.outcome, g.human.chips), ("lose", 950))
        self.assertTrue(all(c.outcome == "lose" for c in g.cpus))

    def test_both_blackjack_is_push(self):
        g = rigged(["10", "10", "10", "A", "K"] + ["7", "7", "7", "K", "A"])
        g.deal(50)
        self.assertEqual((g.human.outcome, g.human.chips), ("push", 1000))

    def test_hit_bust(self):
        g = rigged(["10", "10", "10", "10", "10"] + ["8", "8", "8", "6", "7"] + ["K"])
        g.deal(50)
        self.assertEqual(g.phase, "playing")
        g.hit()  # 16 + K = 26
        self.assertEqual(g.phase, "result")
        self.assertEqual((g.human.outcome, g.human.net, g.human.chips), ("bust", -50, 950))
        self.assertEqual(g.dealer_total, 17)  # 17でスタンド
        self.assertTrue(all(c.outcome == "win" for c in g.cpus))  # CPUは18で勝ち

    def test_double_down_win(self):
        g = rigged(["10", "10", "10", "5", "6"] + ["8", "8", "8", "6", "10"] + ["10", "2"])
        g.deal(50)
        self.assertTrue(g.can_double)
        g.double()  # 5+6+10 = 21、ディーラー 16+2 = 18
        self.assertEqual(g.phase, "result")
        self.assertEqual((g.human.bet, g.human.net, g.human.chips), (100, 100, 1100))
        self.assertTrue(g.human.doubled)

    def test_stand_push(self):
        g = rigged(CPU18_UP + ["10", "10"] + CPU18_DOWN + ["8", "8"])
        g.deal(50)
        g.stand()
        self.assertEqual((g.human.outcome, g.human.chips), ("push", 1000))

    def test_dealer_bust_pays_win(self):
        g = rigged(CPU18_UP + ["10", "10"] + CPU18_DOWN + ["8", "6"] + ["K"])
        g.deal(50)
        g.stand()
        self.assertTrue(g.dealer_bust)
        self.assertEqual((g.human.outcome, g.human.chips), ("win", 1050))

    def test_cannot_double_after_hit_or_without_chips(self):
        g = rigged(CPU18_UP + ["2", "10"] + CPU18_DOWN + ["3", "7"] + ["2"])
        g.deal(50)
        g.hit()
        self.assertFalse(g.can_double)
        g2 = rigged(CPU18_UP + ["5", "10"] + CPU18_DOWN + ["6", "7"], human_chips=60)
        g2.deal(50)  # 残り10 < ベット50
        self.assertFalse(g2.can_double)
        with self.assertRaises(bj.GameError):
            g2.double()


class ValidationTests(unittest.TestCase):
    def test_bad_bets_and_phases(self):
        g = bj.Game("0001", 100)
        for bad in (0, 5, 101, -10):
            with self.assertRaises(bj.GameError):
                g.deal(bad)
        for action in (g.hit, g.stand, g.double):
            with self.assertRaises(bj.GameError):
                action()
        g.deal(10)
        with self.assertRaises(bj.GameError):
            g.deal(10)  # 配札後は再ベット不可

    def test_reshuffle_and_cpu_rebuy(self):
        g = bj.Game("0001", 1000)
        g.shoe.cards = g.shoe.cards[:50]
        g.cpus[0].chips = 5
        g.deal(10)
        self.assertGreater(len(g.shoe.cards), 200)
        self.assertTrue(any("シャッフル" in e for e in g.events))
        self.assertTrue(any("CPU-1" in e for e in g.events))


class SimulationTests(unittest.TestCase):
    def test_random_play_invariants(self):
        random.seed(12345)
        g = bj.Game("0001", 1000)
        for _ in range(3000):
            if g.human.chips < bj.MIN_BET:
                g.human.chips = bj.START_CHIPS
            before = g.human.chips
            bet = random.randint(bj.MIN_BET, g.human.chips)
            g.new_round()
            g.deal(bet)
            steps = 0
            while g.phase == "playing":
                steps += 1
                self.assertLess(steps, 30)
                choice = random.choice(["hit", "stand", "double"])
                if choice == "double" and not g.can_double:
                    choice = "hit"
                getattr(g, choice)()
            self.assertEqual(g.phase, "result")
            for s in g.seats:
                self.assertGreaterEqual(s.chips, 0)
                self.assertTrue(s.outcome)
            self.assertEqual(g.human.chips, before + g.human.net)
            live = any(not s.is_bust and not s.is_blackjack for s in g.seats)
            if live and not g.dealer_bj:
                self.assertGreaterEqual(g.dealer_total, bj.DEALER_STAND)


if __name__ == "__main__":
    unittest.main()
