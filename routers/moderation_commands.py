import re
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatPermissions
from aiogram.filters import Command, CommandObject
from aiogram.exceptions import TelegramBadRequest

from database import (
    is_admin,
    add_warning,
    remove_warning,
    get_warnings_count,
    add_punishment,
    remove_punishment,
    get_active_punishments,
    cleanup_expired_punishments,
    get_user_nickname
)
from routers.utils import resolve_user_id, extract_user_from_text, get_user_display_name
import logging

logger = logging.getLogger(__name__)

moderation_router = Router()

async def moderator_filter(message: Message) -> bool:
    """Проверяет, является ли пользователь модератором (админ в БД или админ в чате)."""
    if await is_admin(message.from_user.id):
        return True
    
    try:
        member = await message.chat.get_member(message.from_user.id)
        if member.status in ["administrator", "creator"]:
            return True
    except Exception as e:
        logger.error(f"Error checking moderator permissions: {e}")
    
    return False

moderation_router.message.filter(F.chat.type.in_(["group", "supergroup"]), moderator_filter)

@moderation_router.message(Command("бан"))
@moderation_router.message(F.text.lower().startswith("бан"))
async def ban_command(message: Message, bot: Bot, command: CommandObject = None):
    # Извлекаем пользователя
    target_user_id = await resolve_user_id(message)
    
    if not target_user_id:
        await message.reply(
            "❌ Укажите гражданина для бана:\n"
            "• Ответьте на сообщение\n"
            "• Используйте @username\n"
            "• Укажите ID"
        )
        return

    if target_user_id == message.from_user.id:
        await message.reply("❌ Вы не можете забанить самого себя!")
        return

    # Извлекаем причину
    reason = "Не указана"
    if command and command.args:
        # Если есть аргументы, первый может быть юзернеймом/айди, остальные - причина
        parts = command.args.split(maxsplit=1)
        if len(parts) > 1:
            reason = parts[1]
    elif not message.reply_to_message:
        # Если не реплай и не CommandObject args, попробуем из текста
        parts = message.text.split(maxsplit=2)
        if len(parts) > 2:
            reason = parts[2]

    try:
        await message.chat.ban(user_id=target_user_id)
        
        await add_punishment(target_user_id, message.chat.id, "ban", reason, message.from_user.id)
        
        target_name = await get_user_display_name(target_user_id)
        await message.reply(
            f"✅ Гражданин {target_name} забанен!\n"
            f"📝 Причина: {reason}\n"
            f"👮 Модератор: {message.from_user.first_name}"
        )
    except Exception as e:
        logger.error(f"Error banning user {target_user_id}: {e}")
        await message.reply(f"❌ Ошибка: {str(e)}")

@moderation_router.message(Command("разбан"))
async def unban_command(message: Message, bot: Bot):
    target_user_id = await resolve_user_id(message)
    
    if not target_user_id:
        await message.reply("❌ Укажите гражданина для разбана.")
        return

    try:
        await message.chat.unban(user_id=target_user_id)
        await remove_punishment(target_user_id, message.chat.id, "ban", message.from_user.id)
        
        target_name = await get_user_display_name(target_user_id)
        await message.reply(f"✅ Гражданин {target_name} разбанен!")
    except Exception as e:
        logger.error(f"Error unbanning user {target_user_id}: {e}")
        await message.reply(f"❌ Ошибка: {str(e)}")

