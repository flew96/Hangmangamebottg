# Telegram Hangman Bot

[Русский](README.md)

A Telegram Hangman game: guess letters or whole words, play solo, or challenge a friend with a custom word. The bot interface is in Russian.

## Quick start

Requires **Python 3.10–3.14**; Python 3.12 is recommended. Uses aiogram 3 and Python's built-in SQLite.

1. Create a bot with [@BotFather](https://t.me/BotFather) and obtain a token.
2. Clone the project and install dependencies:

   ```sh
   git clone https://github.com/flew96/Hangmangamebottg.git
   cd Hangmangamebottg
   python3.12 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

3. Configure and start the bot:

   ```sh
   export BOT_TOKEN='your_token_from_BotFather'
   python maincode.py
   ```

On Windows, activate with `.venv\Scripts\Activate.ps1` and set the token with `$env:BOT_TOKEN = 'your_token_from_BotFather'`.

The token is read from the environment. `.env.example` documents the settings. To use a `.env` file on macOS/Linux:

```sh
cp .env.example .env
# Edit .env to set your actual token, then:
set -a
source .env
set +a
python maincode.py
```

`.env` is not loaded automatically. Secrets, the virtual environment, and runtime data are excluded from Git.

## Playing

Use the bot in **private chats**.

- Send `/start`, then a letter such as `о` or a whole word such as `молоко`.
- You start with the word's length + 3 attempts. A wrong letter or word costs one attempt; repeating a guess costs none.
- Correct letters reveal every occurrence. The bot shows the masked word, remaining attempts, and tried letters.
- Guesses are case-insensitive. Words accept 1–32 Russian or English letters without spaces. `Е` and `Ё` are distinct.
- Winning, losing, or surrendering ends the game. `/start` replaces your current game.

To challenge a friend, send `/setword космос` and share the returned `/join CODE` command. The friend sends it **to the same bot in their own private chat**, then guesses normally. Joining replaces their current game.

The first player to join claims the invitation; other players cannot interfere. The word's author cannot join their own invitation. A new `/setword` replaces the author's unclaimed invitation, preserving games already claimed by friends. Share a code privately when inviting a specific person.

The previous `CODE LETTER` and `CODE WORD` formats also work; a first guess can claim an unclaimed invitation.

## Commands

| Command | Action |
| --- | --- |
| `/start`, `/restart` | Start a new game |
| `/setword word` | Create a challenge for a friend |
| `/join CODE` | Join a friend's game |
| `/surrender` | Give up and reveal the word |
| `/review` | Choose a rating from 1 to 5 and leave a review |
| `/cancel` | Cancel review input without ending the game |
| `/help` | Rules and commands |
| `/about` | Project information |
| `/social` | Author's contacts |
| `/support` | Support the project |

Commands remain available during review input. Successful `/start`, `/join`, and `/setword` commands cancel that input. Surrender buttons from old games cannot end a new game.

## Data and upgrading

- `BOT_TOKEN`: required bot token.
- `DATA_DIR`: defaults to `content` beside the source files. Relative paths are resolved from the project directory, independently of the process's working directory.
- `content/hangman.sqlite3`: active games, invitations, and reviews. Each turn and game completion is committed in a transaction.
- `content/log.txt`: rotating technical log, up to three backups of 1 MB each. The new log excludes message text, secret words, reviews, and usernames.
- Reviews contain user ID, name, rating, text, and a UTC timestamp. Protect access to the data directory.

Before upgrading, stop the old bot and back up `content`. Place the old `games.txt` in the configured data directory **before the first new-version launch**. Unfinished games are imported once. Invalid rows are skipped with a warning; the last unfinished game wins if a user had several games. The original file is unchanged. The legacy format did not distinguish solo games from invitations: imported games stay with their original players, and friend invitations must be recreated.

Old `reviews.txt` stays as an archive; new reviews go into SQLite. Finished games are not reimported. Pending review input is held in memory; after a restart, users must send `/review` again.

Run one bot process per token. Startup preserves pending Telegram updates. Stop the bot before copying the data directory for a backup.

## Development

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
```

Tests cover game rules, restart persistence, legacy imports, player ownership, stale buttons, reviews, and Telegram handlers. They require no real token or Telegram connection. GitHub Actions runs checks on Python 3.10, 3.12, and 3.14.

- `maincode.py`: Telegram commands, buttons, and polling startup.
- `game.py`: game rules and word list.
- `storage.py`: SQLite transactions and legacy game import.
- `config.py`: environment settings and project information.

Library documentation: [aiogram 2 to 3 migration](https://docs.aiogram.dev/en/latest/migration_2_to_3.html).

## Author and license

[Bagrat Gevorkyan](https://github.com/flew96). [MIT license](LICENSE), © 2024.
