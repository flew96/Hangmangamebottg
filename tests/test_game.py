import unittest

from game import MAX_WORD_LENGTH, WORDS, HangmanGame, normalize_word


class GameTests(unittest.TestCase):
    def test_wrong_letter_and_word_cost_one_attempt_each(self):
        game = HangmanGame("молоко")
        for guess in ("я", "река"):
            before = game.attempts
            self.assertEqual(game.guess(guess), "incorrect")
            self.assertEqual(game.attempts, before - 1)
            self.assertEqual(game.guess(guess.upper()), "already_guessed")
            self.assertEqual(game.attempts, before - 1)

    def test_letters_reveal_all_occurrences_and_win(self):
        game = HangmanGame("молоко")
        game.guess("о")
        self.assertEqual(game.get_display_word(), "_ О _ О _ О")
        for letter in "млк":
            self.assertEqual(game.guess(letter), "correct")
        self.assertTrue(game.is_victory())
        self.assertTrue(game.is_game_over())
        self.assertEqual(game.attempts, 9)
        with self.assertRaises(ValueError):
            game.guess("я")

    def test_whole_word_wins_and_loss_stops_further_guesses(self):
        game = HangmanGame("python")
        self.assertEqual(game.guess(" Python "), "correct")
        self.assertTrue(game.is_victory())
        game = HangmanGame("я", attempts=1)
        self.assertEqual(game.guess("а"), "incorrect")
        self.assertTrue(game.is_game_over())
        self.assertFalse(game.is_victory())
        with self.assertRaises(ValueError):
            game.guess("я")

    def test_validation_does_not_consume_attempts(self):
        game = HangmanGame("ёж")
        for invalid in ("", "123", "a b", "кот!", "🙂", "ß", "a" * (MAX_WORD_LENGTH + 1)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                game.guess(invalid)
        self.assertEqual(game.attempts, 5)
        self.assertEqual(game.guessed_letters, set())
        game.guess("е")
        self.assertEqual(game.get_display_word(), "_ _")
        game.guess("ё")
        self.assertEqual(game.get_display_word(), "Ё _")
        self.assertTrue(all(normalize_word(word) for word in WORDS))
