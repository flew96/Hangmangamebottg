import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User

from maincode import Review, create_dispatcher
from storage import Store


class FakeSession(BaseSession):
    """Capture Telegram methods locally; never connect to Telegram."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=len(self.calls),
                date=datetime.now(timezone.utc),
                chat=Chat(id=int(method.chat_id), type="private"),
                text=method.text,
            )
        if isinstance(method, AnswerCallbackQuery):
            return True
        raise AssertionError(f"Unexpected Telegram method: {type(method).__name__}")

    async def stream_content(self, url, **kwargs):
        raise AssertionError("Unexpected download")
        yield b""


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.store = Store(Path(self.temp.name))
        self.session = FakeSession()
        self.bot = Bot("123456:TEST_TOKEN_FOR_OFFLINE_TESTS", session=self.session)
        self.dp = create_dispatcher(self.store)
        self.sequence = 0

    async def asyncTearDown(self):
        await self.dp.storage.close()
        await self.dp.fsm.events_isolation.close()
        await self.bot.session.close()
        self.store.close()
        self.temp.cleanup()

    def message(self, user_id=1, text=None, private=True):
        self.sequence += 1
        return Message(
            message_id=self.sequence,
            date=datetime.now(timezone.utc),
            chat=Chat(id=user_id if private else -100, type="private" if private else "group"),
            from_user=User(id=user_id, is_bot=False, first_name="Test"),
            text=text,
            photo=None
            if text is not None
            else [
                PhotoSize(
                    file_id="photo",
                    file_unique_id="photo",
                    width=1,
                    height=1,
                )
            ],
        )

    async def send(self, text=None, user_id=1, private=True):
        msg = self.message(user_id, text, private)
        await self.dp.feed_update(self.bot, Update(update_id=self.sequence, message=msg))

    async def click(self, data, user_id=1):
        msg = self.message(user_id, "button message")
        callback = CallbackQuery(
            id=str(self.sequence),
            from_user=msg.from_user,
            chat_instance="test",
            message=msg,
            data=data,
        )
        await self.dp.feed_update(
            self.bot,
            Update(update_id=self.sequence, callback_query=callback),
        )

    def last_text(self):
        return next(
            call.text for call in reversed(self.session.calls) if isinstance(call, SendMessage)
        )

    async def test_new_game_simple_guess_and_stale_surrender(self):
        with patch("maincode.random.choice", return_value="кот"):
            await self.send("/start")
            old = self.store.active_game(1)["code"]
            await self.send("к")
            self.assertIn("К _ _", self.last_text())
            await self.send("/restart")
        new = self.store.active_game(1)["code"]
        await self.click("surrender:" + old)
        self.assertEqual(self.store.active_game(1)["code"], new)
        self.assertTrue(self.session.calls[-1].show_alert)
        await self.click("surrender:" + new)
        self.assertIsNone(self.store.active_game(1))
        self.assertIn("КОТ", self.last_text())

    async def test_friend_can_join_and_win_but_third_player_cannot(self):
        await self.send("/setword ёж")
        code = self.store.db.execute("SELECT code FROM games").fetchone()[0]
        await self.send("/join " + code, user_id=2)
        self.assertNotIn("ЁЖ", self.last_text())
        await self.send(code + " ёж", user_id=3)
        self.assertIn("другой человек", self.last_text())
        await self.send("ёж", user_id=2)
        self.assertIn("Победа!", self.last_text())
        self.assertIsNone(self.store.active_game(2))

    async def test_reviews_do_not_swallow_commands_or_break_the_game(self):
        code, _ = self.store.create_game(1, "кот")
        await self.send("/review")
        await self.click("rate_5")
        await self.send("/help")
        self.assertIn("/join", self.last_text())
        await self.send()
        self.assertIn("текстом", self.last_text())
        await self.send("Спасибо!")
        self.assertIn("Отзыв сохранён", self.last_text())
        self.assertEqual(
            self.store.db.execute("SELECT text FROM reviews").fetchone()[0], "Спасибо!"
        )
        await self.send("к")
        self.assertIn("К _ _", self.last_text())
        await self.send("/review")
        await self.send("/cancel")
        self.assertEqual(self.store.active_game(1)["code"], code)
        await self.click("rate_1")
        self.assertIsInstance(self.session.calls[-1], AnswerCallbackQuery)
        self.assertIn("устарела", self.session.calls[-1].text)

    async def test_storage_failure_keeps_review_for_retry(self):
        await self.send("/review")
        await self.click("rate_4")
        with patch.object(self.store, "add_review", side_effect=OSError("disk unavailable")):
            with self.assertLogs("maincode", level="ERROR"):
                await self.send("текст")
        self.assertIn("Попробуйте ещё раз", self.last_text())
        state = self.dp.fsm.get_context(self.bot, chat_id=1, user_id=1)
        self.assertEqual(await state.get_state(), Review.text.state)
        await self.send("текст")
        self.assertIsNone(await state.get_state())

    async def test_invalid_input_non_text_and_group_do_not_change_game(self):
        self.store.create_game(1, "кот")
        for text in (None, "", "123", "A B C", "/unknown"):
            await self.send(text)
        await self.send("/setword секрет", private=False)
        self.assertIn("личных сообщениях", self.last_text())
        self.assertEqual(self.store.active_game(1)["attempts"], 6)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM games").fetchone()[0], 1)

    async def test_callbacks_acknowledged_and_concurrent_guesses_preserved(self):
        self.store.create_game(1, "кот")
        await self.click("help")
        self.assertIsInstance(self.session.calls[-2], AnswerCallbackQuery)
        messages = [self.message(text="к"), self.message(text="о")]
        await asyncio.gather(
            *[
                self.dp.feed_update(self.bot, Update(update_id=msg.message_id, message=msg))
                for msg in messages
            ]
        )
        self.assertEqual(self.store.play(1, "к")[1].get_display_word(), "К О _")
