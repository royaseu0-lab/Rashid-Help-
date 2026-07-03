import re
import time
from collections import defaultdict, deque

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions, Message

from bot import db
from bot.config import OWNER_ID, SIGHTENGINE_API_SECRET, SIGHTENGINE_API_USER
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


@router.message(F.text.regexp(r"^(تفعيل حماية الصور)$"), IsGroupAdmin())
async def cmd_enable_nsfw(message: Message):
    await db.set_group_field(message.chat.id, "nsfw_ban", 1)
    note = "" if (SIGHTENGINE_API_USER and SIGHTENGINE_API_SECRET) else "\n⚠️ يحتاج إعداد SIGHTENGINE_API_USER و SIGHTENGINE_API_SECRET في متغيرات البيئة."
    await message.reply(f"🔞🛡 تم تفعيل حماية الصور الإباحية. سيتم حظر المرسل وحذف رسائله.{note}")


@router.message(F.text.regexp(r"^(ايقاف حماية الصور|إيقاف حماية الصور)$"), IsGroupAdmin())
async def cmd_disable_nsfw(message: Message):
    await db.set_group_field(message.chat.id, "nsfw_ban", 0)
    await message.reply("🔞 تم إيقاف حماية الصور الإباحية.")


def _normalize_bl(text: str) -> str:
    """Normalize text for blacklist matching: strip symbols, diacritics, collapse repeats."""
    # Remove all non-letter characters (punctuation, spaces, tatweel, underscores...)
    cleaned = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    # Remove Arabic diacritics (harakat / tashkeel)
    cleaned = re.sub(r"[ً-ٰٟۖ-ۭ]", "", cleaned)
    # Collapse consecutive repeated characters: خاااص → خاص
    cleaned = re.sub(r"(.)\1+", r"\1", cleaned)
    return cleaned.lower()


async def _check_nsfw_score(bot: Bot, file_id: str) -> float:
    """Returns nudity score 0.0–1.0 via Sightengine API. Returns 0.0 if not configured or error."""
    if not SIGHTENGINE_API_USER or not SIGHTENGINE_API_SECRET:
        return 0.0
    try:
        import aiohttp
        tg_file = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{bot.token}/{tg_file.file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.sightengine.com/1.0/check.json",
                params={
                    "url": file_url,
                    "models": "nudity-2.0",
                    "api_user": SIGHTENGINE_API_USER,
                    "api_secret": SIGHTENGINE_API_SECRET,
                },
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json()
        nudity = data.get("nudity", {})
        return max(float(nudity.get("very_explicit", 0)), float(nudity.get("erotica", 0)))
    except Exception:
        return 0.0


@router.message(F.photo | F.video, IsGroupChat())
async def check_nsfw_media(message: Message, bot: Bot):
    if not message.from_user or message.from_user.id == OWNER_ID:
        return
    if await is_group_admin(bot, message.chat.id, message.from_user.id):
        return
    group = await db.get_group(message.chat.id)
    if not group.get("nsfw_ban"):
        return

    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.video and message.video.thumbnail:
        file_id = message.video.thumbnail.file_id
    else:
        return

    score = await _check_nsfw_score(bot, file_id)
    if score < 0.75:
        return

    try:
        await message.delete()
        await bot.ban_chat_member(message.chat.id, message.from_user.id, revoke_messages=True)
        await db.record_ban(message.chat.id, message.from_user.id)
        await message.answer(f"🔞 تم حظر {mention(message.from_user)} لإرساله محتوى إباحي وحذف رسائله.")
    except TelegramBadRequest:
        pass


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
    normalized_text = _normalize_bl(text)
    for word in blacklist:
        normalized_word = _normalize_bl(word)
        if normalized_word and normalized_word in normalized_text:
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
