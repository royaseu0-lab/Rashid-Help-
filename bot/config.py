import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DEVELOPER_CONTACT = os.getenv("DEVELOPER_CONTACT", "@Rashid_1Help")
DATABASE_PATH = os.getenv("DATABASE_PATH", "rashid_help.db")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Copy .env.example to .env and fill in your "
        "bot token from @BotFather."
    )

if not OWNER_ID:
    raise RuntimeError(
        "OWNER_ID is not set. Put your numeric Telegram user ID in .env."
    )

DEFAULT_FLOOD_LIMIT = 5
DEFAULT_FLOOD_SECONDS = 8
MAX_WARNS_BEFORE_MUTE = 3
