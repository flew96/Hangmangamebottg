import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from storage import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.path = Path(self.temp.name)
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def reopen(self):
        self.store.close()
        self.store = Store(self.path)

    def test_progress_and_reviews_survive_restart(self):
        code, _ = self.store.create_game(1, "молоко")
        self.store.play(1, "о")
        self.store.play(1, "река")
        self.store.add_review(1, "author", 5, "Хорошая игра\nСпасибо!")
        self.reopen()
        restored = self.store.active_game(1)
        self.assertEqual(restored["code"], code)
        self.assertEqual(restored["attempts"], 8)
        _, game, result = self.store.play(1, "река")
        self.assertEqual(result, "already_guessed")
        self.assertEqual(game.get_display_word(), "_ О _ О _ О")
        review = self.store.db.execute("SELECT * FROM reviews").fetchone()
        self.assertEqual(review["text"], "Хорошая игра\nСпасибо!")

    def test_restart_replaces_active_game_and_old_button_is_safe(self):
        old, _ = self.store.create_game(1, "кот")
        new, _ = self.store.create_game(1, "река")
        with self.assertRaises(ValueError):
            self.store.surrender(1, old)
        self.assertEqual(self.store.active_game(1)["code"], new)
        self.assertEqual(self.store.surrender(1, new), "РЕКА")
        self.reopen()
        self.assertIsNone(self.store.active_game(1))

    def test_friend_claim_ownership_and_guesses(self):
        own, _ = self.store.create_game(2, "молоко")
        code, _ = self.store.create_game(1, "кот", invitation=True)
        for action in (lambda: self.store.join(1, code), lambda: self.store.play(1, "к", code)):
            with self.assertRaises(ValueError):
                action()
        with self.assertRaises(ValueError):
            self.store.play(2, "123", code)
        self.assertEqual(self.store.active_game(2)["code"], own)
        _, game, _ = self.store.play(2, "к", code.lower())
        self.assertEqual(game.get_display_word(), "К _ _")
        self.assertEqual(self.store.active_game(2)["code"], code)
        for action in (lambda: self.store.join(3, code), lambda: self.store.play(3, "кот", code)):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(self.store.join(2, code)[0], code)
        self.assertTrue(self.store.play(2, "кот")[1].is_victory())
        self.reopen()
        self.assertIsNone(self.store.active_game(2))

    def test_join_and_invitation_replacement_preserve_other_games(self):
        active, _ = self.store.create_game(1, "молоко")
        old, _ = self.store.create_game(1, "кот", invitation=True)
        new, _ = self.store.create_game(1, "река", invitation=True)
        with self.assertRaises(ValueError):
            self.store.join(2, old)
        self.assertEqual(self.store.active_game(1)["code"], active)
        self.assertEqual(self.store.join(2, new)[0], new)
        self.store.create_game(1, "океан", invitation=True)
        self.assertEqual(self.store.active_game(2)["code"], new)
        with self.assertRaises(ValueError):
            self.store.play(3, "м", active)

    def test_loss_is_persisted_before_restart(self):
        code, _ = self.store.create_game(1, "я")
        for guess in "абвг":
            _, game, _ = self.store.play(1, guess)
        self.assertEqual(game.attempts, 0)
        self.reopen()
        with self.assertRaises(ValueError):
            self.store.play(1, "я", code)

    def test_invalid_review_is_not_saved(self):
        for rating, text in ((0, "текст"), (6, "текст"), (5, " "), (5, "a" * 4001)):
            with self.assertRaises(ValueError):
                self.store.add_review(1, "user", rating, text)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM reviews").fetchone()[0], 0)

    def test_failed_move_rolls_back_claim_and_preserves_previous_game(self):
        own, _ = self.store.create_game(2, "молоко")
        invite, _ = self.store.create_game(1, "кот", invitation=True)
        self.store.db.executescript("""
            CREATE TRIGGER reject_move BEFORE UPDATE OF attempts ON games
            BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END;
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.play(2, "к", invite)
        self.assertEqual(self.store.active_game(2)["code"], own)
        invitation = self.store.db.execute(
            "SELECT * FROM games WHERE code = ?", (invite,)
        ).fetchone()
        self.assertIsNone(invitation["player_id"])
        self.assertEqual(invitation["guessed_letters"], "[]")
        self.store.db.execute("DROP TRIGGER reject_move")
        self.assertEqual(self.store.play(2, "к", invite)[1].get_display_word(), "К _ _")

    def test_legacy_import_skips_bad_rows_and_never_resurrects_games(self):
        self.store.close()
        (self.path / "hangman.sqlite3").unlink()
        data = dict(user_id=1, secret_word="кот", guessed_letters=["к"], attempts=5, finished=False)
        lines = [
            "broken",
            "ABCDE:" + json.dumps(data),
            "FGHIJ:" + json.dumps(dict(data, user_id=2, attempts=0)),
            "KLMNO:" + json.dumps(dict(data, guessed_letters=None)),
            "PQRST:" + json.dumps(dict(data, user_id=3, secret_word="ß")),
        ]
        legacy = self.path / "games.txt"
        original = "\n".join(lines)
        legacy.write_text(original, encoding="utf-8")
        with self.assertLogs("storage", level="WARNING"):
            self.store = Store(self.path)
        self.assertEqual(self.store.active_game(1)["attempts"], 5)
        self.assertIsNone(self.store.active_game(2))
        self.assertEqual(self.store.play(1, "к")[2], "already_guessed")
        self.store.surrender(1)
        self.reopen()
        self.assertIsNone(self.store.active_game(1))
        self.assertEqual(legacy.read_text(encoding="utf-8"), original)
