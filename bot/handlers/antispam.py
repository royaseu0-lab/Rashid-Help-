import re
import time
from collections import defaultdict, deque

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions, Message

from bot import db
from bot.config import OWNER_ID
from bot.filters import IsGroupAdmin, IsGroupChat
from bot.utils import is_group_admin, mention, strip_command

router = Router()
router.message.filter(IsGroupChat())

_LINK_RE = re.compile(r"(https?://|t\.me/|telegram\.me/|@\w{4,})", re.IGNORECASE)

# in-memory flood tracker: {(chat_id, user_id): deque[timestamps]}
_flood_tracker: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=20))

NO_PERMISSIONS = ChatPermissions(can_send_messages=False)


@router.message(F.text.regexp(r"^منع\s+(.+)$"), IsGroupAdmin())
async def cmd_add_blacklist(message: Message):
    word = strip_command(message.text).strip()
    if not word:
        return
    await db.add_blacklist_word(message.chat.id, word)
    await message.reply(f"🚫 تمت إضافة «{word}» إلى الكلمات الممنوعة.")


@router.message(F.text.regexp(r"^(قائمة المنع)$"))
async def cmd_list_blacklist(message: Message):
    words = await db.list_blacklist(message.chat.id)
    if not words:
        await message.reply("لا توجد كلمات ممنوعة حاليًا في هذه المجموعة.")
        return
    listing = "\n".join(f"• {w}" for w in words)
    await message.reply(f"🚫 الكلمات الممنوعة:\n{listing}")


@router.message(F.text.regexp(r"^الغاء منع\s+(.+)$"), IsGroupAdmin())
async def cmd_remove_blacklist(message: Message):
    word = strip_command(message.text).strip()
    removed = await db.remove_blacklist_word(message.chat.id, word)
    if removed:
        await message.reply(f"✅ تم إلغاء منع «{word}».")
    else:
        await message.reply("⚠️ هذه الكلمة غير موجودة في قائمة المنع.")


@router.message(F.text.regexp(r"^(مسح قائمة المنع)$"), IsGroupAdmin())
async def cmd_clear_blacklist(message: Message):
    await db.clear_blacklist(message.chat.id)
    await message.reply("✅ تم مسح جميع الكلمات الممنوعة.")


@router.message(F.text.regexp(r"^(تفعيل منع الروابط)$"), IsGroupAdmin())
async def cmd_enable_antilink(message: Message):
    await db.set_group_field(message.chat.id, "antilink", 1)
    await message.reply("🔗🚫 تم تفعيل منع الروابط في المجموعة.")


@router.message(F.text.regexp(r"^(ايقاف منع الروابط|إيقاف منع الروابط)$"), IsGroupAdmin())
async def cmd_disable_antilink(message: Message):
    await db.set_group_field(message.chat.id, "antilink", 0)
    await message.reply("🔗✅ تم إيقاف منع الروابط في المجموعة.")


@router.message(F.text.regexp(r"^(المحظورين)$"))
async def cmd_list_banned(message: Message):
    rows = await db.list_banned(message.chat.id)
    if not rows:
        await message.reply("لا يوجد أعضاء محظورون مسجلون.")
        return
    listing = "\n".join(f"• <code>{uid}</code>" for uid, _ in rows)
    await message.reply(f"🚫 الأعضاء المحظورون:\n{listing}")


@router.message(F.text.regexp(r"^(المقيدين)$"))
async def cmd_list_muted(message: Message):
    rows = await db.list_muted(message.chat.id)
    if not rows:
        await message.reply("لا يوجد أعضاء مقيدون مسجلون.")
        return
    listing = "\n".join(f"• <code>{uid}</code>" for uid, _, _ in rows)
    await message.reply(f"🔇 الأعضاء المقيدون:\n{listing}")


@router.message(F.text, F.text.func(lambda t: not t.startswith(("/", "."))))
async def catch_all_moderation(message: Message, bot: Bot):
    """Runs last: enforces blacklist words, link blocking, and flood control."""
    if not message.from_user or message.from_user.id == OWNER_ID:
        return
    if await is_group_admin(bot, message.chat.id, message.from_user.id):
        return

    group = await db.get_group(message.chat.id)
    text = message.text or ""

    if group.get("antilink") and _LINK_RE.search(text):
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        count = await db.add_warn(message.chat.id, message.from_user.id)
        await message.answer(
            f"🔗 تم حذف رسالة {mention(message.from_user)} لاحتوائها على رابط ممنوع. "
            f"(إنذار {count})"
        )
        return

    blacklist = await db.list_blacklist(message.chat.id)
    normalized = re.sub(r"[\s\W]+", "", text, flags=re.UNICODE)
    for word in blacklist:
        normalized_word = re.sub(r"[\s\W]+", "", word, flags=re.UNICODE)
        if normalized_word and normalized_word in normalized:
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            await message.answer(
                f"🚫 تم حذف رسالة {mention(message.from_user)} لاحتوائها على كلمة ممنوعة."
            )
            return

    if group.get("antiflood"):
        key = (message.chat.id, message.from_user.id)
        now = time.time()
        bucket = _flood_tracker[key]
        bucket.append(now)
        window = group.get("flood_seconds", 8)
        limit = group.get("flood_limit", 5)
        recent = [t for t in bucket if now - t <= window]
        if len(recent) >= limit:
            try:
                await bot.restrict_chat_member(
                    message.chat.id, message.from_user.id, permissions=NO_PERMISSIONS,
                    until_date=int(now) + 300,
                )
            except TelegramBadRequest:
                pass
            await db.record_mute(message.chat.id, message.from_user.id, int(now) + 300, "flood")
            bucket.clear()
            await message.answer(
                f"⛔️ تم كتم {mention(message.from_user)} لمدة 5 دقائق بسبب الإسبام/التكرار."
            )
