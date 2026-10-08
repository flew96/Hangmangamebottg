"""Read configuration at startup; imports never require a bot token."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ABOUT_TEXT = (
    "Виселица в Telegram — угадывайте слова по буквам или целиком.\n"
    "Можно играть самому или загадать слово другу через /setword.\n\n"
    "Автор: Баграт Геворкян\n"
    "Код: https://github.com/flew96/Hangmangamebottg\n"
    "Связаться с автором: /social"
)


def load_settings() -> tuple[str, Path]:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token or token == "your_bot_token_here":
        raise ValueError("Задайте BOT_TOKEN в окружении. Инструкция есть в README.md.")
    data_dir = Path(os.environ.get("DATA_DIR", "content")).expanduser()
    if not data_dir.is_absolute():
        data_dir = BASE_DIR / data_dir
    return token, data_dir
