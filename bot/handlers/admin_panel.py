import json

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import db
from bot.config import DEVELOPER_CONTACT, OWNER_ID

router = Router()
router.message.filter(F.chat.type == "private", F.from_user.id == OWNER_ID)
router.callback_query.filter(F.from_user.id == OWNER_ID)

REPLIES_PER_PAGE = 5


class PanelState(StatesGroup):
    broadcast = State()
    edit_welcome = State()
    edit_rules = State()
    edit_bot_info = State()
    # add reply from panel
    add_reply_match = State()
    add_reply_triggers = State()
    add_reply_content = State()


# ─── keyboard helpers ─────────────────────────────────────────────────────────

def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _url_btn(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def back_btn(dest: str = "ap:main") -> list[InlineKeyboardButton]:
    return [_btn("◀️ رجوع", dest)]


# ─── main panel ───────────────────────────────────────────────────────────────

def main_kb(group_count: int) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("⚙️ الإعدادات", "ap:settings"), _btn("📝 المحتوى", "ap:content")],
        [_btn("👥 المجموعات", "ap:groups"), _btn("📢 بث رسالة", "ap:broadcast")],
        [_btn("🔧 النظام والدعم", "ap:system")],
    )


async def _all_groups() -> list[dict]:
    ids = await db.all_group_ids()
    groups = []
    for cid in ids:
        g = await db.get_group(cid)
        groups.append(g)
    return groups


def groups_kb(groups: list[dict], back: str = "ap:main") -> InlineKeyboardMarkup:
    rows = []
    for g in groups:
        title = (g.get("title") or str(g["chat_id"]))[:30]
        rows.append([_btn(f"🏘 {title}", f"ap:g:{g['chat_id']}")])
    rows.append(back_btn(back))
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── group menu ───────────────────────────────────────────────────────────────

def group_menu_kb(chat_id: int) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("⚙️ الإعدادات", f"ap:g:{chat_id}:settings")],
        [_btn("📝 المحتوى", f"ap:g:{chat_id}:content")],
        [_btn("📊 إحصائيات", f"ap:g:{chat_id}:stats")],
        back_btn("ap:groups"),
    )


# ─── group settings ───────────────────────────────────────────────────────────

def group_settings_kb(chat_id: int, g: dict) -> InlineKeyboardMarkup:
    def tog(label_on, label_off, field):
        val = g.get(field, 0)
        icon = "✅" if val else "🔴"
        label = label_on if val else label_off
        return _btn(f"{icon} {label}", f"ap:g:{chat_id}:toggle:{field}")

    return _kb(
        [tog("الحماية من الفيضان مفعّلة", "الحماية من الفيضان معطّلة", "antiflood")],
        [tog("منع الروابط مفعّل", "منع الروابط معطّل", "antilink")],
        [tog("الترحيب مفعّل", "الترحيب معطّل", "welcome_enabled")],
        [tog("القروب مقفول", "القروب مفتوح", "locked")],
        [_btn("📜 تعديل القوانين", f"ap:g:{chat_id}:edit_rules")],
        back_btn(f"ap:g:{chat_id}"),
    )


# ─── group content (full panel as requested) ──────────────────────────────────

def group_content_kb(chat_id: int, replies_count: int, deeplink_count: int = 0) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("👋 رسالة الترحيب", f"ap:g:{chat_id}:edit_welcome")],
        [_btn(f"💬 الردود التلقائية ({replies_count})", f"ap:g:{chat_id}:replies:0")],
        [_btn("✏️ تعديل الأزرار", f"ap:g:{chat_id}:edit_buttons"),
         _btn("🔘 الأزرار الشفافة", f"ap:g:{chat_id}:transparent_btns")],
        [_btn("📎 الاختصارات", f"ap:g:{chat_id}:shortcuts")],
        [_btn("📋 قائمة التعديلات", f"ap:g:{chat_id}:edits_log"),
         _btn("✏️ تعديل المحتوى", f"ap:g:{chat_id}:edit_content")],
        [_btn(f"🔗 ديب لينك مخصص ({deeplink_count})", f"ap:g:{chat_id}:deeplinks")],
        [_btn("ℹ️ معلومات البوت", f"ap:g:{chat_id}:bot_info")],
        [_btn("❓ المساعدة", f"ap:g:{chat_id}:help_page")],
        back_btn(f"ap:g:{chat_id}"),
    )


# ─── replies list with pagination ─────────────────────────────────────────────

