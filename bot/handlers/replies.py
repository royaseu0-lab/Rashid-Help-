import json
import re

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot import db
from bot.filters import IsGroupAdmin, IsGroupChat

router = Router()
router.message.filter(IsGroupChat())


class AddReply(StatesGroup):
    choosing_match_type = State()
    waiting_triggers = State()
    waiting_content = State()


class DeleteReply(StatesGroup):
    waiting_trigger = State()


def _match_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ البحث في كامل الجملة", callback_data="match:contains")],
            [InlineKeyboardButton(text="❌ مطابقة كاملة", callback_data="match:exact")],
        ]
    )


@router.message(F.text == "اضف رد", IsGroupAdmin())
async def start_add_reply(message: Message, state: FSMContext):
    await state.update_data(chat_id=message.chat.id)
    await state.set_state(AddReply.choosing_match_type)
    await message.reply("اختر طريقة البحث:", reply_markup=_match_type_keyboard())


@router.callback_query(AddReply.choosing_match_type, F.data.startswith("match:"))
async def choose_match_type(callback: CallbackQuery, state: FSMContext):
    match_type = callback.data.split(":", 1)[1]
    await state.update_data(match_type=match_type)
    await state.set_state(AddReply.waiting_triggers)
    await callback.message.edit_text(
        "أرسل الأمر/الأوامر الآن (يمكنك إضافة أكثر من أمر مفصولة بـ |)\nمثال: هلا|مرحبا"
    )
    await callback.answer()


@router.message(AddReply.waiting_triggers, F.text)
async def receive_triggers(message: Message, state: FSMContext):
    triggers = [t.strip() for t in message.text.split("|") if t.strip()]
    if not triggers:
        await message.reply("⚠️ أرسل أمرًا واحدًا على الأقل.")
        return
    await state.update_data(triggers=triggers)
    await state.set_state(AddReply.waiting_content)
    await message.reply(
        "الآن أرسل الرد (نص، أو صورة/فيديو/ملصق/ملف). يمكنك استخدام أزرار بالصيغة:\n"
        "{[ النص - t.me/link ]}"
    )


def _extract_buttons(text: str) -> tuple[str, list]:
    buttons = []
    pattern = re.compile(r"\{\[\s*(.+?)\s*-\s*(.+?)\s*\]\}")

    def _strip(m):
        buttons.append({"text": m.group(1), "url": m.group(2)})
        return ""

    cleaned = pattern.sub(_strip, text).strip()
    return cleaned, buttons


@router.message(AddReply.waiting_content)
async def receive_content(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data["chat_id"]
    triggers = data["triggers"]
    match_type = data["match_type"]

    content_type = "text"
    content_text = ""
    file_id = ""
    buttons = []

    if message.text:
        content_text, buttons = _extract_buttons(message.text)
    elif message.photo:
        content_type = "photo"
        file_id = message.photo[-1].file_id
        content_text = message.caption or ""
    elif message.video:
        content_type = "video"
        file_id = message.video.file_id
        content_text = message.caption or ""
    elif message.sticker:
        content_type = "sticker"
        file_id = message.sticker.file_id
    elif message.document:
        content_type = "document"
        file_id = message.document.file_id
        content_text = message.caption or ""
    elif message.voice:
        content_type = "voice"
        file_id = message.voice.file_id
    elif message.animation:
        content_type = "animation"
        file_id = message.animation.file_id
        content_text = message.caption or ""
    else:
        await message.reply("⚠️ نوع المحتوى غير مدعوم، أرسل نص أو صورة أو فيديو أو ملصق أو ملف.")
        return

    await db.add_reply(
        chat_id, triggers, match_type, content_type, content_text, file_id, buttons
    )
    await state.clear()
    await message.reply(f"✅ تم حفظ الرد بنجاح للأمر/الأوامر: {' | '.join(triggers)}")


@router.message(F.text == "حذف رد", IsGroupAdmin())
async def start_delete_reply(message: Message, state: FSMContext):
    await state.set_state(DeleteReply.waiting_trigger)
    await message.reply("أرسل الأمر الذي تريد حذف الرد الخاص به:")


@router.message(DeleteReply.waiting_trigger, F.text)
async def finish_delete_reply(message: Message, state: FSMContext):
    removed = await db.delete_reply_by_trigger(message.chat.id, message.text.strip())
    await state.clear()
    if removed:
        await message.reply("✅ تم حذف الرد.")
    else:
        await message.reply("⚠️ لم يتم العثور على رد بهذا الأمر.")


@router.message(F.text.in_({"ردود", "قائمة الردود"}))
async def list_replies(message: Message):
    replies = await db.list_replies(message.chat.id)
    if not replies:
        await message.reply("لا توجد ردود مضافة في هذه المجموعة.")
        return
    lines = []
    for i, r in enumerate(replies, start=1):
        triggers = r["triggers"].replace("|", " / ")
        lines.append(f"{i}. {triggers}")
    await message.reply("📋 قائمة الردود:\n" + "\n".join(lines))


def _normalize(text: str) -> str:
    return re.sub(r"[\s\W]+", "", text, flags=re.UNICODE).lower()


@router.message(F.text)
async def trigger_match(message: Message):
    replies = await db.list_replies(message.chat.id)
    if not replies:
        raise SkipHandler

    text = message.text.strip()
    normalized_text = _normalize(text)

    for r in replies:
        triggers = r["triggers"].split("|")
        for trig in triggers:
            if r["match_type"] == "exact":
                if text == trig:
                    await _send_reply(message, r)
                    return
            else:
                if _normalize(trig) and _normalize(trig) in normalized_text:
                    await _send_reply(message, r)
                    return

    raise SkipHandler


async def _send_reply(message: Message, reply_row: dict):
    buttons = json.loads(reply_row["buttons"] or "[]")
    markup = None
    if buttons:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=b["text"], url=b["url"])] for b in buttons]
        )

    content_type = reply_row["content_type"]
    text = reply_row["content_text"]
    file_id = reply_row["file_id"]

    if content_type == "text":
        await message.reply(text or "...", reply_markup=markup)
    elif content_type == "photo":
        await message.reply_photo(file_id, caption=text or None, reply_markup=markup)
    elif content_type == "video":
        await message.reply_video(file_id, caption=text or None, reply_markup=markup)
    elif content_type == "sticker":
        await message.reply_sticker(file_id)
    elif content_type == "document":
        await message.reply_document(file_id, caption=text or None, reply_markup=markup)
    elif content_type == "voice":
        await message.reply_voice(file_id)
    elif content_type == "animation":
        await message.reply_animation(file_id, caption=text or None, reply_markup=markup)
