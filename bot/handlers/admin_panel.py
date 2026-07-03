import time

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


class PanelState(StatesGroup):
    broadcast = State()
    edit_welcome = State()
    edit_rules = State()
    edit_bot_info = State()
    _pending_chat = State()


# ─── keyboard builders ────────────────────────────────────────────────────────

def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def main_kb(group_count: int) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("⚙️ الإعدادات", "ap:settings"), _btn("📝 المحتوى", "ap:content")],
        [_btn("👥 المجموعات", "ap:groups"), _btn("📢 بث رسالة", "ap:broadcast")],
        [_btn("🔧 النظام والدعم", "ap:system")],
    )


def back_btn(dest: str = "ap:main") -> list[InlineKeyboardButton]:
    return [_btn("◀️ رجوع", dest)]


def groups_kb(groups: list[dict], back: str = "ap:main") -> InlineKeyboardMarkup:
    rows = []
    for g in groups:
        title = (g.get("title") or str(g["chat_id"]))[:30]
        rows.append([_btn(f"🏘 {title}", f"ap:g:{g['chat_id']}")])
    rows.append(back_btn(back))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_menu_kb(chat_id: int) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("⚙️ الإعدادات", f"ap:g:{chat_id}:settings")],
        [_btn("📝 المحتوى", f"ap:g:{chat_id}:content")],
        [_btn("📊 إحصائيات", f"ap:g:{chat_id}:stats")],
        back_btn("ap:groups"),
    )


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


def group_content_kb(chat_id: int, replies_count: int) -> InlineKeyboardMarkup:
    return _kb(
        [_btn("👋 رسالة الترحيب", f"ap:g:{chat_id}:edit_welcome")],
        [_btn(f"💬 الردود التلقائية ({replies_count})", f"ap:g:{chat_id}:replies")],
        [_btn("🚫 الكلمات الممنوعة", f"ap:g:{chat_id}:blacklist")],
        back_btn(f"ap:g:{chat_id}"),
    )


# ─── helpers ──────────────────────────────────────────────────────────────────

async def _all_groups() -> list[dict]:
    ids = await db.all_group_ids()
    groups = []
    for cid in ids:
        g = await db.get_group(cid)
        groups.append(g)
    return groups


async def _edit_or_send(target, text: str, kb: InlineKeyboardMarkup):
    """Edit existing message or send new one."""
    try:
        await target.message.edit_text(text, reply_markup=kb)
    except (AttributeError, TelegramBadRequest):
        await target.answer(text, reply_markup=kb)


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


# ─── main menu ────────────────────────────────────────────────────────────────

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


# ─── settings: pick a group ───────────────────────────────────────────────────

@router.callback_query(F.data == "ap:settings")
async def panel_settings(cb: CallbackQuery):
    groups = await _all_groups()
    if not groups:
        await cb.answer("لا توجد مجموعات مسجّلة بعد.", show_alert=True)
        return
    await cb.message.edit_text(
        "⚙️ <b>الإعدادات</b>\n\nاختر المجموعة التي تريد ضبط إعداداتها:",
        reply_markup=groups_kb(groups, back="ap:main"),
    )
    await cb.answer()


# ─── content: pick a group ────────────────────────────────────────────────────

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
    count = len(groups)
    if not groups:
        await cb.answer("لا توجد مجموعات مسجّلة بعد.", show_alert=True)
        return
    await cb.message.edit_text(
        f"👥 <b>المجموعات</b> ({count})\n\nاختر مجموعة لإدارتها:",
        reply_markup=groups_kb(groups, back="ap:main"),
    )
    await cb.answer()


# ─── group main submenu ───────────────────────────────────────────────────────

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
    current = g.get(field, 0)
    new_val = 0 if current else 1
    await db.set_group_field(chat_id, field, new_val)
    g[field] = new_val

    # Apply lock/unlock immediately via Telegram API
    if field == "locked":
        from bot.handlers.moderation import FULL_PERMISSIONS, NO_PERMISSIONS
        try:
            perms = NO_PERMISSIONS if new_val else FULL_PERMISSIONS
            await bot.set_chat_permissions(chat_id, permissions=perms)
        except TelegramBadRequest:
            pass

    title = g.get("title") or str(chat_id)
    status = "✅ مفعّل" if new_val else "🔴 معطّل"
    await cb.answer(f"{status}", show_alert=False)
    await cb.message.edit_text(
        f"⚙️ <b>إعدادات: {title}</b>\n\nاضغط على أي خيار لتفعيله أو تعطيله:",
        reply_markup=group_settings_kb(chat_id, g),
    )


