import time

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions, Message

from bot import db
from bot.config import MAX_WARNS_BEFORE_MUTE
from bot.filters import IsGroupAdmin, IsGroupChat
from bot.utils import format_remaining, mention, parse_duration, split_target_and_rest, strip_command

router = Router()
router.message.filter(IsGroupChat())

NO_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_polls=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)


@router.message(F.text.regexp(r"^(كتم|/كتم)(\s|$)"), IsGroupAdmin())
async def cmd_mute(message: Message, bot: Bot):
    target, rest = await split_target_and_rest(message, bot, strip_command(message.text))
    if not target:
        await message.reply("⚠️ حدد العضو بالرد على رسالته أو بذكر يوزره/آيديه.")
        return
    seconds = parse_duration(rest) if rest else None
    until = int(time.time()) + seconds if seconds else 0
    try:
        await bot.restrict_chat_member(
            message.chat.id, target.id, permissions=NO_PERMISSIONS,
            until_date=until or None,
        )
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر كتم العضو: {e.message}")
        return
    await db.record_mute(message.chat.id, target.id, until, reason="")
    duration_text = f" لمدة {format_remaining(int(time.time()) + seconds)}" if seconds else " بشكل دائم"
    await message.reply(f"🔇 تم كتم {mention(target)}{duration_text}.")


@router.message(F.text.regexp(r"^(الغاء كتم|إلغاء كتم|الغاءالكتم|/unmute)(\s|$)"), IsGroupAdmin())
async def cmd_unmute(message: Message, bot: Bot):
    target, _ = await split_target_and_rest(message, bot, strip_command(message.text))
    if not target:
        await message.reply("⚠️ حدد العضو بالرد على رسالته أو بذكر يوزره/آيديه.")
        return
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=FULL_PERMISSIONS)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر إلغاء الكتم: {e.message}")
        return
    await db.remove_mute_record(message.chat.id, target.id)
    await message.reply(f"🔊 تم إلغاء الكتم عن {mention(target)}.")


@router.message(F.text.regexp(r"^(حظر|/حظر|/ban)(\s|$)"), IsGroupAdmin())
async def cmd_ban(message: Message, bot: Bot):
    target, _ = await split_target_and_rest(message, bot, strip_command(message.text))
    if not target:
        await message.reply("⚠️ حدد العضو بالرد على رسالته أو بذكر يوزره/آيديه.")
        return
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر حظر العضو: {e.message}")
        return
    await db.record_ban(message.chat.id, target.id)
    await message.reply(f"🚫 تم حظر {mention(target)}.")


@router.message(F.text.regexp(r"^(الغاء حظر|إلغاء حظر|الغاءالحظر|/unban)(\s|$)"), IsGroupAdmin())
async def cmd_unban(message: Message, bot: Bot):
    target, _ = await split_target_and_rest(message, bot, strip_command(message.text))
    if not target:
        await message.reply("⚠️ حدد العضو بالرد على رسالته أو بذكر يوزره/آيديه.")
        return
    try:
        await bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر إلغاء الحظر: {e.message}")
        return
    await db.remove_ban_record(message.chat.id, target.id)
    await message.reply(f"✅ تم إلغاء الحظر عن {mention(target)}.")


@router.message(F.text.regexp(r"^(طرد|/طرد|/kick)(\s|$)"), IsGroupAdmin())
async def cmd_kick(message: Message, bot: Bot):
    target, _ = await split_target_and_rest(message, bot, strip_command(message.text))
    if not target:
        await message.reply("⚠️ حدد العضو بالرد على رسالته أو بذكر يوزره/آيديه.")
        return
    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر طرد العضو: {e.message}")
        return
    await message.reply(f"👋 تم طرد {mention(target)} (يمكنه العودة بدعوة جديدة).")


@router.message(F.text.regexp(r"^(انذار|إنذار|/انذار|/warn)(\s|$)"), IsGroupAdmin())
async def cmd_warn(message: Message, bot: Bot):
    target, _ = await split_target_and_rest(message, bot, strip_command(message.text))
    if not target:
        await message.reply("⚠️ حدد العضو بالرد على رسالته أو بذكر يوزره/آيديه.")
        return
    count = await db.add_warn(message.chat.id, target.id)
    if count >= MAX_WARNS_BEFORE_MUTE:
        try:
            await bot.restrict_chat_member(message.chat.id, target.id, permissions=NO_PERMISSIONS)
        except TelegramBadRequest:
            pass
        await message.reply(
            f"⚠️ {mention(target)} وصل إلى {count} إنذارات وتم كتمه تلقائيًا."
        )
    else:
        await message.reply(f"⚠️ تم إعطاء {mention(target)} إنذار ({count}/{MAX_WARNS_BEFORE_MUTE}).")