def replies_kb(chat_id: int, replies: list[dict], page: int) -> InlineKeyboardMarkup:
    rows = []
    rows.append([_btn("➕ إضافة رد جديد", f"ap:g:{chat_id}:reply:add")])

    total = len(replies)
    start = page * REPLIES_PER_PAGE
    end = min(start + REPLIES_PER_PAGE, total)
    page_replies = replies[start:end]

    if total:
        rows.append([_btn("─────── الردود ───────", "ap:noop")])
    for r in page_replies:
        triggers = r["triggers"].replace("|", " / ")[:35]
        rows.append([_btn(f"💬 {triggers}", f"ap:g:{chat_id}:reply:{r['id']}")])

    # pagination row
    nav = []
    if page > 0:
        nav.append(_btn("◀️", f"ap:g:{chat_id}:replies:{page - 1}"))
    if total:
        nav.append(_btn(f"📄 {page + 1}/{max(1, (total + REPLIES_PER_PAGE - 1) // REPLIES_PER_PAGE)}", "ap:noop"))
    if end < total:
        nav.append(_btn("▶️", f"ap:g:{chat_id}:replies:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append(back_btn(f"ap:g:{chat_id}:content"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reply_detail_kb(chat_id: int, reply_id: int, page: int) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("🗑️ حذف هذا الرد", f"ap:g:{chat_id}:reply:{reply_id}:del")],
        back_btn(f"ap:g:{chat_id}:replies:{page}"),
    )


def match_type_kb(chat_id: int) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("✅ البحث في كامل الجملة", f"ap:g:{chat_id}:reply:add:contains")],
        [_btn("❌ مطابقة كاملة فقط", f"ap:g:{chat_id}:reply:add:exact")],
        back_btn(f"ap:g:{chat_id}:replies:0"),
    )


# ─── /admin entry ─────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    count = await db.count_groups()
    text = (
        f"🤖 <b>لوحة تحكم المساعد رشيد</b>\n\n"
        f"📊 المجموعات النشطة: <b>{count}</b>\n"
        f"👤 المالك: {DEVELOPER_CONTACT}\n\n"
        "اختر القسم الذي تريد إدارته:"
    )
    await message.answer(text, reply_markup=main_kb(count))


# ─── main menu callback ───────────────────────────────────────────────────────

@router.callback_query(F.data == "ap:main")
async def panel_main(cb: CallbackQuery):
    count = await db.count_groups()
    text = (
        f"🤖 <b>لوحة تحكم المساعد رشيد</b>\n\n"
        f"📊 المجموعات النشطة: <b>{count}</b>\n"
        f"👤 المالك: {DEVELOPER_CONTACT}\n\n"
        "اختر القسم الذي تريد إدارته:"
    )
    await cb.message.edit_text(text, reply_markup=main_kb(count))
    await cb.answer()


@router.callback_query(F.data == "ap:noop")
async def noop(cb: CallbackQuery):
    await cb.answer()


# ─── settings ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ap:settings")
async def panel_settings(cb: CallbackQuery):
    groups = await _all_groups()
    if not groups:
        await cb.answer("لا توجد مجموعات مسجّلة بعد.", show_alert=True)
        return
    await cb.message.edit_text(
        "⚙️ <b>الإعدادات</b>\n\nاختر المجموعة:",
        reply_markup=groups_kb(groups, back="ap:main"),
    )
    await cb.answer()


# ─── content ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ap:content")
async def panel_content(cb: CallbackQuery):
    groups = await _all_groups()
    if not groups:
        await cb.answer("لا توجد مجموعات مسجّلة بعد.", show_alert=True)
        return
    await cb.message.edit_text(
        "📝 <b>المحتوى</b>\n\nاختر المجموعة:",
        reply_markup=groups_kb(groups, back="ap:main"),
    )
    await cb.answer()


# ─── groups list ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ap:groups")
async def panel_groups(cb: CallbackQuery):
    groups = await _all_groups()
    if not groups:
        await cb.answer("لا توجد مجموعات مسجّلة بعد.", show_alert=True)
        return
    await cb.message.edit_text(
        f"👥 <b>المجموعات</b> ({len(groups)})\n\nاختر مجموعة لإدارتها:",
        reply_markup=groups_kb(groups, back="ap:main"),
    )
    await cb.answer()