@moderation_router.message(Command("мут"))
async def mute_command(message: Message, bot: Bot, command: CommandObject = None):
    target_user_id = await resolve_user_id(message)
    
    if not target_user_id:
        await message.reply("❌ Укажите гражданина для мута.")
        return

    if target_user_id == message.from_user.id:
        await message.reply("❌ Вы не можете замутить самого себя!")
        return

    duration_minutes = None
    reason = "Не указана"

    if command and command.args:
        parts = command.args.split()
        # Ищем число (минуты) в конце или середине
        for part in parts:
            if part.isdigit():
                duration_minutes = int(part)
                break
        # Остальное - причина (упрощенно)
        reason = command.args

    until_date = None
    if duration_minutes:
        until_date = datetime.now() + timedelta(minutes=duration_minutes)

    try:
        await message.chat.restrict(
            user_id=target_user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        
        await add_punishment(target_user_id, message.chat.id, "mute", reason, message.from_user.id, duration_minutes)
        
        target_name = await get_user_display_name(target_user_id)
        dur_text = f"на {duration_minutes} мин." if duration_minutes else "перманентно"
        await message.reply(f"✅ Гражданин {target_name} замучен {dur_text}!")
    except Exception as e:
        logger.error(f"Error muting user {target_user_id}: {e}")
        await message.reply(f"❌ Ошибка: {str(e)}")

@moderation_router.message(Command("размут"))
async def unmute_command(message: Message, bot: Bot):
    target_user_id = await resolve_user_id(message)
    
    if not target_user_id:
        await message.reply("❌ Укажите гражданина для размута.")
        return

    try:
        await message.chat.restrict(
            user_id=target_user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await remove_punishment(target_user_id, message.chat.id, "mute", message.from_user.id)
        
        target_name = await get_user_display_name(target_user_id)
        await message.reply(f"✅ Гражданин {target_name} размучен!")
    except Exception as e:
        logger.error(f"Error unmuting user {target_user_id}: {e}")
        await message.reply(f"❌ Ошибка: {str(e)}")

@moderation_router.message(Command("варн"))
async def warn_command(message: Message, bot: Bot, command: CommandObject = None):
    target_user_id = await resolve_user_id(message)
    
    if not target_user_id:
        await message.reply("❌ Укажите гражданина для предупреждения.")
        return

    reason = command.args if command and command.args else "Не указана"
    
    if await add_warning(target_user_id, message.chat.id, reason, message.from_user.id):
        target_name = await get_user_display_name(target_user_id)
        count = await get_warnings_count(target_user_id, message.chat.id)
        await message.reply(f"⚠️ Гражданину {target_name} выдано предупреждение ({count}).")
    else:
        await message.reply("❌ Ошибка при выдаче предупреждения.")

@moderation_router.message(Command("снять_варн"))
async def unwarn_command(message: Message, bot: Bot):
    target_user_id = await resolve_user_id(message)
    
    if not target_user_id:
        await message.reply("❌ Укажите гражданина.")
        return

    if await remove_warning(target_user_id, message.chat.id, message.from_user.id):
        target_name = await get_user_display_name(target_user_id)
        count = await get_warnings_count(target_user_id, message.chat.id)
        await message.reply(f"✅ С гражданина {target_name} снято предупреждение. Осталось: {count}")
    else:
        await message.reply("❌ У гражданина нет предупреждений.")

@moderation_router.message(Command("наказания"))
async def punishments_command(message: Message, bot: Bot):
    target_user_id = await resolve_user_id(message)
    
    if not target_user_id:
        await message.reply("❌ Укажите гражданина.")
        return

    punishments = await get_active_punishments(target_user_id, message.chat.id)
    warnings_count = await get_warnings_count(target_user_id, message.chat.id)
    target_name = await get_user_display_name(target_user_id)

    if not punishments and warnings_count == 0:
        await message.reply(f"📋 Гражданин {target_name} чист.")
        return

    res = f"📋 Наказания {target_name}:\n"
    if warnings_count > 0:
        res += f"⚠️ Предупреждений: {warnings_count}\n"
    
    for p in punishments:
        ptype = "Бан" if p['type'] == 'ban' else "Мут"
        exp = f"до {p['expires_at'][:16]}" if p['expires_at'] else "перм."
        res += f"• {ptype} ({exp}): {p['reason']}\n"
    
    await message.reply(res)

async def cleanup_expired_punishments_task():
    """Фоновая задача для автоматического снятия истекших наказаний."""
    while True:
        try:
            cleaned = await cleanup_expired_punishments()
            if cleaned > 0:
                logger.info(f"Automatically removed {cleaned} expired punishments.")
        except Exception as e:
            logger.error(f"Error in cleanup_expired_punishments_task: {e}")
        await asyncio.sleep(300)