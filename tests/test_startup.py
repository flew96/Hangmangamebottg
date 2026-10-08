import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from maincode import COMMANDS, main


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_polling_preserves_updates_and_closes_resources(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            bot = Mock()
            bot.session.close = AsyncMock()
            bot.set_my_commands = AsyncMock()
            bot.delete_webhook = AsyncMock()
            dp = Mock(start_polling=AsyncMock())
            store = Mock()
            with (
                patch("maincode.load_settings", return_value=("test", Path(temp))),
                patch("maincode.Bot", return_value=bot),
                patch("maincode.Store", return_value=store),
                patch("maincode.create_dispatcher", return_value=dp),
                patch("maincode.logging.basicConfig"),
                patch("maincode.RotatingFileHandler"),
            ):
                await main()
            bot.set_my_commands.assert_awaited_once_with(COMMANDS)
            bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)
            dp.start_polling.assert_awaited_once_with(bot, close_bot_session=False)
            store.close.assert_called_once()
            bot.session.close.assert_awaited_once()

    async def test_setup_failure_still_closes_database_and_bot(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            bot = Mock()
            bot.session.close = AsyncMock()
            bot.set_my_commands = AsyncMock(side_effect=OSError("offline"))
            store = Mock()
            with (
                patch("maincode.load_settings", return_value=("test", Path(temp))),
                patch("maincode.Bot", return_value=bot),
                patch("maincode.Store", return_value=store),
                patch("maincode.create_dispatcher"),
                patch("maincode.logging.basicConfig"),
                patch("maincode.RotatingFileHandler"),
                self.assertRaises(OSError),
            ):
                await main()
            store.close.assert_called_once()
            bot.session.close.assert_awaited_once()
