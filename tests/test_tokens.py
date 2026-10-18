import tempfile
import unittest
from pathlib import Path

from aeromancer import tokens
from aeromancer.store import Store

NOW = 1_790_000_000.0


class TokensTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "db.sqlite3")

    def tearDown(self):
        self.store.close()
        self.dir.cleanup()

    def test_checks_only_its_own_scope(self):
        view = tokens.issue(self.store, "alice", "view", None, now=NOW)
        write = tokens.issue(self.store, "laptop", "write", None, now=NOW)
        self.assertEqual(tokens.check(self.store, view, "view", now=NOW).name, "alice")
        self.assertIsNone(tokens.check(self.store, view, "write", now=NOW))
        self.assertEqual(tokens.check(self.store, write, "write", now=NOW).name, "laptop")
        self.assertIsNone(tokens.check(self.store, write, "view", now=NOW))

    def test_expires(self):
        secret = tokens.issue(self.store, "alice", "view", 3600, now=NOW)
        self.assertIsNotNone(tokens.check(self.store, secret, "view", now=NOW + 3599))
        self.assertIsNone(tokens.check(self.store, secret, "view", now=NOW + 3600))

    def test_revoked_at_once(self):
        secret = tokens.issue(self.store, "alice", "view", None, now=NOW)
        (token,) = tokens.list_tokens(self.store)
        self.assertTrue(tokens.revoke(self.store, token.id, now=NOW + 1))
        self.assertFalse(tokens.revoke(self.store, token.id))
        self.assertIsNone(tokens.check(self.store, secret, "view", now=NOW + 2))

    def test_stores_no_secret(self):
        secret = tokens.issue(self.store, "alice", "view", None, now=NOW)
        dump = "\n".join(self.store.db.iterdump())
        self.assertNotIn(secret, dump)
        self.assertNotIn(secret[len(tokens.PREFIX) :], dump)

    def test_refuses_nonsense(self):
        tokens.issue(self.store, "alice", "view", None, now=NOW)
        for secret in (None, "", "aer_", "aer_nope", "garbage"):
            self.assertIsNone(tokens.check(self.store, secret, "view", now=NOW))
        with self.assertRaises(ValueError):
            tokens.issue(self.store, "eve", "admin", None)


if __name__ == "__main__":
    unittest.main()
