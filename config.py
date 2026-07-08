import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/db.sqlite3")
