from aiogram import F, Router
from aiogram.types import Message

from bot import db
from bot.filters import IsGroupAdmin, IsGroupChat
from bot.utils import mention, strip_command

router = Router()
router.message.filter(IsGroupChat())


@router.message(F.text.regexp(r"^(تفعيل الترحيب)$"), IsGroupAdmin())
async def enable_welcome(message: Message):
    await db.set_group_field(message.chat.id, "welcome_enabled", 1)
    await message.reply("👋 تم تفعيل الترحيب بالأعضاء الجدد.")


@router.message(F.text.regexp(r"^(ايقاف الترحيب|إيقاف الترحيب)$"), IsGroupAdmin())
async def disable_welcome(message: Message):
    await db.set_group_field(message.chat.id, "welcome_enabled", 0)
    await message.reply("👋 تم إيقاف الترحيب بالأعضاء الجدد.")


@router.message(F.text.regexp(r"^(تعيين الترحيب)(\s+)"), IsGroupAdmin())
async def set_welcome_text(message: Message):
    text = strip_command(message.text)
    await db.set_group_field(message.chat.id, "welcome_text", text)
    await message.reply("✅ تم حفظ رسالة الترحيب الجديدة.")


@router.message(F.new_chat_members)
async def greet_new_members(message: Message):
    group = await db.get_group(message.chat.id)
    if not group.get("welcome_enabled"):
        return
    welcome_text = group.get("welcome_text") or "أهلاً بك {user} في {chat}! 🌹"
    for member in message.new_chat_members:
        text = welcome_text.replace("{user}", mention(member)).replace(
            "{chat}", message.chat.title or "المجموعة"
        )
        await message.answer(text)
