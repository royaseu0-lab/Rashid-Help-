import re
import time

from aiogram import Bot
from aiogram.types import Message, User

from bot.config import OWNER_ID

_DURATION_UNITS = [
    (re.compile(r"^(دقيق[ةه]?|دقائق|دقايق|دق|د)$"), 60),
    (re.compile(r"^(ساع[ةه]?|ساعات|سا|س)$"), 3600),
    (re.compile(r"^(يوم|أيام|ايام|ي)$"), 86400),
]


def parse_duration(text: str) -> int | None:
    """Parse strings like '1 دقيقة', '10 دقائق', '3 ساعات', '2 يوم' into seconds."""
    text = text.strip()
    match = re.match(r"^(\d+)\s*(\S+)$", text)
    if not match:
        return None
    amount, unit = match.groups()
    amount = int(amount)
    for pattern, seconds in _DURATION_UNITS:
        if pattern.match(unit):
            return amount * seconds
    return None


async def resolve_target_user(message: Message, bot: Bot, args_text: str = "") -> User | None:
    """Resolve the target user from a reply, an @mention, or a numeric ID in args_text."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user

    args_text = args_text.strip()
    if not args_text:
        return None

    if args_text.startswith("@"):
        username = args_text[1:].split()[0]
        try:
            chat = await bot.get_chat(f"@{username}")
            return User(id=chat.id, is_bot=False, first_name=chat.first_name or username)
        except Exception:
            return None

    first_token = args_text.split()[0]
    if first_token.isdigit():
        try:
            member = await bot.get_chat_member(message.chat.id, int(first_token))
            return member.user
        except Exception:
            return User(id=int(first_token), is_bot=False, first_name=str(first_token))

    return None


async def split_target_and_rest(
    message: Message, bot: Bot, args_text: str
) -> tuple[User | None, str]:
    """Resolve target user and return (user, remaining_text) for duration/reason parsing."""
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user, args_text.strip()

    args_text = args_text.strip()
    if not args_text:
        return None, ""

    tokens = args_text.split(maxsplit=1)
    first, rest = tokens[0], (tokens[1] if len(tokens) > 1 else "")

    if first.startswith("@"):
        try:
            chat = await bot.get_chat(first)
            return User(id=chat.id, is_bot=False, first_name=chat.first_name or first[1:]), rest
        except Exception:
            return None, rest

    if first.isdigit():
        uid = int(first)
        try:
            member = await bot.get_chat_member(message.chat.id, uid)
            return member.user, rest
        except Exception:
            return User(id=uid, is_bot=False, first_name=first), rest

    return None, args_text


async def is_group_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    return member.status in ("administrator", "creator")


def strip_command(text: str) -> str:
    """Remove the leading command token (whether Arabic word or /slash command)."""
    parts = text.strip().split(maxsplit=1)
    return parts[1] if len(parts) > 1 else ""


def format_remaining(until_ts: int) -> str:
    remaining = until_ts - int(time.time())
    if remaining <= 0:
        return "منتهي"
    days, remainder = divmod(remaining, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days} يوم")
    if hours:
        parts.append(f"{hours} ساعة")
    if minutes:
        parts.append(f"{minutes} دقيقة")
    return " ".join(parts) if parts else "أقل من دقيقة"


def mention(user: User) -> str:
    name = user.first_name or str(user.id)
    return f'<a href="tg://user?id={user.id}">{name}</a>'
