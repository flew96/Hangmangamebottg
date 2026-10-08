"""Telegram interface for Hangman. Run with: python maincode.py."""

import asyncio
import logging
import random
import sqlite3
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.token import TokenValidationError

from config import ABOUT_TEXT, load_settings
from game import WORDS, HangmanGame
from storage import Store

logger = logging.getLogger(__name__)
HELP_TEXT = (
    "Угадывайте русские или английские слова по буквам или целиком.\n"
    "Неверная буква или слово отнимает одну попытку. Повторный ответ — ни одной.\n\n"
    "/start или /restart — новая игра\n"
    "/setword слово — загадать слово другу\n"
    "/join КОД — присоединиться к игре друга\n"
    "/surrender — сдаться\n"
    "/review — оценка и отзыв\n"
    "/cancel — отменить ввод отзыва\n"
    "/about — о проекте\n"
    "/social — контакты автора\n"
    "/support — поддержать проект\n"
    "/help — справка\n\n"
    "После /start или /join просто отправляйте букву или слово.\n"
    "Также работает прежний формат: КОД Б или КОД СЛОВО.\n"
    "В словах от 1 до 32 букв; Е и Ё считаются разными буквами."
)
COMMANDS = [
    BotCommand(command=command, description=description)
    for command, description in (
        ("start", "Новая игра"),
        ("setword", "Загадать слово другу"),
        ("join", "Присоединиться по коду"),
        ("surrender", "Сдаться"),
        ("review", "Оставить отзыв"),
        ("cancel", "Отменить ввод отзыва"),
        ("help", "Правила и команды"),
        ("about", "О проекте"),
        ("social", "Контакты автора"),
        ("support", "Поддержать проект"),
    )
]


class Review(StatesGroup):
    rating = State()
    text = State()


def game_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сдаться", callback_data=f"surrender:{code}"),
                InlineKeyboardButton(text="Правила", callback_data="help"),
            ]
        ]
    )


def game_status(game: HangmanGame) -> str:
    letters = " ".join(sorted(game.guessed_letters)) or "—"
    return (
        f"{game.get_display_word()}\nОсталось попыток: {game.attempts}\nНазванные буквы: {letters}"
    )


def link_keyboard(links: tuple[tuple[str, str], ...]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, url=url)] for text, url in links]
    )