@router.message(F.text.regexp(r"^(الغاء الانذار|إلغاء الانذار|الغاءالانذار|/unwarn)(\s|$)"), IsGroupAdmin())
async def cmd_unwarn(message: Message, bot: Bot):
    target, _ = await split_target_and_rest(message, bot, strip_command(message.text))
    if not target:
        await message.reply("⚠️ حدد العضو بالرد على رسالته أو بذكر يوزره/آيديه.")
        return
    count = await db.remove_warn(message.chat.id, target.id)
    await message.reply(f"✅ تم حذف إنذار عن {mention(target)} (المتبقي: {count}).")


@router.message(F.text.regexp(r"^(حذف الانذارات|الانذارات|/clearwarns)(\s|$)"), IsGroupAdmin())
async def cmd_clear_warns(message: Message, bot: Bot):
    target, _ = await split_target_and_rest(message, bot, strip_command(message.text))
    if not target:
        await message.reply("⚠️ حدد العضو بالرد على رسالته أو بذكر يوزره/آيديه.")
        return
    await db.clear_warns(message.chat.id, target.id)
    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=FULL_PERMISSIONS)
    except TelegramBadRequest:
        pass
    await message.reply(f"✅ تم حذف جميع الإنذارات عن {mention(target)} وإلغاء أي تقييد.")


@router.message(F.text.regexp(r"^(حذف وحظر)(\s|$)"), IsGroupAdmin())
async def cmd_delete_and_ban(message: Message, bot: Bot):
    if not message.reply_to_message:
        await message.reply("⚠️ استخدم هذا الأمر بالرد على رسالة العضو.")
        return
    target = message.reply_to_message.from_user
    try:
        await message.reply_to_message.delete()
        await bot.ban_chat_member(message.chat.id, target.id)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر تنفيذ الأمر: {e.message}")
        return
    await db.record_ban(message.chat.id, target.id)
    await message.reply(f"🚫 تم حذف الرسالة وحظر {mention(target)}.")
    await message.delete()


@router.message(F.text.regexp(r"^(حذف وكتم)(\s|$)"), IsGroupAdmin())
async def cmd_delete_and_mute(message: Message, bot: Bot):
    if not message.reply_to_message:
        await message.reply("⚠️ استخدم هذا الأمر بالرد على رسالة العضو.")
        return
    target = message.reply_to_message.from_user
    try:
        await message.reply_to_message.delete()
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=NO_PERMISSIONS)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر تنفيذ الأمر: {e.message}")
        return
    await db.record_mute(message.chat.id, target.id, 0)
    await message.reply(f"🔇 تم حذف الرسالة وكتم {mention(target)}.")
    await message.delete()


@router.message(F.text.regexp(r"^(تحذير)(\s|$)"), IsGroupAdmin())
async def cmd_warn_and_delete(message: Message, bot: Bot):
    if not message.reply_to_message:
        await message.reply("⚠️ استخدم هذا الأمر بالرد على رسالة العضو.")
        return
    target = message.reply_to_message.from_user
    try:
        await message.reply_to_message.delete()
    except TelegramBadRequest:
        pass
    count = await db.add_warn(message.chat.id, target.id)
    if count >= MAX_WARNS_BEFORE_MUTE:
        try:
            await bot.restrict_chat_member(message.chat.id, target.id, permissions=NO_PERMISSIONS)
        except TelegramBadRequest:
            pass
        await message.reply(f"⚠️ تم حذف الرسالة، و{mention(target)} وصل {count} إنذارات وتم كتمه.")
    else:
        await message.reply(f"⚠️ تم حذف الرسالة وإعطاء {mention(target)} إنذار ({count}/{MAX_WARNS_BEFORE_MUTE}).")


@router.message(F.text.regexp(r"^(مسح من هنا)$"), IsGroupAdmin())
async def cmd_purge(message: Message, bot: Bot):
    if not message.reply_to_message:
        await message.reply("⚠️ رد على أول رسالة تريد الحذف من عندها.")
        return
    start_id = message.reply_to_message.message_id
    end_id = message.message_id
    ids = list(range(start_id, end_id + 1))
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            await bot.delete_messages(message.chat.id, chunk)
        except TelegramBadRequest:
            for mid in chunk:
                try:
                    await bot.delete_message(message.chat.id, mid)
                except TelegramBadRequest:
                    pass


@router.message(F.text.regexp(r"^(مسح \d+)$"), IsGroupAdmin())
async def cmd_purge_n(message: Message, bot: Bot):
    n = int(message.text.split()[1])
    n = min(n, 200)
    ids = list(range(message.message_id - n, message.message_id + 1))
    try:
        await bot.delete_messages(message.chat.id, ids)
    except TelegramBadRequest:
        for mid in ids:
            try:
                await bot.delete_message(message.chat.id, mid)
            except TelegramBadRequest:
                pass


