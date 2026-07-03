from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot import db
from bot.config import OWNER_ID

router = Router()

HELP_TEXT = """
🤖 <b>المساعد رشيد - بوت حماية المجموعات</b>

<b>أوامر الإدارة (رد على رسالة العضو أو اذكر يوزره/آيديه):</b>
كتم | الغاء كتم | حظر | الغاء حظر | طرد
انذار | الغاء الانذار | حذف الانذارات
حذف وحظر | حذف وكتم | تحذير

<b>أوامر الرسائل:</b>
مسح (رد على رسالة) | مسح [عدد] | مسح من هنا
تثبيت | تثبيت! | حتثبيت

<b>إدارة المجموعة:</b>
اغلاق | فتح | رابط | القوانين | تعيين القوانين [النص]
المطور | معلومات | عرض

<b>الحماية من السبام:</b>
منع [كلمة] | قائمة المنع | الغاء منع [كلمة] | مسح قائمة المنع
تفعيل منع الروابط | ايقاف منع الروابط
المحظورين | المقيدين

<b>الترحيب:</b>
تفعيل الترحيب | ايقاف الترحيب | تعيين الترحيب [النص]

<b>نظام الردود التلقائية:</b>
اضف رد | حذف رد | ردود

أضفني كمشرف بكامل الصلاحيات في مجموعتك لأبدأ بحمايتها 🛡
"""


@router.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type == "private":
        if message.from_user and message.from_user.id == OWNER_ID:
            # Owner sees the admin panel directly
            count = await db.count_groups()
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ الإعدادات", callback_data="ap:settings"),
                 InlineKeyboardButton(text="📝 المحتوى", callback_data="ap:content")],
                [InlineKeyboardButton(text="👥 المجموعات", callback_data="ap:groups"),
                 InlineKeyboardButton(text="📢 بث رسالة", callback_data="ap:broadcast")],
                [InlineKeyboardButton(text="🔧 النظام والدعم", callback_data="ap:system")],
            ])
            await message.answer(
                f"👋 أهلاً <b>رشيد</b>!\n\n"
                f"🤖 <b>المساعد رشيد</b> جاهز\n"
                f"📊 المجموعات النشطة: <b>{count}</b>\n\n"
                "اختر من لوحة التحكم:",
                reply_markup=kb,
            )
        else:
            await message.answer(
                "👋 أهلاً بك!\n\n"
                "أنا <b>المساعد رشيد</b>، بوت حماية المجموعات.\n"
                "أضفني إلى مجموعتك وارفعني مشرفًا لأبدأ الحماية.\n\n"
                "أرسل /help لرؤية كل الأوامر."
            )
    else:
        await db.ensure_group(message.chat.id, message.chat.title or "")
        await message.answer("👋 المساعد رشيد جاهز لحماية هذه المجموعة. 🛡")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)


@router.message(Command("id"))
async def cmd_id(message: Message):
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    await message.answer(f"🆔 الآيدي: <code>{target.id}</code>")
