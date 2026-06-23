from aiogram import Bot
from aiogram.filters import BaseFilter
from aiogram.types import Message

from bot.utils import is_group_admin


class IsGroupAdmin(BaseFilter):
    """Allows the handler to run only if the sender is a group admin/creator or the bot owner."""

    async def __call__(self, message: Message, bot: Bot) -> bool:
        if message.chat.type == "private":
            return False
        if not message.from_user:
            return False
        return await is_group_admin(bot, message.chat.id, message.from_user.id)


class IsGroupChat(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.chat.type in ("group", "supergroup")