def create_dispatcher(store: Store) -> Dispatcher:
    dp = Dispatcher(store=store, events_isolation=SimpleEventIsolation())
    router = Router()
    router.message.filter(F.chat.type == "private")
    router.callback_query.filter(F.message.chat.type == "private")

    @router.message(Command("start", "restart"))
    async def start_game(message: Message, state: FSMContext):
        await state.clear()
        code, game = store.create_game(message.from_user.id, random.choice(WORDS))
        await message.answer(
            f"Игра началась! Отправьте букву или слово. Код: {code}\n\n{game_status(game)}",
            reply_markup=game_keyboard(code),
        )

    @router.message(Command("help"))
    async def help_command(message: Message):
        await message.answer(HELP_TEXT)

    @router.message(Command("about"))
    async def about_command(message: Message):
        await message.answer(ABOUT_TEXT)

    @router.message(Command("social"))
    async def social_command(message: Message):
        await message.answer(
            "Контакты автора:",
            reply_markup=link_keyboard(
                (
                    ("Telegram", "https://t.me/swizzy_ed"),
                    ("Steam", "https://steamcommunity.com/profiles/76561199070099207/"),
                    ("GitHub", "https://github.com/flew96"),
                )
            ),
        )

    @router.message(Command("support"))
    async def support_command(message: Message):
        await message.answer(
            "Спасибо за поддержку проекта!",
            reply_markup=link_keyboard(
                (("Поддержать", "https://www.donationalerts.com/r/underkassq"),)
            ),
        )

    @router.message(Command("setword"))
    async def set_word(message: Message, command: CommandObject, state: FSMContext):
        if not command.args:
            await message.answer("Используйте /setword слово. Например: /setword космос")
            return
        try:
            code, _ = store.create_game(message.from_user.id, command.args, invitation=True)
        except ValueError as error:
            await message.answer(str(error))
            return
        await state.clear()
        await message.answer(
            f"Слово загадано! Отправьте другу команду:\n/join {code}\n\n"
            "Или попросите его отправить код и букву: " + code + " Б\n"
            "Новое /setword заменит ваше приглашение, пока друг не начал играть."
        )

    @router.message(Command("join"))
    async def join_game(message: Message, command: CommandObject, state: FSMContext):
        if not command.args or len(command.args.split()) != 1:
            await message.answer("Используйте /join КОД, который прислал друг.")
            return
        try:
            code, game = store.join(message.from_user.id, command.args.strip())
        except ValueError as error:
            await message.answer(str(error))
            return
        await state.clear()
        await message.answer(
            f"Вы в игре {code}. Отправьте букву или слово.\n\n{game_status(game)}",
            reply_markup=game_keyboard(code),
        )

    @router.message(Command("surrender"))
    async def surrender_command(message: Message):
        try:
            word = store.surrender(message.from_user.id)
        except ValueError as error:
            await message.answer(str(error))
            return
        await message.answer(f"Вы сдались. Слово: {word}.\n/start — попробовать снова.")

    @router.callback_query(F.data.startswith("surrender:"))
    async def surrender_callback(callback: CallbackQuery):
        try:
            word = store.surrender(callback.from_user.id, callback.data.split(":", 1)[1])
        except ValueError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await callback.answer()
        await callback.message.answer(f"Вы сдались. Слово: {word}.\n/start — попробовать снова.")

    @router.callback_query(F.data == "help")
    async def help_callback(callback: CallbackQuery):
        await callback.answer()
        await callback.message.answer(HELP_TEXT)

    @router.message(Command("cancel"))
    async def cancel_review(message: Message, state: FSMContext):
        await state.clear()
        await message.answer(
            "Ввод отзыва отменён. Можете продолжать игру или начать новую: /start."
        )

    @router.message(Command("review"))
    async def review_command(message: Message, state: FSMContext):
        await state.clear()
        await state.set_state(Review.rating)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=f"{i} ⭐", callback_data=f"rate_{i}")
                    for i in range(1, 6)
                ]
            ]
        )
        await message.answer("Оцените бота. /cancel — отменить.", reply_markup=keyboard)

    @router.callback_query(Review.rating, F.data.regexp(r"^rate_[1-5]$"))
    async def rating_callback(callback: CallbackQuery, state: FSMContext):
        await state.update_data(rating=int(callback.data[-1]))
        await state.set_state(Review.text)
        await callback.answer()
        await callback.message.answer("Спасибо! Напишите отзыв текстом. /cancel — отменить.")

    # Commands are registered before FSM text handlers so they never become a review.
    @router.message(F.text.startswith("/"))
    async def unknown_command(message: Message):
        await message.answer("Неизвестная команда. /help — список команд.")

    @router.message(Review.text, F.text)
    async def review_text(message: Message, state: FSMContext):
        data = await state.get_data()
        try:
            store.add_review(
                message.from_user.id,
                message.from_user.username or message.from_user.first_name,
                data["rating"],
                message.text,
            )
        except ValueError as error:
            await message.answer(str(error))
            return
        await state.clear()
        await message.answer("Отзыв сохранён. Спасибо! Можете продолжать игру.")

    @router.message(Review.rating)
    async def waiting_for_rating(message: Message):
        await message.answer("Выберите оценку кнопкой выше или отправьте /cancel.")

    @router.message(Review.text)
    async def waiting_for_text(message: Message):
        await message.answer("Напишите отзыв текстом или отправьте /cancel.")

    @router.message(F.text)
    async def guess(message: Message):
        parts = message.text.strip().split()
        if not 1 <= len(parts) <= 2:
            await message.answer("Отправьте букву, слово или КОД Б. /help — правила.")
            return
        code, value = (None, parts[0]) if len(parts) == 1 else parts
        try:
            code, game, result = store.play(message.from_user.id, value, code)
        except ValueError as error:
            await message.answer(str(error))
            return
        if game.is_victory():
            await message.answer(
                f"Победа! Вы угадали слово: {game.secret_word}.\n/start — новая игра."
            )
        elif game.is_game_over():
            await message.answer(
                f"Попытки закончились. Слово: {game.secret_word}.\n/start — новая игра."
            )
        else:
            prefix = {
                "correct": "Верно!",
                "incorrect": "Не угадали.",
                "already_guessed": "Такой ответ уже был — попытку не отнимаю.",
            }[result]
            await message.answer(
                f"{prefix}\n\n{game_status(game)}", reply_markup=game_keyboard(code)
            )

    @router.message()
    async def non_text(message: Message):
        await message.answer("Для игры отправьте букву или слово текстом. /help — правила.")

    fallback = Router()
    dp.include_routers(router, fallback)

    @fallback.message()
    async def group_message(message: Message):
        await message.answer(
            "Игра доступна в личных сообщениях с ботом. Откройте чат и отправьте /start."
        )

    @fallback.callback_query()
    async def stale_callback(callback: CallbackQuery):
        await callback.answer("Эта кнопка устарела. /help — команды; /review — новый отзыв.")

    @dp.errors()
    async def handle_error(event: ErrorEvent):
        # Do not log update contents: /setword, reviews and usernames are private.
        logger.error("Update failed (%s)", type(event.exception).__name__)
        message = event.update.message
        callback = event.update.callback_query
        try:
            if callback:
                await callback.answer(
                    "Не удалось обработать запрос. Попробуйте ещё раз.", show_alert=True
                )
            elif message:
                await message.answer("Не удалось обработать запрос. Попробуйте ещё раз.")
        except Exception as error:
            logger.warning("Could not notify user (%s)", type(error).__name__)
        return True

    return dp


async def main():
    token, data_dir = load_settings()
    try:
        bot = Bot(token)
    except TokenValidationError:
        raise ValueError("Некорректный BOT_TOKEN. Получите токен у @BotFather.") from None
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=[
                logging.StreamHandler(),
                RotatingFileHandler(
                    data_dir / "log.txt",
                    maxBytes=1_000_000,
                    backupCount=3,
                    encoding="utf-8",
                ),
            ],
        )
        store = Store(data_dir)
        try:
            dp = create_dispatcher(store)
            await bot.set_my_commands(COMMANDS)
            # Preserve pending updates; stop any previous bot instance before starting.
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot, close_bot_session=False)
        finally:
            store.close()
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, OSError, sqlite3.Error) as error:
        raise SystemExit(str(error)) from None
