# Luci Bot

Telegram bot with keyword based auto replies, a user database and an admin broadcast.
Built with Python, aiogram 3 and SQLite.

## Features

- Greets users and stores them in the database automatically
- Replies to messages that contain configured keywords
- Admins manage keywords right from the chat, no code changes needed
- Broadcast a message to every user of the bot
- User statistics and CSV export
- Admin access through an invite link, no hardcoded user IDs

## Commands

For everyone:

| Command | Description |
|---|---|
| `/start` | Show the welcome message |
| `/help` | Show all available commands |

For admins:

| Command | Description |
|---|---|
| `/broadcast <text>` | Send a message to all users |
| `/users` | Show user statistics |
| `/export` | Download the user list as a CSV file |
| `/addkeyword <keyword> <reply>` | Add or update an automatic reply |
| `/removekeyword <keyword>` | Remove a keyword |
| `/listkeywords` | Show all keywords with their replies |

Keywords are case insensitive and match whole words only, so the keyword
`vip` will not trigger on the word `viper`. If a message contains several
keywords, the first one in alphabetical order wins.

## Admin access

Open this link (with your real values) and press Start:

```
https://t.me/<bot_username>?start=<ADMIN_SECRET>
```

`ADMIN_SECRET` is the value from your `.env` file. Anyone who opens the bot
through this link becomes an admin, so share it carefully.

## Setup

Requires Python 3.10 or newer.

```bash
./setup.sh                  # creates .venv and installs dependencies
cp .env.example .env        # then put your real values into .env
source .venv/bin/activate
alembic upgrade head        # creates the SQLite database in data/
python main.py
```

## Deployment (Linux with systemd)

```bash
./setup.sh
cp .env.example .env        # fill in BOT_TOKEN and ADMIN_SECRET
sudo ./deploy.sh
```

`deploy.sh` creates a systemd service named after the project folder,
enables it on boot and starts it. Useful commands:

```bash
systemctl status luci-simple-bot
journalctl -u luci-simple-bot -f
```

## Updating the bot

Push your changes to the repository, then on the server:

```bash
sudo ./deploy.sh
```

When the service already exists, the script pulls the latest code, updates
dependencies, applies database migrations and restarts the bot.

## Project layout

- `main.py` - entry point, bot and dispatcher setup
- `handlers/` - command and message handlers
- `models.py` - database tables
- `crud.py` - database queries
- `middlewares.py` - saves every user who talks to the bot
- `alembic/` - database migrations
- `data/` - SQLite database, created on first run
- `logs/` - log files
