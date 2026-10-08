"""Small, transactional SQLite store; no separate database service required."""

import json
import logging
import secrets
import sqlite3
import string
from pathlib import Path

from game import HangmanGame, normalize_word

logger = logging.getLogger(__name__)


class Store:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(data_dir / "hangman.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                code TEXT PRIMARY KEY,
                creator_id INTEGER NOT NULL,
                player_id INTEGER UNIQUE,
                secret_word TEXT NOT NULL,
                guessed_letters TEXT NOT NULL DEFAULT '[]',
                guessed_words TEXT NOT NULL DEFAULT '[]',
                attempts INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
                text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY);
        """)
        self._import_legacy(data_dir / "games.txt")

    def close(self):
        self.db.close()

    @staticmethod
    def _game(row) -> HangmanGame:
        return HangmanGame(
            row["secret_word"],
            set(json.loads(row["guessed_letters"])),
            row["attempts"],
            set(json.loads(row["guessed_words"])),
        )

    def active_game(self, user_id: int):
        return self.db.execute("SELECT * FROM games WHERE player_id = ?", (user_id,)).fetchone()

    def create_game(self, user_id: int, word: str, invitation: bool = False):
        game = HangmanGame(word)
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            if not self.db.execute("SELECT 1 FROM games WHERE code = ?", (code,)).fetchone():
                break
        with self.db:
            if invitation:
                self.db.execute(
                    "DELETE FROM games WHERE creator_id = ? AND player_id IS NULL",
                    (user_id,),
                )
            else:
                self.db.execute("DELETE FROM games WHERE player_id = ?", (user_id,))
            self.db.execute(
                "INSERT INTO games (code, creator_id, player_id, secret_word, attempts) "
                "VALUES (?, ?, ?, ?, ?)",
                (code, user_id, None if invitation else user_id, game.secret_word, game.attempts),
            )
        return code, game

    def play(self, user_id: int, guess: str, code: str | None = None):
        guess = normalize_word(guess)
        # ponytail: short synchronous transactions suit one bot process; use a worker
        # and a server database if measured traffic makes local disk latency matter.
        with self.db:
            row = (
                self.db.execute("SELECT * FROM games WHERE code = ?", (code.upper(),)).fetchone()
                if code
                else self.active_game(user_id)
            )
            if row is None:
                raise ValueError("Игра не найдена. /start — новая игра; /join КОД — игра друга.")
            if row["player_id"] is None:
                self._claim(row, user_id)
            elif row["player_id"] != user_id:
                raise ValueError("Эту игру уже играет другой человек.")
            game = self._game(row)
            result = game.guess(guess)
            if game.is_game_over():
                self.db.execute("DELETE FROM games WHERE code = ?", (row["code"],))
            else:
                self.db.execute(
                    "UPDATE games SET guessed_letters = ?, guessed_words = ?, attempts = ? "
                    "WHERE code = ?",
                    (
                        json.dumps(sorted(game.guessed_letters)),
                        json.dumps(sorted(game.guessed_words)),
                        game.attempts,
                        row["code"],
                    ),
                )
        return row["code"], game, result

    def _claim(self, row, user_id: int):
        if row["creator_id"] == user_id:
            raise ValueError("Это ваше слово. Отправьте код другу, чтобы он его угадал.")
        self.db.execute("DELETE FROM games WHERE player_id = ?", (user_id,))
        self.db.execute("UPDATE games SET player_id = ? WHERE code = ?", (user_id, row["code"]))

    def join(self, user_id: int, code: str):
        with self.db:
            row = self.db.execute("SELECT * FROM games WHERE code = ?", (code.upper(),)).fetchone()
            if row is None:
                raise ValueError("Код игры не найден. Проверьте код у друга.")
            if row["player_id"] is None:
                self._claim(row, user_id)
            elif row["player_id"] != user_id:
                raise ValueError("Эту игру уже играет другой человек.")
        return row["code"], self._game(row)

    def surrender(self, user_id: int, code: str | None = None) -> str:
        with self.db:
            row = self.active_game(user_id)
            if row is None or (code is not None and row["code"] != code):
                raise ValueError("Эта игра уже окончена. /start — новая игра.")
            self.db.execute("DELETE FROM games WHERE code = ?", (row["code"],))
        return row["secret_word"]

    def add_review(self, user_id: int, username: str, rating: int, text: str):
        if not 1 <= rating <= 5 or not text.strip() or len(text) > 4000:
            raise ValueError("Отзыв должен содержать от 1 до 4000 символов, оценка — от 1 до 5.")
        with self.db:
            self.db.execute(
                "INSERT INTO reviews (user_id, username, rating, text) VALUES (?, ?, ?, ?)",
                (user_id, username, rating, text.strip()),
            )

    def _import_legacy(self, path: Path):
        if self.db.execute("SELECT 1 FROM metadata WHERE key = 'legacy_games'").fetchone():
            return
        with self.db:
            if path.exists():
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        code, raw = line.split(":", 1)
                        data = json.loads(raw)
                        if not code.isascii() or not code.isalnum() or not 1 <= len(code) <= 8:
                            raise ValueError("Invalid legacy code")
                        game = HangmanGame(data["secret_word"])
                        user_id = data["user_id"]
                        letters = data["guessed_letters"]
                        attempts = data["attempts"]
                        if (
                            type(user_id) is not int
                            or type(attempts) is not int
                            or not 0 <= attempts <= game.attempts
                            or not isinstance(letters, list)
                            or any(
                                not isinstance(c, str) or len(normalize_word(c)) != 1
                                for c in letters
                            )
                        ):
                            raise ValueError("Invalid legacy game")
                        game.guessed_letters = {normalize_word(c) for c in letters}
                        game.attempts = attempts
                        if data.get("finished") or game.is_game_over():
                            continue
                    except (ValueError, TypeError, KeyError, AttributeError):
                        logger.warning("Skipping invalid legacy game at line %d", number)
                        continue
                    self.db.execute("DELETE FROM games WHERE player_id = ?", (user_id,))
                    self.db.execute(
                        "INSERT OR REPLACE INTO games "
                        "(code, creator_id, player_id, secret_word, guessed_letters, attempts) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            code.upper(),
                            user_id,
                            user_id,
                            game.secret_word,
                            json.dumps(sorted(game.guessed_letters)),
                            attempts,
                        ),
                    )
            self.db.execute("INSERT INTO metadata (key) VALUES ('legacy_games')")