@router.message(F.text.regexp(r"^(مسح|/مسح|/del)$"), IsGroupAdmin())
async def cmd_delete(message: Message, bot: Bot):
    if not message.reply_to_message:
        await message.reply("⚠️ استخدم هذا الأمر بالرد على الرسالة المراد حذفها.")
        return
    try:
        await message.reply_to_message.delete()
        await message.delete()
    except TelegramBadRequest:
        pass


@router.message(F.text.regexp(r"^(تثبيت|ثبت|/تثبيت|/pin)(\s|$)"), IsGroupAdmin())
async def cmd_pin(message: Message, bot: Bot):
    if not message.reply_to_message:
        await message.reply("⚠️ رد على الرسالة المراد تثبيتها.")
        return
    notify = message.text.strip().endswith("!")
    try:
        await bot.pin_chat_message(
            message.chat.id, message.reply_to_message.message_id,
            disable_notification=not notify,
        )
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر التثبيت: {e.message}")
        return
    await message.reply("📌 تم تثبيت الرسالة.")


@router.message(F.text.regexp(r"^(حتثبيت|الغاء تثبيت|/unpin)(\s|$)"), IsGroupAdmin())
async def cmd_unpin(message: Message, bot: Bot):
    try:
        if message.reply_to_message:
            await bot.unpin_chat_message(message.chat.id, message.reply_to_message.message_id)
        else:
            await bot.unpin_chat_message(message.chat.id)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر إلغاء التثبيت: {e.message}")
        return
    await message.reply("📌 تم إلغاء تثبيت الرسالة.")


@router.message(F.text.regexp(r"^(اغلاق|قفل|/اغلاق|/lock)$"), IsGroupAdmin())
async def cmd_lock(message: Message, bot: Bot):
    try:
        await bot.set_chat_permissions(message.chat.id, permissions=NO_PERMISSIONS)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر إغلاق المناقشة: {e.message}")
        return
    await db.set_group_field(message.chat.id, "locked", 1)
    await message.reply("🔒 تم إغلاق المناقشة في المجموعة، المشرفون فقط يمكنهم الكتابة.")


@router.message(F.text.regexp(r"^(فتح|/فتح|/unlock)$"), IsGroupAdmin())
async def cmd_unlock(message: Message, bot: Bot):
    try:
        await bot.set_chat_permissions(message.chat.id, permissions=FULL_PERMISSIONS)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر فتح المناقشة: {e.message}")
        return
    await db.set_group_field(message.chat.id, "locked", 0)
    await message.reply("🔓 تم فتح المناقشة في المجموعة.")


@router.message(F.text.regexp(r"^(رابط|/رابط|/link)$"))
async def cmd_link(message: Message, bot: Bot):
    try:
        link = await bot.export_chat_invite_link(message.chat.id)
    except TelegramBadRequest as e:
        await message.reply(f"❌ تعذر جلب رابط المجموعة: {e.message}")
        return
    await message.reply(f"🔗 رابط المجموعة:\n{link}")


@router.message(F.text.regexp(r"^(معلومات|عرض|كشف|/معلومات|/info)(\s|$)"))
async def cmd_info(message: Message, bot: Bot):
    target, _ = await split_target_and_rest(message, bot, strip_command(message.text))
    target = target or message.from_user
    warns = await db.get_warns(message.chat.id, target.id)
    try:
        member = await bot.get_chat_member(message.chat.id, target.id)
        status = member.status
    except TelegramBadRequest:
        status = "غير معروف"
    text = (
        f"👤 معلومات العضو\n"
        f"الاسم: {mention(target)}\n"
        f"الآيدي: <code>{target.id}</code>\n"
        f"اليوزر: @{target.username if target.username else 'لا يوجد'}\n"
        f"الحالة: {status}\n"
        f"عدد الإنذارات: {warns}"
    )
    await message.reply(text)


@router.message(F.text.regexp(r"^(القوانين|/القوانين|/rules)$"))
async def cmd_rules(message: Message):
    group = await db.get_group(message.chat.id)
    rules = group.get("rules") or "لا توجد قوانين مضافة لهذه المجموعة بعد."
    await message.reply(f"📜 قوانين المجموعة:\n\n{rules}")


@router.message(F.text.regexp(r"^(تعيين القوانين)(\s+)"), IsGroupAdmin())
async def cmd_set_rules(message: Message):
    rules_text = strip_command(message.text)
    await db.set_group_field(message.chat.id, "rules", rules_text)
    await message.reply("✅ تم تحديث قوانين المجموعة.")


@router.message(F.text.regexp(r"^(المطور|/المطور)$"))
async def cmd_developer(message: Message):
    from bot.config import DEVELOPER_CONTACT

    await message.reply(f"🤖 بوت المساعد رشيد\nالمطور: {DEVELOPER_CONTACT}")
