import os
import sys
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/db.sqlite3")

# Validate critical environment variables on startup
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set in .env file")
    sys.exit(1)
