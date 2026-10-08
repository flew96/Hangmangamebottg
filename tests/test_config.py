import os
import unittest
from pathlib import Path
from unittest.mock import patch

from config import BASE_DIR, load_settings


class ConfigTests(unittest.TestCase):
    def test_missing_or_placeholder_token_has_actionable_error(self):
        for token in ("", " ", "your_bot_token_here"):
            with patch.dict(os.environ, {"BOT_TOKEN": token}, clear=True):
                with self.assertRaisesRegex(ValueError, "BOT_TOKEN"):
                    load_settings()

    def test_relative_data_directory_is_independent_of_working_directory(self):
        with patch.dict(os.environ, {"BOT_TOKEN": "test", "DATA_DIR": "data"}, clear=True):
            self.assertEqual(load_settings(), ("test", BASE_DIR / "data"))
        with patch.dict(os.environ, {"BOT_TOKEN": "test", "DATA_DIR": str(BASE_DIR)}, clear=True):
            self.assertEqual(load_settings()[1], Path(BASE_DIR))
