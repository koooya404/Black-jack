"""ユーザー登録・ログイン・チップ保存(JSONファイル)。

- ユーザー名は登録順に 0001〜9999 を自動採番
- パスワードは任意の4桁の数字(ソルト付きPBKDF2ハッシュで保存)
- 連続で間違えるとしばらくロック(4桁は1万通りしかないため)

保存先は環境変数 BJ_DB_PATH で変更できる(既定: ./data/users.json)。
注意: Streamlit Community Cloud などはディスクが永続しない(再起動・再デプロイで消える)。
      長く使うなら、このファイルの load/save を外部DBに差し替えること。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from datetime import datetime

DB_PATH = os.environ.get("BJ_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "users.json"
)
START_CHIPS = 1000
MAX_USERS = 9999
MAX_FAILS = 5
LOCK_SECONDS = 600
PBKDF2_ROUNDS = 100_000

BAD_LOGIN = "ユーザー名またはパスワードが違います。"

_lock = threading.RLock()  # Streamlitは1プロセス内で複数セッションを処理する


class UserStoreError(Exception):
    pass


# ---------------------------------------------------------------- 入出力
def _load() -> dict:
    try:
        with open(DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"users": {}}


def _save(db: dict) -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_PATH)  # 書き込み途中で壊れないよう置き換え


def _hash_pw(pw: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), PBKDF2_ROUNDS).hex()


# ---------------------------------------------------------------- 検証
def valid_pin(pw: str) -> bool:
    return len(pw) == 4 and pw.isascii() and pw.isdigit()


def normalize_id(raw: str) -> str:
    """'1' → '0001'。数字以外はそのまま返す(存在しないIDとして扱われる)。"""
    raw = (raw or "").strip()
    return raw.zfill(4) if raw.isascii() and raw.isdigit() else raw


# ---------------------------------------------------------------- 公開API
def register(pw: str) -> str:
    """新規登録して、割り当てたユーザー名(例 '0001')を返す。"""
    if not valid_pin(pw):
        raise UserStoreError("パスワードは4桁の数字です。")
    with _lock:
        db = _load()
        next_id = max((int(k) for k in db["users"]), default=0) + 1
        if next_id > MAX_USERS:
            raise UserStoreError("登録人数の上限(9999人)に達しています。")
        uid = f"{next_id:04d}"
        salt = os.urandom(16).hex()
        db["users"][uid] = {
            "salt": salt,
            "hash": _hash_pw(pw, salt),
            "chips": START_CHIPS,
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        _save(db)
        return uid


def authenticate(raw_id: str, pw: str) -> tuple[bool, str]:
    """(成功か, 失敗時のメッセージ)。"""
    uid = normalize_id(raw_id)
    with _lock:
        db = _load()
        user = db["users"].get(uid)
        if user is None:
            _hash_pw(pw, "00" * 16)  # 存在有無で応答時間が変わらないように
            return False, BAD_LOGIN

        now = time.time()
        if user.get("locked_until", 0) > now:
            minutes = int((user["locked_until"] - now) // 60) + 1
            return False, f"試行回数が多すぎます。約{minutes}分後にもう一度お試しください。"

        if hmac.compare_digest(_hash_pw(pw, user["salt"]), user["hash"]):
            if user.get("fails") or user.get("locked_until"):
                user["fails"], user["locked_until"] = 0, 0
                _save(db)
            return True, ""

        user["fails"] = user.get("fails", 0) + 1
        if user["fails"] >= MAX_FAILS:
            user["fails"] = 0
            user["locked_until"] = now + LOCK_SECONDS
        _save(db)
        return False, BAD_LOGIN


def get_chips(uid: str) -> int:
    with _lock:
        return int(_load()["users"][uid]["chips"])


def set_chips(uid: str, chips: int) -> None:
    with _lock:
        db = _load()
        db["users"][uid]["chips"] = int(chips)
        _save(db)
