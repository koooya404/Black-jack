"""app.py を、本物のStreamlitなしで通し実行するスモークテスト。

Streamlitの代わりに最小のスタブ(ボタン押下→コールバック→スクリプト再実行)を差し込み、
登録→ログイン→ベット→プレイ→結果→次ラウンド→破産→ログアウト の流れで例外が出ないこと、
チップが保存されること、描画HTMLのタグが閉じていることを確認する。
実際の見た目(CSS)は確認できないので、スマホ実機やブラウザで別途確認すること。
"""
import contextlib
import os
import random
import re
import runpy
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
APP = os.path.join(ROOT, "app.py")

import blackjack_core as bj  # noqa: E402
import user_store as store  # noqa: E402


class Rerun(Exception):
    pass


class SessionState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = SessionState()
        self.inputs = {}
        self.pressed = set()
        self.pressed_forms = set()
        self.buttons = {}
        self.html = []
        self.texts = []

    def begin_run(self):
        self.buttons, self.html, self.texts = {}, [], []

    # 何もしない/記録するだけのAPI
    def set_page_config(self, **kw): pass
    def markdown(self, body, unsafe_allow_html=False, **kw): self.html.append(body)
    def caption(self, body, **kw): self.texts.append(body)
    def error(self, body, **kw): self.texts.append("ERROR: " + body)
    def rerun(self): raise Rerun()

    @contextlib.contextmanager
    def _ctx(self):
        yield

    def tabs(self, labels): return [self._ctx() for _ in labels]
    def columns(self, n): return [self._ctx() for _ in range(n)]
    def form(self, key, **kw): return self._ctx()
    def expander(self, label, **kw): return self._ctx()

    def text_input(self, label, key=None, **kw):
        return self.inputs.get(key, "")

    def form_submit_button(self, label, **kw):
        return label in self.pressed_forms

    def button(self, label, key=None, on_click=None, args=(), disabled=False, **kw):
        self.buttons[key] = (on_click, args, disabled)
        return key in self.pressed


class App:
    def __init__(self):
        self.st = FakeStreamlit()

    def run(self):
        while True:
            self.st.begin_run()
            try:
                runpy.run_path(APP, run_name="__main__")
            except Rerun:
                self.st.pressed.clear()
                self.st.pressed_forms.clear()
                continue
            break
        self.st.pressed.clear()
        self.st.pressed_forms.clear()
        self.check_html()

    def click(self, key):
        callback, args, disabled = self.st.buttons[key]
        assert not disabled, f"button {key} is disabled"
        if callback:
            callback(*args)
        self.st.pressed.add(key)
        self.run()

    def submit(self, label, **inputs):
        self.st.inputs.update(inputs)
        self.st.pressed_forms.add(label)
        self.run()

    def has(self, key):
        return key in self.st.buttons

    def disabled(self, key):
        return self.st.buttons[key][2]

    @property
    def state(self):
        return self.st.session_state

    def check_html(self):
        for chunk in self.st.html:
            if chunk.startswith("<style"):
                continue
            for tag in ("div", "span"):
                opens = len(re.findall(rf"<{tag}[\s>]", chunk))
                closes = len(re.findall(rf"</{tag}>", chunk))
                assert opens == closes, f"<{tag}> unbalanced in: {chunk[:200]}"
            if chunk.startswith("<"):  # HTMLは空行・行頭インデントがあるとMarkdownとして崩れる
                assert "\n" not in chunk, f"newline inside HTML block: {chunk[:80]}"


class AppFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = mock.patch.object(store, "DB_PATH", os.path.join(self.tmp.name, "users.json"))
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        self.app = App()
        sys.modules["streamlit"] = self.app.st
        self.addCleanup(sys.modules.pop, "streamlit", None)
        random.seed(7)

    def register(self, pin="1234"):
        a = self.app
        a.run()
        self.assertNotIn("user", a.state)
        a.submit("登録する", reg_pw1="12ab", reg_pw2="12ab")
        self.assertTrue(any("4桁" in t for t in a.st.texts))
        a.submit("登録する", reg_pw1=pin, reg_pw2="9999")
        self.assertTrue(any("一致しません" in t for t in a.st.texts))
        a.submit("登録する", reg_pw1=pin, reg_pw2=pin)
        self.assertEqual(a.state.new_user, "0001")
        self.assertTrue(any("0001" in h for h in a.st.html))
        a.click("start")
        self.assertEqual(a.state.user, "0001")
        self.assertEqual(a.state.game.phase, "betting")

    def test_full_flow(self):
        a = self.app
        self.register()

        # ベット操作
        self.assertEqual(a.state.bet, 50)
        a.click("add100")
        self.assertEqual(a.state.bet, 150)
        a.click("clear")
        self.assertEqual(a.state.bet, 0)
        self.assertTrue(a.disabled("deal"))
        a.click("allin")
        self.assertEqual(a.state.bet, 1000)
        self.assertTrue(a.disabled("add10"))  # これ以上増やせない
        a.click("clear")
        a.click("add50")
        a.click("deal")
        self.assertIn(a.state.game.phase, ("playing", "result"))

        # 60ラウンド遊ぶ(途中オールインで破産も起こす)
        bankrupt_seen = False
        for i in range(60):
            g = a.state.game
            if g.phase == "betting":
                if i % 3 == 0:
                    a.click("allin")
                a.click("deal")
                g = a.state.game
            while g.phase == "playing":
                choices = ["hit", "stand"] + ([] if a.disabled("double") else ["double"])
                a.click(random.choice(choices))
            self.assertEqual(g.phase, "result")
            self.assertEqual(store.get_chips("0001"), g.human.chips)  # 保存されている
            if g.human.chips < bj.MIN_BET:
                bankrupt_seen = True
                self.assertTrue(any("チップが尽きました" in t for t in a.st.texts))
                a.click("next")
                self.assertEqual(g.human.chips, bj.START_CHIPS)
                self.assertEqual(store.get_chips("0001"), bj.START_CHIPS)
            else:
                a.click("next")
            self.assertEqual(g.phase, "betting")
            self.assertGreaterEqual(a.state.bet, bj.MIN_BET)
            self.assertLessEqual(a.state.bet, g.human.chips)
        self.assertTrue(bankrupt_seen, "破産ケースが一度も発生しなかった(テストの前提が崩れた)")

    def test_logout_and_login(self):
        a = self.app
        self.register()
        a.click("add10")
        a.click("deal")
        g = a.state.game
        while g.phase == "playing":
            a.click("stand")
        chips = g.human.chips
        a.click("logout")
        self.assertNotIn("user", a.state)
        a.run()  # ログイン画面に戻る

        a.submit("ログイン", login_id="1", login_pw="9999")
        self.assertTrue(any("違います" in t for t in a.st.texts))
        a.submit("ログイン", login_id="1", login_pw="abc")
        self.assertTrue(any("4桁" in t for t in a.st.texts))
        a.submit("ログイン", login_id="1", login_pw="1234")
        self.assertEqual(a.state.user, "0001")
        self.assertEqual(a.state.game.human.chips, chips)  # 前回のチップから再開


if __name__ == "__main__":
    unittest.main()