# ─── group submenu ────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+)$"))
async def panel_group_menu(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    g = await db.get_group(chat_id)
    title = g.get("title") or str(chat_id)
    replies = await db.list_replies(chat_id)
    blacklist = await db.list_blacklist(chat_id)
    text = (
        f"🏘 <b>{title}</b>\n\n"
        f"🆔 آيدي: <code>{chat_id}</code>\n"
        f"💬 الردود التلقائية: {len(replies)}\n"
        f"🚫 الكلمات الممنوعة: {len(blacklist)}\n"
        f"🔒 مقفول: {'نعم' if g.get('locked') else 'لا'}\n"
        f"👋 الترحيب: {'مفعّل' if g.get('welcome_enabled') else 'معطّل'}"
    )
    await cb.message.edit_text(text, reply_markup=group_menu_kb(chat_id))
    await cb.answer()


# ─── group settings ───────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):settings$"))
async def panel_group_settings(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    g = await db.get_group(chat_id)
    title = g.get("title") or str(chat_id)
    await cb.message.edit_text(
        f"⚙️ <b>إعدادات: {title}</b>\n\nاضغط على أي خيار لتفعيله أو تعطيله:",
        reply_markup=group_settings_kb(chat_id, g),
    )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):toggle:(\w+)$"))
async def panel_toggle(cb: CallbackQuery, bot: Bot):
    parts = cb.data.split(":")
    chat_id = int(parts[2])
    field = parts[4]
    g = await db.get_group(chat_id)
    new_val = 0 if g.get(field, 0) else 1
    await db.set_group_field(chat_id, field, new_val)
    g[field] = new_val
    if field == "locked":
        from bot.handlers.moderation import FULL_PERMISSIONS, NO_PERMISSIONS
        try:
            perms = NO_PERMISSIONS if new_val else FULL_PERMISSIONS
            await bot.set_chat_permissions(chat_id, permissions=perms)
        except TelegramBadRequest:
            pass
    title = g.get("title") or str(chat_id)
    await cb.answer("✅ مفعّل" if new_val else "🔴 معطّل")
    await cb.message.edit_text(
        f"⚙️ <b>إعدادات: {title}</b>\n\nاضغط على أي خيار لتفعيله أو تعطيله:",
        reply_markup=group_settings_kb(chat_id, g),
    )


# ─── group content ────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):content$"))
async def panel_group_content(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    replies = await db.list_replies(chat_id)
    g = await db.get_group(chat_id)
    title = g.get("title") or str(chat_id)
    await cb.message.edit_text(
        f"📝 <b>المحتوى: {title}</b>\n\nإدارة رسائل البوت والردود التلقائية",
        reply_markup=group_content_kb(chat_id, len(replies)),
    )
    await cb.answer()


# ─── group stats ──────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):stats$"))
async def panel_group_stats(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    g = await db.get_group(chat_id)
    replies = await db.list_replies(chat_id)
    blacklist = await db.list_blacklist(chat_id)
    banned = await db.list_banned(chat_id)
    muted = await db.list_muted(chat_id)
    title = g.get("title") or str(chat_id)
    text = (
        f"📊 <b>إحصائيات: {title}</b>\n\n"
        f"💬 الردود التلقائية: {len(replies)}\n"
        f"🚫 الكلمات الممنوعة: {len(blacklist)}\n"
        f"🔒 المحظورون: {len(banned)}\n"
        f"🔇 المكتومون: {len(muted)}\n"
        f"👋 الترحيب: {'مفعّل' if g.get('welcome_enabled') else 'معطّل'}\n"
        f"🔗 منع الروابط: {'مفعّل' if g.get('antilink') else 'معطّل'}\n"
        f"⚡ حماية الفيضان: {'مفعّلة' if g.get('antiflood') else 'معطّلة'}"
    )
    await cb.message.edit_text(text, reply_markup=_kb(back_btn(f"ap:g:{chat_id}")))
    await cb.answer()


# ─── replies list (paginated) ─────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):replies:(\d+)$"))
async def panel_replies_list(cb: CallbackQuery):
    parts = cb.data.split(":")
    chat_id = int(parts[2])
    page = int(parts[4])
    replies = await db.list_replies(chat_id)
    total = len(replies)
    g = await db.get_group(chat_id)
    title = g.get("title") or str(chat_id)
    text = (
        f"💬 <b>الردود التلقائية: {title}</b>\n"
        f"العدد الإجمالي: <b>{total}</b> رد\n\n"
        "اضغط على أي رد لعرض تفاصيله أو حذفه\n"
        "اضغط ➕ لإضافة رد جديد"
    )
    await cb.message.edit_text(text, reply_markup=replies_kb(chat_id, replies, page))
    await cb.answer()


# ─── single reply detail ──────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):reply:(\d+)$"))
async def panel_reply_detail(cb: CallbackQuery):
    parts = cb.data.split(":")
    chat_id = int(parts[2])
    reply_id = int(parts[4])
    replies = await db.list_replies(chat_id)
    reply = next((r for r in replies if r["id"] == reply_id), None)
    if not reply:
        await cb.answer("هذا الرد لم يعد موجودًا.", show_alert=True)
        return
    triggers = reply["triggers"].replace("|", "\n• ")
    match_label = "البحث في كامل الجملة" if reply["match_type"] == "contains" else "مطابقة كاملة"
    type_labels = {
        "text": "نص", "photo": "صورة", "video": "فيديو",
        "sticker": "ملصق", "document": "ملف", "voice": "صوت", "animation": "GIF"
    }
    content_type = type_labels.get(reply["content_type"], reply["content_type"])
    content_preview = (reply["content_text"] or "")[:100]
    page = 0
    for i, r in enumerate(replies):
        if r["id"] == reply_id:
            page = i // REPLIES_PER_PAGE
            break
    text = (
        f"💬 <b>تفاصيل الرد #{reply_id}</b>\n\n"
        f"📌 الأوامر:\n• {triggers}\n\n"
        f"🔍 نوع البحث: {match_label}\n"
        f"📄 نوع المحتوى: {content_type}\n"
    )
    if content_preview:
        text += f"✏️ المحتوى:\n<i>{content_preview}</i>"
    await cb.message.edit_text(text, reply_markup=reply_detail_kb(chat_id, reply_id, page))
    await cb.answer()


# ─── delete reply ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):reply:(\d+):del$"))
async def panel_reply_delete(cb: CallbackQuery):
    parts = cb.data.split(":")
    chat_id = int(parts[2])
    reply_id = int(parts[4])
    async with __import__("aiosqlite").connect(__import__("bot.config", fromlist=["DATABASE_PATH"]).DATABASE_PATH) as db_conn:
        await db_conn.execute("DELETE FROM replies WHERE id = ? AND chat_id = ?", (reply_id, chat_id))
        await db_conn.commit()
    replies = await db.list_replies(chat_id)
    total = len(replies)
    await cb.answer("🗑️ تم حذف الرد.", show_alert=False)
    g = await db.get_group(chat_id)
    title = g.get("title") or str(chat_id)
    await cb.message.edit_text(
        f"💬 <b>الردود التلقائية: {title}</b>\n"
        f"العدد الإجمالي: <b>{total}</b> رد\n\n"
        "اضغط على أي رد لعرض تفاصيله أو حذفه\n"
        "اضغط ➕ لإضافة رد جديد",
        reply_markup=replies_kb(chat_id, replies, 0),
    )


# ─── add reply from panel: choose match type ─────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):reply:add$"))
async def panel_add_reply_start(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    await state.set_state(PanelState.add_reply_match)
    await state.update_data(panel_chat_id=chat_id)
    await cb.message.edit_text(
        "➕ <b>إضافة رد جديد</b>\n\nاختر طريقة البحث:",
        reply_markup=match_type_kb(chat_id),
    )
    await cb.answer()


@router.callback_query(PanelState.add_reply_match, F.data.regexp(r"^ap:g:(-?\d+):reply:add:(contains|exact)$"))
async def panel_add_reply_match_chosen(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    chat_id = int(parts[2])
    match_type = parts[5]
    await state.update_data(panel_match_type=match_type)
    await state.set_state(PanelState.add_reply_triggers)
    label = "البحث في كامل الجملة ✅" if match_type == "contains" else "مطابقة كاملة ❌"
    await cb.message.edit_text(
        f"➕ <b>إضافة رد جديد</b>\nطريقة البحث: {label}\n\n"
        "أرسل الآن الأمر/الأوامر (يمكنك فصل أكثر من أمر بـ |)\n"
        "مثال: <code>هلا|مرحبا|أهلا</code>\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await cb.answer()


@router.message(PanelState.add_reply_triggers, F.text)
async def panel_add_reply_triggers(message: Message, state: FSMContext):
    if message.text == "/cancel":
        data = await state.get_data()
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return
    triggers = [t.strip() for t in message.text.split("|") if t.strip()]
    if not triggers:
        await message.answer("⚠️ أرسل أمرًا واحدًا على الأقل.")
        return
    await state.update_data(panel_triggers=triggers)
    await state.set_state(PanelState.add_reply_content)
    await message.answer(
        f"✅ الأوامر: <b>{' | '.join(triggers)}</b>\n\n"
        "الآن أرسل الرد:\n"
        "• نص عادي\n"
        "• صورة أو فيديو أو ملصق أو ملف\n"
        "• يمكن إضافة أزرار بالصيغة: <code>{[ النص - t.me/link ]}</code>\n\n"
        "أو أرسل /cancel للإلغاء"
    )


@router.message(PanelState.add_reply_content)
async def panel_add_reply_content(message: Message, state: FSMContext):
    if message.text == "/cancel":
        data = await state.get_data()
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return
    data = await state.get_data()
    chat_id = data["panel_chat_id"]
    triggers = data["panel_triggers"]
    match_type = data["panel_match_type"]

    import re as _re
    import json as _json

    def _extract_buttons(text: str):
        buttons = []
        pattern = _re.compile(r"\{\[\s*(.+?)\s*-\s*(.+?)\s*\]\}")
        def _strip(m):
            buttons.append({"text": m.group(1), "url": m.group(2)})
            return ""
        cleaned = pattern.sub(_strip, text).strip()
        return cleaned, buttons

    content_type = "text"
    content_text = ""
    file_id = ""
    buttons = []

    if message.text:
        content_text, buttons = _extract_buttons(message.text)
    elif message.photo:
        content_type, file_id = "photo", message.photo[-1].file_id
        content_text = message.caption or ""
    elif message.video:
        content_type, file_id = "video", message.video.file_id
        content_text = message.caption or ""
    elif message.sticker:
        content_type, file_id = "sticker", message.sticker.file_id
    elif message.document:
        content_type, file_id = "document", message.document.file_id
        content_text = message.caption or ""
    elif message.voice:
        content_type, file_id = "voice", message.voice.file_id
    elif message.animation:
        content_type, file_id = "animation", message.animation.file_id
        content_text = message.caption or ""
    else:
        await message.answer("⚠️ نوع المحتوى غير مدعوم.")
        return

    await db.add_reply(chat_id, triggers, match_type, content_type, content_text, file_id, buttons)
    await state.clear()

    replies = await db.list_replies(chat_id)
    total = len(replies)
    g = await db.get_group(chat_id)
    title = g.get("title") or str(chat_id)
    await message.answer(
        f"✅ تم حفظ الرد بنجاح!\n"
        f"الأوامر: <b>{' | '.join(triggers)}</b>\n"
        f"إجمالي الردود الآن: <b>{total}</b>",
        reply_markup=replies_kb(chat_id, replies, 0),
    )


# ─── edit welcome ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):edit_welcome$"))
async def panel_edit_welcome_start(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    g = await db.get_group(chat_id)
    current = g.get("welcome_text") or "لم يتم تعيين رسالة ترحيب بعد."
    await state.set_state(PanelState.edit_welcome)
    await state.update_data(chat_id=chat_id)
    await cb.message.edit_text(
        f"👋 <b>رسالة الترحيب الحالية:</b>\n\n{current}\n\n"
        "أرسل رسالة الترحيب الجديدة\n"
        "المتغيرات المتاحة: <code>{user}</code> للاسم، <code>{chat}</code> لاسم المجموعة\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    await cb.answer()


@router.message(PanelState.edit_welcome, F.text)
async def panel_edit_welcome_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return
    data = await state.get_data()
    chat_id = data["chat_id"]
    await db.set_group_field(chat_id, "welcome_text", message.text)
    await db.set_group_field(chat_id, "welcome_enabled", 1)
    await state.clear()
    replies = await db.list_replies(chat_id)
    await message.answer(
        "✅ تم حفظ رسالة الترحيب وتفعيلها.",
        reply_markup=group_content_kb(chat_id, len(replies)),
    )


# ─── edit rules ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):edit_rules$"))
async def panel_edit_rules_start(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    g = await db.get_group(chat_id)
    current = g.get("rules") or "لم يتم تعيين قوانين بعد."
    await state.set_state(PanelState.edit_rules)
    await state.update_data(chat_id=chat_id)
    await cb.message.edit_text(
        f"📜 <b>القوانين الحالية:</b>\n\n{current}\n\n"
        "أرسل القوانين الجديدة أو /cancel للإلغاء:"
    )
    await cb.answer()


@router.message(PanelState.edit_rules, F.text)
async def panel_edit_rules_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return
    data = await state.get_data()
    chat_id = data["chat_id"]
    await db.set_group_field(chat_id, "rules", message.text)
    await state.clear()
    g = await db.get_group(chat_id)
    await message.answer("✅ تم حفظ القوانين.", reply_markup=group_settings_kb(chat_id, g))


# ─── bot info ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):bot_info$"))
async def panel_bot_info(cb: CallbackQuery, state: FSMContext):
    chat_id = int(cb.data.split(":")[2])
    g = await db.get_group(chat_id)
    title = g.get("title") or str(chat_id)
    await state.set_state(PanelState.edit_bot_info)
    await state.update_data(chat_id=chat_id)
    await cb.message.edit_text(
        f"ℹ️ <b>معلومات البوت في: {title}</b>\n\n"
        "أرسل النص الذي تريد عرضه عند كتابة <b>المطور</b> أو /cancel للإلغاء:"
    )
    await cb.answer()


@router.message(PanelState.edit_bot_info, F.text)
async def panel_bot_info_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ تم الإلغاء.")
        return
    await state.clear()
    await message.answer("✅ تم الحفظ.")


# ─── placeholder panels ───────────────────────────────────────────────────────

async def _coming_soon(cb: CallbackQuery, title: str, back: str):
    await cb.message.edit_text(
        f"{title}\n\n⏳ هذه الميزة قيد التطوير وستكون متاحة قريبًا.",
        reply_markup=_kb(back_btn(back)),
    )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):edit_buttons$"))
async def panel_edit_buttons(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    await _coming_soon(cb, "✏️ <b>تعديل الأزرار</b>", f"ap:g:{chat_id}:content")


@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):transparent_btns$"))
async def panel_transparent_btns(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    demo_kb = InlineKeyboardMarkup(inline_keyboard=[
        # live demo buttons so owner sees exactly how they render
        [InlineKeyboardButton(text="📢 قناتنا", url="https://t.me/Rashid_1Help"),
         InlineKeyboardButton(text="🌐 الموقع", url="https://t.me/Rashid_1Help")],
        [InlineKeyboardButton(text="✉️ تواصل معنا", url="https://t.me/Rashid_1Help")],
        # action buttons
        [_btn("➕ إضافة رد مع أزرار", f"ap:g:{chat_id}:reply:add")],
        back_btn(f"ap:g:{chat_id}:content"),
    ])
    await cb.message.edit_text(
        "🔘 <b>الأزرار الشفافة</b>\n\n"
        "أضف أزرار URL في ردودك التلقائية بالصيغة:\n"
        "<code>{[ النص - الرابط ]}</code>\n\n"
        "<b>مثال كامل:</b>\n"
        "<code>أهلاً! تابعنا على:\n"
        "{[ قناتنا - t.me/mychannel ]}\n"
        "{[ الموقع - https://example.com ]}</code>\n\n"
        "⬇️ <b>هكذا تظهر الأزرار في الرسالة الفعلية:</b>",
        reply_markup=demo_kb,
    )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):shortcuts$"))
async def panel_shortcuts(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    await cb.message.edit_text(
        "📎 <b>الاختصارات</b>\n\n"
        "<b>اختصارات الأوامر المتاحة في المجموعة:</b>\n\n"
        "• كتم / الغاء كتم\n"
        "• حظر / الغاء حظر\n"
        "• طرد / انذار\n"
        "• مسح / مسح من هنا\n"
        "• اضف رد / حذف رد / ردود\n"
        "• منع [كلمة] / قائمة المنع",
        reply_markup=_kb(back_btn(f"ap:g:{chat_id}:content")),
    )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):edits_log$"))
async def panel_edits_log(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    replies = await db.list_replies(chat_id)
    blacklist = await db.list_blacklist(chat_id)
    g = await db.get_group(chat_id)
    text = (
        "📋 <b>قائمة التعديلات</b>\n\n"
        f"💬 الردود التلقائية: {len(replies)}\n"
        f"🚫 الكلمات الممنوعة: {len(blacklist)}\n"
        f"📜 القوانين: {'محددة' if g.get('rules') else 'لم تحدد'}\n"
        f"👋 رسالة الترحيب: {'محددة' if g.get('welcome_text') else 'لم تحدد'}"
    )
    await cb.message.edit_text(text, reply_markup=_kb(back_btn(f"ap:g:{chat_id}:content")))
    await cb.answer()


@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):edit_content$"))
async def panel_edit_content(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    await cb.message.edit_text(
        "✏️ <b>تعديل المحتوى</b>\n\n"
        "اختر ما تريد تعديله:",
        reply_markup=_kb(
            [_btn("👋 رسالة الترحيب", f"ap:g:{chat_id}:edit_welcome")],
            [_btn("📜 القوانين", f"ap:g:{chat_id}:edit_rules")],
            back_btn(f"ap:g:{chat_id}:content"),
        ),
    )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):deeplinks$"))
async def panel_deeplinks(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    await cb.message.edit_text(
        "🔗 <b>ديب لينك مخصص</b>\n\n"
        "يمكنك إنشاء روابط مخصصة تفتح البوت مباشرة مع رسالة أو أمر محدد.\n\n"
        "مثال على رابط ديب لينك:\n"
        "<code>t.me/Rashid_Help_bot?start=welcome</code>\n\n"
        "⏳ إدارة الديب لينك قيد التطوير.",
        reply_markup=_kb(back_btn(f"ap:g:{chat_id}:content")),
    )
    await cb.answer()


@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):help_page$"))
async def panel_help_page(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    await cb.message.edit_text(
        "❓ <b>المساعدة</b>\n\n"
        "<b>كيف تضيف ردًا تلقائيًا؟</b>\n"
        "اضغط 💬 الردود التلقائية ← ➕ إضافة رد جديد\n\n"
        "<b>كيف تفعّل الترحيب؟</b>\n"
        "اضغط ⚙️ الإعدادات ← اختر مجموعة ← الترحيب\n\n"
        "<b>كيف تمنع كلمة في المجموعة؟</b>\n"
        "أرسل في المجموعة: <code>منع [الكلمة]</code>\n\n"
        "<b>كيف تكتم عضوًا؟</b>\n"
        "رد على رسالته واكتب: <code>كتم</code>\n\n"
        f"للتواصل: {DEVELOPER_CONTACT}",
        reply_markup=_kb(back_btn(f"ap:g:{chat_id}:content")),
    )
    await cb.answer()


# ─── broadcast ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ap:broadcast")
async def panel_broadcast_start(cb: CallbackQuery, state: FSMContext):
    count = await db.count_groups()
    await state.set_state(PanelState.broadcast)
    await cb.message.edit_text(
        f"📢 <b>بث رسالة</b>\n\n"
        f"سيتم إرسال رسالتك إلى <b>{count}</b> مجموعة.\n\n"
        "أرسل الرسالة (نص، صورة، فيديو...) أو /cancel للإلغاء:",
        reply_markup=_kb(back_btn("ap:main")),
    )
    await cb.answer()


@router.message(PanelState.broadcast)
async def panel_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if message.text == "/cancel":
        await state.clear()
        count = await db.count_groups()
        await message.answer("❌ تم الإلغاء.", reply_markup=main_kb(count))
        return
    await state.clear()
    group_ids = await db.all_group_ids()
    sent, failed = 0, 0
    for chat_id in group_ids:
        try:
            await message.copy_to(chat_id)
            sent += 1
        except Exception:
            failed += 1
    count = await db.count_groups()
    await message.answer(
        f"✅ تم البث إلى {sent} مجموعة.\n❌ فشل: {failed}",
        reply_markup=main_kb(count),
    )


# ─── system ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "ap:system")
async def panel_system(cb: CallbackQuery):
    count = await db.count_groups()
    text = (
        "🔧 <b>النظام والدعم</b>\n\n"
        f"📊 المجموعات: {count}\n"
        f"👤 المالك: {DEVELOPER_CONTACT}\n"
        f"🤖 البوت: @Rashid_Help_bot\n\n"
        "<b>أوامر سريعة في المجموعة:</b>\n"
        "• <code>اضف رد</code> ← رد تلقائي جديد\n"
        "• <code>منع [كلمة]</code> ← حظر كلمة\n"
        "• <code>تعيين القوانين [نص]</code>\n"
        "• <code>تعيين الترحيب [نص]</code>"
    )
    await cb.message.edit_text(text, reply_markup=_kb(back_btn("ap:main")))
    await cb.answer()