# ─── group content ────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):content$"))
async def panel_group_content(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    g = await db.get_group(chat_id)
    replies = await db.list_replies(chat_id)
    title = g.get("title") or str(chat_id)
    await cb.message.edit_text(
        f"📝 <b>محتوى: {title}</b>",
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
    await cb.message.edit_text(
        text,
        reply_markup=_kb(back_btn(f"ap:g:{chat_id}")),
    )
    await cb.answer()


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
        "أرسل الرسالة الجديدة (يمكنك استخدام {user} لاسم العضو و {chat} لاسم المجموعة):\n\n"
        "أو أرسل /cancel للإلغاء.",
        reply_markup=_kb(back_btn(f"ap:g:{chat_id}:content")),
    )
    await cb.answer()


@router.message(PanelState.edit_welcome, F.text)
async def panel_edit_welcome_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ تم الإلغاء.", reply_markup=None)
        return
    data = await state.get_data()
    chat_id = data["chat_id"]
    await db.set_group_field(chat_id, "welcome_text", message.text)
    await db.set_group_field(chat_id, "welcome_enabled", 1)
    await state.clear()
    g = await db.get_group(chat_id)
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
        "أرسل القوانين الجديدة أو /cancel للإلغاء:",
        reply_markup=_kb(back_btn(f"ap:g:{chat_id}:settings")),
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
    await message.answer(
        "✅ تم حفظ القوانين.",
        reply_markup=group_settings_kb(chat_id, g),
    )


# ─── replies list ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):replies$"))
async def panel_group_replies(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    replies = await db.list_replies(chat_id)
    if not replies:
        text = "💬 لا توجد ردود تلقائية في هذه المجموعة.\n\nأرسل <b>اضف رد</b> داخل المجموعة لإضافة رد جديد."
    else:
        lines = [f"{i}. {r['triggers'].replace('|', ' / ')}" for i, r in enumerate(replies, 1)]
        text = "💬 <b>الردود التلقائية:</b>\n\n" + "\n".join(lines)
    await cb.message.edit_text(
        text,
        reply_markup=_kb(back_btn(f"ap:g:{chat_id}:content")),
    )
    await cb.answer()


# ─── blacklist view ───────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^ap:g:(-?\d+):blacklist$"))
async def panel_group_blacklist(cb: CallbackQuery):
    chat_id = int(cb.data.split(":")[2])
    words = await db.list_blacklist(chat_id)
    if not words:
        text = "🚫 لا توجد كلمات ممنوعة.\n\nأرسل <b>منع [كلمة]</b> داخل المجموعة لإضافة كلمة."
    else:
        text = "🚫 <b>الكلمات الممنوعة:</b>\n\n" + "\n".join(f"• {w}" for w in words)
    await cb.message.edit_text(
        text,
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
        "أرسل الرسالة الآن (نص أو صورة أو فيديو...) أو /cancel للإلغاء:",
        reply_markup=_kb(back_btn("ap:main")),
    )
    await cb.answer()


@router.message(PanelState.broadcast)
async def panel_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if message.text == "/cancel":
        await state.clear()
        count = await db.count_groups()
        await message.answer(
            "❌ تم الإلغاء.",
            reply_markup=main_kb(count),
        )
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
        "<b>أوامر مفيدة في المجموعات:</b>\n"
        "• <code>اضف رد</code> ← إضافة رد تلقائي\n"
        "• <code>منع [كلمة]</code> ← حظر كلمة\n"
        "• <code>تعيين القوانين [النص]</code> ← تعيين القوانين\n"
        "• <code>تعيين الترحيب [النص]</code> ← تعيين الترحيب"
    )
    await cb.message.edit_text(text, reply_markup=_kb(back_btn("ap:main")))
    await cb.answer()
