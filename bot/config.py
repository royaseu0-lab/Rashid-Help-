import os
import re

from dotenv import load_dotenv

load_dotenv()


def _parse_token(raw: str) -> str:
    """Strip whitespace and extract only the token value if key:value format slipped in."""
    raw = raw.strip()
    # Handle accidental "Key: BOT_TOKEN\nValue: <token>" paste
    if "\n" in raw:
        for part in raw.split("\n"):
            part = part.strip()
            if re.match(r"^\d+:[A-Za-z0-9_-]{30,}$", part):
                return part
    return raw


def _parse_owner_id(raw: str) -> int:
    """Extract numeric user ID from the value, tolerating extra text."""
    digits = re.search(r"\b(5\d{8,10}|\d{6,12})\b", raw)
    if digits:
        return int(digits.group(0))
    only_digits = re.sub(r"\D", "", raw)
    return int(only_digits) if only_digits else 0


BOT_TOKEN = _parse_token(os.getenv("BOT_TOKEN", ""))
OWNER_ID = _parse_owner_id(os.getenv("OWNER_ID", "0"))
DEVELOPER_CONTACT = os.getenv("DEVELOPER_CONTACT", "@Rashid_1Help")
DATABASE_PATH = os.getenv("DATABASE_PATH", "rashid_help.db")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Add it in Render → Environment → BOT_TOKEN."
    )

if not OWNER_ID:
    raise RuntimeError(
        "OWNER_ID is not set. Add your Telegram numeric ID in Render → Environment → OWNER_ID."
    )

DEFAULT_FLOOD_LIMIT = 5
DEFAULT_FLOOD_SECONDS = 8
MAX_WARNS_BEFORE_MUTE = 3
