import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import user_store as store  # noqa: E402


class UserStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(store, "DB_PATH", os.path.join(self.tmp.name, "data", "users.json"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_sequential_ids(self):
        self.assertEqual(store.register("1234"), "0001")
        self.assertEqual(store.register("5678"), "0002")
        self.assertEqual(store.register("0000"), "0003")
        self.assertEqual(store.get_chips("0002"), 1000)

    def test_invalid_pins(self):
        for bad in ("abc", "123", "12345", "", "12 4", "１２３４", "-123"):
            with self.assertRaises(store.UserStoreError, msg=bad):
                store.register(bad)
        self.assertFalse(os.path.exists(store.DB_PATH))  # 失敗では何も作られない

    def test_authenticate(self):
        uid = store.register("1234")
        self.assertEqual(store.authenticate(uid, "1234"), (True, ""))
        self.assertEqual(store.authenticate("1", "1234"), (True, ""))  # '1' → '0001'
        self.assertEqual(store.authenticate(" 0001 ", "1234"), (True, ""))
        ok, msg = store.authenticate(uid, "9999")
        self.assertFalse(ok)
        self.assertEqual(msg, store.BAD_LOGIN)
        # 存在しないユーザーも同じメッセージ
        self.assertEqual(store.authenticate("0042", "1234"), (False, store.BAD_LOGIN))
        self.assertEqual(store.authenticate("abc", "1234"), (False, store.BAD_LOGIN))

    def test_lockout_and_unlock(self):
        uid = store.register("1234")
        for _ in range(store.MAX_FAILS):
            self.assertFalse(store.authenticate(uid, "0000")[0])
        ok, msg = store.authenticate(uid, "1234")  # 正しくてもロック中
        self.assertFalse(ok)
        self.assertIn("分後", msg)
        later = store.time.time() + store.LOCK_SECONDS + 1
        with mock.patch.object(store.time, "time", return_value=later):
            self.assertEqual(store.authenticate(uid, "1234"), (True, ""))

    def test_failures_reset_after_success(self):
        uid = store.register("1234")
        for _ in range(store.MAX_FAILS - 1):
            store.authenticate(uid, "0000")
        self.assertTrue(store.authenticate(uid, "1234")[0])
        for _ in range(store.MAX_FAILS - 1):  # 成功でカウントが戻るので、またロックされない
            store.authenticate(uid, "0000")
        self.assertTrue(store.authenticate(uid, "1234")[0])

    def test_chips_persist(self):
        uid = store.register("1234")
        store.set_chips(uid, 4321)
        self.assertEqual(store.get_chips(uid), 4321)
        with open(store.DB_PATH, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["users"][uid]["chips"], 4321)

    def test_pin_not_stored_in_plaintext(self):
        uid = store.register("4821")
        with open(store.DB_PATH, encoding="utf-8") as f:
            record = json.load(f)["users"][uid]
        self.assertNotIn("password", record)
        self.assertNotIn("4821", record.values())

    def test_user_limit(self):
        os.makedirs(os.path.dirname(store.DB_PATH))
        with open(store.DB_PATH, "w", encoding="utf-8") as f:
            json.dump({"users": {"9999": {"salt": "00", "hash": "", "chips": 1}}}, f)
        with self.assertRaises(store.UserStoreError):
            store.register("1234")


if __name__ == "__main__":
    unittest.main()
