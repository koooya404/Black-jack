"""ブラックジャック(Streamlit版)。スマホ・タブレット向けに、すべてボタン操作で遊べる。

起動: streamlit run app.py
"""
from __future__ import annotations

import inspect

import streamlit as st

import blackjack_core as bj
import user_store as store

st.set_page_config(
    page_title="ブラックジャック",
    page_icon="🃏",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def _wide(fn) -> dict:
    """ボタンを横幅いっぱいにする引数(Streamlitのバージョン差を吸収)。"""
    return {"width": "stretch"} if "width" in inspect.signature(fn).parameters else {"use_container_width": True}


WIDE = _wide(st.button)
WIDE_FORM = _wide(st.form_submit_button)

# HTMLブロックの途中に空行やインデントを入れない(Markdownに解釈されるため)
CSS = """<style>
.block-container{max-width:600px;padding:1rem .8rem 3rem}
footer{visibility:hidden}
.hdr{display:flex;justify-content:space-between;align-items:center;font-weight:700;margin-bottom:.4rem}
.hdr .bal{background:rgba(0,0,0,.3);border-radius:2rem;padding:.15rem .8rem;color:#ffd54f}
.nm{display:flex;justify-content:space-between;font-size:.78rem;opacity:.85;margin-bottom:.2rem}
.tot{font-size:.85rem;font-weight:700;min-height:1.3rem;margin-top:.1rem}
.dealer,.me{background:rgba(0,0,0,.22);border-radius:.8rem;padding:.5rem .7rem;margin-bottom:.5rem}
.me{border:2px solid rgba(255,213,79,.55)}
.cpus{display:grid;grid-template-columns:repeat(3,1fr);gap:.4rem;margin-bottom:.5rem}
.seat{background:rgba(0,0,0,.22);border-radius:.7rem;padding:.35rem .4rem;min-width:0}
.seat .bet{font-size:.7rem;opacity:.8}
.hand{display:flex;flex-wrap:wrap}
.ph{opacity:.5;font-size:.8rem}
.card{display:inline-flex;flex-direction:column;align-items:center;justify-content:center;background:#fff;color:#111;border-radius:.45rem;border:1px solid #ccc;box-shadow:0 2px 4px rgba(0,0,0,.35);margin:0 .15rem .3rem 0;font-family:Georgia,serif;line-height:1}
.card.red{color:#c62828}
.card b{font-weight:700}
.card i{font-style:normal;font-size:1.2em}
.card.lg{width:3.6rem;height:5.1rem;font-size:1.5rem}
.card.md{width:2.9rem;height:4.1rem;font-size:1.2rem}
.card.sm{width:2.05rem;height:2.9rem;font-size:.85rem}
.card.back{background:repeating-linear-gradient(45deg,#1e4fa3,#1e4fa3 4px,#2a62c4 4px,#2a62c4 8px);border:2px solid #fff}
@media (min-width:768px){.card.lg{width:4.4rem;height:6.2rem;font-size:1.8rem}.card.md{width:3.4rem;height:4.8rem;font-size:1.4rem}.card.sm{width:2.4rem;height:3.4rem;font-size:1rem}}
.tag{display:inline-block;border-radius:.35rem;padding:0 .35rem;font-size:.72rem;font-weight:700;color:#fff}
.tag.win{background:#2e7d32}
.tag.lose{background:#c62828}
.tag.push{background:#546e7a}
.banner{text-align:center;border-radius:.8rem;padding:.6rem;margin:.2rem 0 .6rem;font-size:1.4rem;font-weight:800;color:#fff}
.banner small{display:block;font-size:.9rem;font-weight:600;opacity:.95}
.banner.win{background:#2e7d32}
.banner.lose{background:#c62828}
.banner.push{background:#546e7a}
.betbox{display:flex;justify-content:space-between;align-items:center;background:rgba(0,0,0,.28);border-radius:.8rem;padding:.5rem .9rem;margin-bottom:.5rem}
.betbox b{font-size:1.8rem;color:#ffd54f}
.welcome{text-align:center;background:rgba(0,0,0,.25);border-radius:1rem;padding:1.2rem;margin:1rem 0}
.uid{font-size:3rem;font-weight:800;letter-spacing:.3rem;color:#ffd54f;margin:.4rem 0}
div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important;gap:.5rem !important}
div[data-testid="stHorizontalBlock"]>div{min-width:0 !important;flex:1 1 0 !important;width:auto !important}
.stButton>button,.stFormSubmitButton>button{min-height:3.1rem;font-size:1.05rem;font-weight:700;border-radius:.8rem}
button[kind="primary"],button[kind="primaryFormSubmit"],button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primaryFormSubmit"]{color:#1b1b1b !important}
</style>"""

# outcome → (小さなタグ, バナー, 色)
OUTCOME = {
    "blackjack": ("BJ", "ブラックジャック!", "win"),
    "win": ("勝ち", "勝ち!", "win"),
    "push": ("引分", "引き分け", "push"),
    "lose": ("負け", "負け…", "lose"),
    "bust": ("バースト", "バースト…", "lose"),
}


# ---------------------------------------------------------------- 描画パーツ
def card_html(card: bj.Card | None, size: str) -> str:
    if card is None:
        return f'<span class="card back {size}"></span>'
    red = " red" if card.is_red else ""
    return f'<span class="card {size}{red}"><b>{card.rank}</b><i>{card.suit}</i></span>'


def hand_html(cards: list[bj.Card], size: str, hide_hole: bool = False) -> str:
    if not cards:
        return '<div class="hand"><span class="ph">—</span></div>'
    parts = [card_html(None if (hide_hole and i == 1) else c, size) for i, c in enumerate(cards)]
    return '<div class="hand">' + "".join(parts) + "</div>"


def net_text(n: int) -> str:
    if n > 0:
        return f"+{n:,}"
    if n < 0:
        return f"−{-n:,}"
    return "±0"


def total_label(seat: bj.Seat) -> str:
    if not seat.cards:
        return ""
    total = seat.total
    return f"{total}" + ("(ソフト)" if seat.soft and total <= 21 else "")


def tag_html(seat: bj.Seat, phase: str) -> str:
    if phase == "result" and seat.outcome:
        label, _, cls = OUTCOME[seat.outcome]
        return f'<span class="tag {cls}">{label} {net_text(seat.net)}</span>'
    if seat.is_blackjack:
        return '<span class="tag win">BJ</span>'
    if seat.is_bust:
        return '<span class="tag lose">バースト</span>'
    if seat.doubled:
        return '<span class="tag push">ダブル</span>'
    return ""


def dealer_html(g: bj.Game) -> str:
    hide = g.phase == "playing"
    total, tag = "", ""
    if g.dealer_cards:
        total = "?" if hide else str(g.dealer_total)
        if not hide:
            if g.dealer_bj:
                tag = '<span class="tag win">BJ</span>'
            elif g.dealer_bust:
                tag = '<span class="tag lose">バースト</span>'
    return (
        '<div class="dealer"><div class="nm"><span>ディーラー</span></div>'
        + hand_html(g.dealer_cards, "md", hide_hole=hide)
        + f'<div class="tot">{total} {tag}</div></div>'
    )


def cpu_html(seat: bj.Seat, g: bj.Game) -> str:
    body = hand_html(seat.cards, "sm") if seat.cards else '<div class="hand"><span class="ph">待機中</span></div>'
    bet = f'<div class="bet">ベット {seat.bet:,}</div>' if seat.bet else '<div class="bet">&nbsp;</div>'
    return (
        f'<div class="seat"><div class="nm"><span>{seat.name}</span><span>🪙{seat.chips:,}</span></div>'
        f'{bet}{body}<div class="tot">{total_label(seat)} {tag_html(seat, g.phase)}</div></div>'
    )


def me_html(g: bj.Game) -> str:
    me = g.human
    bet = f"ベット {me.bet:,}" if me.bet else ""
    return (
        f'<div class="me"><div class="nm"><span>あなた({me.name})</span><span>{bet}</span></div>'
        + hand_html(me.cards, "lg")
        + f'<div class="tot">{total_label(me)} {tag_html(me, g.phase)}</div></div>'
    )


# ---------------------------------------------------------------- ボタンの処理
def _g() -> bj.Game:
    return st.session_state.game


def _persist() -> None:
    store.set_chips(st.session_state.user, _g().human.chips)


def _after_action() -> None:
    if _g().phase == "result":  # ラウンドが終わったらチップを保存
        _persist()


def _clamp_bet(bet: int, chips: int) -> int:
    return max(bj.MIN_BET, min(bet, chips))


def add_bet(n: int) -> None:
    st.session_state.bet = min(st.session_state.bet + n, _g().human.chips)


def clear_bet() -> None:
    st.session_state.bet = 0


def all_in() -> None:
    st.session_state.bet = _g().human.chips


def do_deal() -> None:
    bet = st.session_state.bet
    try:
        _g().deal(bet)
    except bj.GameError:
        return
    st.session_state.last_bet = bet
    _after_action()


def do_hit() -> None:
    try:
        _g().hit()
    except bj.GameError:
        return
    _after_action()


def do_stand() -> None:
    try:
        _g().stand()
    except bj.GameError:
        return
    _after_action()


def do_double() -> None:
    try:
        _g().double()
    except bj.GameError:
        return
    _after_action()


def next_round() -> None:
    g = _g()
    if g.human.chips < bj.MIN_BET:  # 破産したら初期チップで再開
        g.human.chips = bj.START_CHIPS
        _persist()
    g.new_round()
    st.session_state.bet = _clamp_bet(st.session_state.last_bet, g.human.chips)


def start_session(uid: str) -> None:
    chips = store.get_chips(uid)
    if chips < bj.MIN_BET:
        chips = bj.START_CHIPS
        store.set_chips(uid, chips)
    st.session_state.user = uid
    st.session_state.game = bj.Game(uid, chips)
    st.session_state.bet = min(50, chips)
    st.session_state.last_bet = st.session_state.bet


def begin_after_register(uid: str) -> None:
    del st.session_state["new_user"]
    start_session(uid)


def logout() -> None:
    for key in ("user", "game", "bet", "last_bet"):
        if key in st.session_state:
            del st.session_state[key]


# ---------------------------------------------------------------- 画面
def auth_screen() -> None:
    st.markdown("## 🃏 ブラックジャック")
    tab_login, tab_reg = st.tabs(["ログイン", "新規登録"])

    with tab_login:
        with st.form("login_form"):
            uid = st.text_input("ユーザー名(4桁)", max_chars=4, key="login_id", placeholder="0001")
            pw = st.text_input("パスワード(4桁の数字)", type="password", max_chars=4, key="login_pw")
            submitted = st.form_submit_button("ログイン", type="primary", **WIDE_FORM)
        if submitted:
            if not store.valid_pin(pw):
                st.error("パスワードは4桁の数字です。")
            else:
                ok, msg = store.authenticate(uid, pw)
                if ok:
                    start_session(store.normalize_id(uid))
                    st.rerun()
                else:
                    st.error(msg)

    with tab_reg:
        st.caption("ユーザー名は登録順に自動で割り当てられます(0001〜9999)。")
        with st.form("register_form"):
            pw1 = st.text_input("パスワード(4桁の数字)", type="password", max_chars=4, key="reg_pw1")
            pw2 = st.text_input("パスワード(確認)", type="password", max_chars=4, key="reg_pw2")
            submitted = st.form_submit_button("登録する", type="primary", **WIDE_FORM)
        if submitted:
            if not store.valid_pin(pw1):
                st.error("パスワードは4桁の数字です。")
            elif pw1 != pw2:
                st.error("確認用のパスワードが一致しません。")
            else:
                try:
                    st.session_state.new_user = store.register(pw1)
                except store.UserStoreError as e:
                    st.error(str(e))
                else:
                    st.rerun()


def welcome_screen() -> None:
    uid = st.session_state.new_user
    st.markdown(
        '<div class="welcome">登録しました!<br>あなたのユーザー名'
        f'<div class="uid">{uid}</div>'
        "ログインに必要です。メモ(スクリーンショット)しておいてください。</div>",
        unsafe_allow_html=True,
    )
    st.button("ゲームを始める", key="start", type="primary", on_click=begin_after_register, args=(uid,), **WIDE)


def controls_betting(g: bj.Game) -> None:
    bet, chips = st.session_state.bet, g.human.chips
    st.markdown(
        f'<div class="betbox"><span>ベット額</span><b>🪙 {bet:,}</b></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    for col, amount in zip(cols, (10, 50, 100, 500)):
        with col:
            st.button(f"+{amount}", key=f"add{amount}", on_click=add_bet, args=(amount,), disabled=bet >= chips, **WIDE)
    c1, c2 = st.columns(2)
    with c1:
        st.button("クリア", key="clear", on_click=clear_bet, **WIDE)
    with c2:
        st.button("オールイン", key="allin", on_click=all_in, **WIDE)
    st.button(
        f"ディール(ベット {bet:,})",
        key="deal",
        type="primary",
        on_click=do_deal,
        disabled=bet < bj.MIN_BET,
        **WIDE,
    )


def controls_playing(g: bj.Game) -> None:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.button("ヒット", key="hit", type="primary", on_click=do_hit, **WIDE)
    with c2:
        st.button("スタンド", key="stand", on_click=do_stand, **WIDE)
    with c3:
        st.button("ダブル", key="double", on_click=do_double, disabled=not g.can_double, **WIDE)
    st.caption("ダブル: ベットを2倍にして1枚だけ引き、そのまま勝負")


def controls_result(g: bj.Game) -> None:
    label, banner, cls = OUTCOME[g.human.outcome]
    st.markdown(
        f'<div class="banner {cls}">{banner}<small>{net_text(g.human.net)} チップ</small></div>',
        unsafe_allow_html=True,
    )
    if g.human.chips < bj.MIN_BET:
        st.error("チップが尽きました。")
        st.button(f"チップ {bj.START_CHIPS:,} で再開", key="next", type="primary", on_click=next_round, **WIDE)
    else:
        st.button("次のラウンド", key="next", type="primary", on_click=next_round, **WIDE)


def game_screen() -> None:
    g: bj.Game = st.session_state.game
    uid = st.session_state.user

    st.markdown(
        f'<div class="hdr"><span>🃏 ユーザー {uid}</span><span class="bal">🪙 {g.human.chips:,}</span></div>',
        unsafe_allow_html=True,
    )
    table = dealer_html(g) + '<div class="cpus">' + "".join(cpu_html(s, g) for s in g.cpus) + "</div>"
    if g.phase != "betting":
        table += me_html(g)
    st.markdown(table, unsafe_allow_html=True)

    if g.events:
        st.caption(" / ".join(g.events))

    if g.phase == "betting":
        controls_betting(g)
    elif g.phase == "playing":
        controls_playing(g)
    else:
        controls_result(g)

    st.caption(f"ラウンド {g.round_no} ・ シュー残り {len(g.shoe.cards)} 枚")
    with st.expander("メニュー・ルール"):
        st.button("ログアウト", key="logout", on_click=logout, **WIDE)
        st.markdown(
            "- ブラックジャックは 3:2、通常の勝ちは 1:1、引き分けはベット返却\n"
            "- ディーラーは17以上でスタンド(ソフト17も)\n"
            "- ダブルダウンは最初の2枚のときだけ\n"
            "- チップはラウンドごとに自動保存されます\n"
            "- CPUのチップは保存されません(ログインごとに1,000から)"
        )


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if st.session_state.get("new_user"):
        welcome_screen()
    elif "user" not in st.session_state:
        auth_screen()
    else:
        game_screen()


main()
