"""Hangman rules, independent of Telegram and storage."""

import re
from dataclasses import dataclass, field

WORDS = (
    "молоко",
    "космос",
    "библиотека",
    "программирование",
    "дипломат",
    "виноград",
    "фестиваль",
    "инструмент",
    "чемпионат",
    "метаморфоза",
    "экспедиция",
    "лабиринт",
    "кибернетика",
    "престиж",
    "аквариум",
    "биосфера",
    "галактика",
    "демократия",
    "живопись",
    "зоопарк",
    "изоляция",
    "квант",
    "литература",
    "мифология",
    "нейрон",
    "океан",
    "пирамида",
    "рубрика",
    "симфония",
    "телескоп",
    "философия",
    "хроника",
    "цитадель",
    "шахматы",
    "электричество",
    "юмор",
    "ягода",
)
MAX_WORD_LENGTH = 32


def normalize_word(word: str) -> str:
    word = word.strip()
    if not re.fullmatch(rf"[a-zA-Zа-яА-ЯёЁ]{{1,{MAX_WORD_LENGTH}}}", word):
        raise ValueError("Введите от 1 до 32 русских или английских букв без пробелов.")
    return word.upper()


@dataclass
class HangmanGame:
    secret_word: str
    guessed_letters: set[str] = field(default_factory=set)
    attempts: int | None = None
    guessed_words: set[str] = field(default_factory=set)

    def __post_init__(self):
        self.secret_word = normalize_word(self.secret_word)
        if self.attempts is None:
            self.attempts = len(self.secret_word) + 3

    def guess(self, value: str) -> str:
        value = normalize_word(value)
        if self.is_game_over():
            raise ValueError("Игра уже окончена. /start — новая игра.")
        guesses = self.guessed_letters if len(value) == 1 else self.guessed_words
        if value in guesses:
            return "already_guessed"
        guesses.add(value)
        correct = value in self.secret_word if len(value) == 1 else value == self.secret_word
        if not correct:
            self.attempts -= 1
        elif len(value) > 1:
            self.guessed_letters.update(self.secret_word)
        return "correct" if correct else "incorrect"

    def get_display_word(self) -> str:
        return " ".join(c if c in self.guessed_letters else "_" for c in self.secret_word)

    def is_victory(self) -> bool:
        return set(self.secret_word) <= self.guessed_letters

    def is_game_over(self) -> bool:
        return self.attempts <= 0 or self.is_victory()
