from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import db
from bot.config import OWNER_ID

router = Router()
router.message.filter(F.chat.type == "private", F.from_user.id == OWNER_ID)
router.callback_query.filter(F.from_user.id == OWNER_ID)


class Broadcast(StatesGroup):
    waiting_text = State()


def _panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="panel:stats")],
            [InlineKeyboardButton(text="📢 بث رسالة لكل المجموعات", callback_data="panel:broadcast")],
        ]
    )


@router.message(Command("admin"))
async def open_panel(message: Message):
    await message.answer("🎛 لوحة تحكم المساعد رشيد", reply_markup=_panel_keyboard())


@router.callback_query(F.data == "panel:stats")
async def show_stats(callback: CallbackQuery):
    count = await db.count_groups()
    await callback.message.edit_text(
        f"📊 عدد المجموعات التي يعمل فيها البوت: {count}",
        reply_markup=_panel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "panel:broadcast")
async def ask_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Broadcast.waiting_text)
    await callback.message.edit_text("✍️ أرسل الآن الرسالة التي تريد بثها لجميع المجموعات.")
    await callback.answer()


@router.message(Broadcast.waiting_text)
async def do_broadcast(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    group_ids = await db.all_group_ids()
    sent, failed = 0, 0
    for chat_id in group_ids:
        try:
            await message.copy_to(chat_id)
            sent += 1
        except TelegramForbiddenError:
            failed += 1
        except Exception:
            failed += 1
    await message.answer(f"✅ تم البث إلى {sent} مجموعة. (فشل: {failed})")
