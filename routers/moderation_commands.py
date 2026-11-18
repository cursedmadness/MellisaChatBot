import re
import asyncio
from datetime import datetime, timedelta, timezone
from html import escape
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
    get_user_nickname,
    reset_user_rating,
    get_user_rate,
    update_user_rate,
    get_all_banned_users,
    get_last_punishment_details,
    get_users_by_rate_range
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
        if member.status == "creator":
            return True
        if member.status == "administrator":
            return bool(member.can_restrict_members)
    except Exception as e:
        logger.error(f"Ошибка проверки прав модератора: {e}")
    
    return False

def parse_moderation_args(message: Message, command: CommandObject | None,
                          target_user_id: int) -> tuple[int | None, str]:
    """Отделяет цель команды от срока: отдельное число — это минуты."""
    if command:
        text = command.args or ""
    else:
        parts = (message.text or "").split(maxsplit=1)
        text = parts[1] if len(parts) > 1 else ""
    parts = text.strip().split(maxsplit=1)
    if parts:
        target = parts[0]
        is_mention = target.startswith(("@", "t.me/", "https://t.me/", "http://t.me/"))
        is_id = (not message.reply_to_message and target.isdigit()
                 and int(target) == target_user_id)
        if is_mention or is_id:
            text = parts[1] if len(parts) > 1 else ""
    pattern = r"(?i)(?<!\w)(\d+)\s*(мин\w*|час\w*|дн\w*|день|дней|нед\w*)\b|\b(час)\b"
    match = re.search(pattern, text)
    duration = None
    if match:
        if match.group(3):
            duration = 60
        else:
            value, unit = int(match.group(1)), match.group(2).lower()
            factor = 1 if unit.startswith("мин") else 60 if unit.startswith("час") else 10080 if unit.startswith("нед") else 1440
            duration = value * factor
    else:
        match = re.search(r"(?<!\S)\d+(?!\S)", text)
        if match:
            duration = int(match.group())
    if duration is not None and not 1 <= duration <= 366 * 24 * 60:
        raise ValueError("Срок наказания должен быть от 1 минуты до 366 дней.")
    if match:
        text = text[:match.start()] + text[match.end():]
    return duration, text.strip() or "Не указана"



@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, Command("бан"))
@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, F.text.lower().regexp(r"^бан(\s|$)"))
async def ban_command(message: Message, bot: Bot, command: CommandObject = None) -> None:
    try:
        # Извлекаем пользователя
        target_user_id = await resolve_user_id(message)
        
        if not target_user_id:
            await message.reply(
                "📵 Гражданин должен быть указан через @username или его сообщение для проведения процедуры исправительного перевоспитания."
            )
            return

        if target_user_id == message.from_user.id:
            await message.reply("❌ Партия не одобряет самовыпил.")
            return

        try:
            duration_minutes, reason = parse_moderation_args(message, command, target_user_id)
        except ValueError as e:
            await message.reply(f"❌ {escape(str(e))}")
            return

        until_date_obj = None
        if duration_minutes:
            until_date_obj = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

        try:
            await message.chat.ban(user_id=target_user_id, until_date=until_date_obj)
            
            await add_punishment(target_user_id, message.chat.id, "ban", reason, message.from_user.id, duration_minutes)
            
            # Сброс рейтинга при бане
            await reset_user_rating(target_user_id)
            
            target_name = await get_user_display_name(target_user_id)
            
            if duration_minutes:
                if duration_minutes >= 1440 and duration_minutes % 1440 == 0:
                    d = duration_minutes // 1440
                    until_date = f"{d} дн."
                elif duration_minutes >= 60 and duration_minutes % 60 == 0:
                    h = duration_minutes // 60
                    if h == 1:
                        until_date = "1 час"
                    elif h % 10 == 1 and h % 100 != 11:
                        until_date = f"{h} час"
                    elif 2 <= h % 10 <= 4 and (h % 100 < 10 or h % 100 >= 20):
                        until_date = f"{h} часа"
                    else:
                        until_date = f"{h} часов"
                else:
                    m = duration_minutes
                    if m % 10 == 1 and m % 100 != 11:
                        until_date = f"{m} минуту"
                    elif 2 <= m % 10 <= 4 and (m % 100 < 10 or m % 100 >= 20):
                        until_date = f"{m} минуты"
                    else:
                        until_date = f"{m} минут"
            else:
                until_date = "окончания блокировки"
            
            await message.reply(
                f"🌲 Смотритель {escape(str(message.from_user.first_name))} заблокировал гражданина {target_name}\n"
                f"Воля партии – исправительное перевоспитание.\n"
                f"Дождитесь {until_date} и приходите ещё!"
            )
            
            # Уведомление в ЛС
            try:
                await bot.send_message(
                    target_user_id,
                    f"🌲Смотритель {escape(str(message.from_user.first_name))} заблокировал гражданина {target_name}\n"
                    f"Воля партии – исправительное перевоспитание.\n"
                    f"Дождитесь {until_date} и приходите ещё!"
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Ошибка бана гражданина {target_user_id}: {e}")
            await message.reply(f"❌ Ошибка: {escape(str(e))}")
    except Exception as e:
        logger.error(f"Глобальная ошибка в ban_command: {e}")
        await message.answer("Произошла ошибка при выполнении команды бана.")


@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, Command("разбан"))
@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, F.text.lower().startswith("разбан"))
async def unban_command(message: Message, bot: Bot) -> None:
    """
    Разбанивает пользователя в чате и удаляет запись о бане из БД.
    """
    try:
        target_user_id = await resolve_user_id(message)
        
        if not target_user_id:
            await message.reply(
                "📵 Гражданин должен быть указан через @username или его сообщение для проведения процедуры исправительного перевоспитания."
            )
            return

        try:
            # Разбаниваем в Telegram (снятие ограничений)
            await message.chat.unban(user_id=target_user_id, only_if_banned=True)
            
            # Удаляем запись о бане из активных наказаний в БД
            removed = await remove_punishment(target_user_id, message.chat.id, "ban", message.from_user.id)
            
            target_name = await get_user_display_name(target_user_id)
            if removed:
                await message.reply(f"✅ Гражданин {target_name} успешно разбанен в системе и в чате!")
                # Уведомление в ЛС
                try:
                    await bot.send_message(
                        target_user_id,
                        f"🕊️ Вы были <b>разбанены</b> в чате <b>{escape(str(message.chat.title))}</b>! Теперь вы снова можете общаться."
                    )
                except Exception:
                    pass
            else:
                await message.reply(f"✅ Гражданин {target_name} разбанен в чате.")
                
        except Exception as e:
            logger.error(f"Ошибка разбана пользователя {target_user_id}: {e}")
            await message.reply(f"❌ Ошибка при разбане: {escape(str(e))}")
    except Exception as e:
        logger.error(f"Глобальная ошибка в unban_command: {e}")
        await message.answer("Ошибка выполнения команды разбана.")

@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, Command("мут"))
async def mute_command(message: Message, bot: Bot, command: CommandObject = None) -> None:
    try:
        target_user_id = await resolve_user_id(message)
        
        if not target_user_id:
            await message.reply("❌ Укажите гражданина для мута.")
            return

        if target_user_id == message.from_user.id:
            await message.reply("❌ Обратитесь к партии с запросом о запрете речи")
            return

        try:
            duration_minutes, reason = parse_moderation_args(message, command, target_user_id)
        except ValueError as e:
            await message.reply(f"❌ {escape(str(e))}")
            return

        until_date = None
        if duration_minutes:
            until_date = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)

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
            
            # Уведомление в ЛС
            try:
                await bot.send_message(
                    target_user_id,
                    f"🤐 Партия временно закрыла вам чат <b>{escape(str(message.chat.title))}</b> {dur_text}.\n"
                    f"📝 Причина: {escape(str(reason))}"
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Ошибка мута гражданина {target_user_id}: {e}")
            await message.reply(f"❌ Ошибка: {escape(str(e))}")
    except Exception as e:
        logger.error(f"Глобальная ошибка в mute_command: {e}")
        await message.answer("Ошибка выполнения команды мута.")

@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, Command("размут"))
async def unmute_command(message: Message, bot: Bot) -> None:
    try:
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
            await message.reply(f"✅ Партия дает слово гражданину {target_name}!")
        except Exception as e:
            logger.error(f"Ошибка размута пользователя {target_user_id}: {e}")
            await message.reply(f"❌ Ошибка: {escape(str(e))}")
    except Exception as e:
        logger.error(f"Глобальная ошибка в unmute_command: {e}")
        await message.answer("Ошибка выполнения команды размута.")

@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, Command("варн"))
async def warn_command(message: Message, bot: Bot, command: CommandObject = None) -> None:
    try:
        target_user_id = await resolve_user_id(message)
        
        if not target_user_id:
            await message.reply("❌ Укажите гражданина для предупреждения.")
            return

        reason = command.args if command and command.args else "Не указана"
        
        if await add_warning(target_user_id, message.chat.id, reason, message.from_user.id):
            target_name = await get_user_display_name(target_user_id)
            count = await get_warnings_count(target_user_id, message.chat.id)
            
            # Штраф рейтинга
            current_rate = await get_user_rate(target_user_id) or 0
            new_rate = current_rate - 50
            await update_user_rate(target_user_id, new_rate)
            
            await message.reply(
                f"⚠️ Гражданину {target_name} выдано предупреждение ({count}).\n"
                f"📉 Партия внимательно следит за гражданином и снимает с него рейтинг в кол-ве 50.\n"
                f"Текущий рейтинг: {new_rate}"
            )
            
            # Уведомление в ЛС
            try:
                await bot.send_message(
                    target_user_id,
                    f"⚠️ Вам выдано <b>предупреждение</b> в чате <b>{escape(str(message.chat.title))}</b>.\n"
                    f"Всего предупреждений: <b>{count}</b>\n"
                    f"📝 Причина: {escape(str(reason))}\n"
                    f"Штраф рейтинга: -50"
                )
            except Exception:
                pass

            # Авто-бан при 3 варнах
            if count >= 3:
                try:
                    # Бан на неделю
                    until_date = datetime.now(timezone.utc) + timedelta(days=7)
                    await message.chat.ban(user_id=target_user_id, until_date=until_date)
                    await add_punishment(target_user_id, message.chat.id, "ban", "3/3 предупреждения", message.bot.id, 10080)
                    await reset_user_rating(target_user_id)
                    await message.answer(f"🚫 Гражданин {target_name} получил 3-е предупреждение и отправляется в ссылку на неделю! Рейтинг обнулен.")
                except Exception as e:
                    logger.error(f"Ошибка авто-бана при 3/3 варнах {target_user_id}: {e}")
            
            # Проверка на авто-мут по рейтингу
            await check_and_apply_auto_moderation(target_user_id, message.chat.id, bot)
        else:
            await message.reply("❌ Ошибка при выдаче предупреждения.")
    except Exception as e:
        logger.error(f"Глобальная ошибка в warn_command: {e}")
        await message.answer("Ошибка выполнения команды предупреждения.")

@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, Command("снять_варн"))
async def unwarn_command(message: Message, bot: Bot) -> None:
    try:
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
    except Exception as e:
        logger.error(f"Ошибка в unwarn_command: {e}")
        await message.answer("Ошибка при снятии варна.")

async def check_and_apply_auto_moderation(user_id: int, chat_id: int, bot: Bot) -> None:
    """
    Проверяет рейтинг пользователя и применяет автоматические наказания.
    """
    try:
        rate = await get_user_rate(user_id) or 0
        
        # Авто-мут при рейтинге 150
        if rate <= 150:
            # Проверяем, нет ли уже активного мута (чтобы не спамить)
            punishments = await get_active_punishments(user_id, chat_id)
            if not any(p['type'] == 'mute' for p in punishments):
                try:
                    until_date = datetime.now(timezone.utc) + timedelta(hours=1)
                    await bot.restrict_chat_member(
                        chat_id=chat_id,
                        user_id=user_id,
                        permissions=ChatPermissions(can_send_messages=False),
                        until_date=until_date
                    )
                    await add_punishment(user_id, chat_id, "mute", "Низкий рейтинг (Черный список)", bot.id, 60)
                    
                    target_name = await get_user_display_name(user_id)
                    await bot.send_message(
                        chat_id, 
                        f"❗ Гражданин {target_name} достигнул критического уровня рейтинга (150) и попадает в <b>Черный список</b>.\n"
                        f"🤐 Наложен автоматический мут на 1 час."
                    )
                    
                    # Уведомление в ЛС
                    try:
                        await bot.send_message(
                            user_id,
                            f"❗ Ваш рейтинг упал до {rate}, вы попали в <b>Черный список</b>.\n"
                            f"🤐 Наложен автоматический мут на 1 час в чате."
                        )
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"Ошибка авто-мута для {user_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка в check_and_apply_auto_moderation: {e}")

@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, Command("банлист"))
@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, F.text.lower() == "банлист")
async def chat_banlist_command(message: Message, bot: Bot) -> None:
    """Выводит список всех забаненных пользователей чата."""
    try:
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("❌ Команда доступна только в группах.")
            return

        banned_users = await get_all_banned_users(message.chat.id)
        if not banned_users:
            await message.reply("📋 В этом чате нет активных банов.")
            return

        res = f"📋 <b>Список забаненных граждан чата {escape(str(message.chat.title))}:</b>\n\n"
        for user in banned_users:
            name = user['nickname']
            reason = user['reason'] or "Не указана"
            expires = user['expires_at'][:16] if user['expires_at'] else "Перманентно"
            res += f"• {escape(str(name))} | До: {escape(str(expires))}\n   Причина: {escape(str(reason))}\n"
        
        await message.answer(res)
    except Exception as e:
        logger.error(f"Ошибка в chat_banlist_command: {e}")
        await message.answer("Ошибка при загрузке банлиста.")

@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, Command("красный_список"))
@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, F.text.lower() == "красный список")
async def chat_redlist_command(message: Message, bot: Bot) -> None:
    """Выводит список граждан с рейтингом > 800."""
    try:
        users = await get_users_by_rate_range(801)
        if not users:
            await message.reply("📋 Красный список пуст. Нам нужно больше примерных граждан!")
            return

        res = f"🔴 <b>Красный список почетных граждан:</b>\n\n"
        for user in users:
            res += f"• {escape(str(user['nickname']))} | Рейтинг: {escape(str(user['reputation']))}\n"
        
        await message.answer(res)
    except Exception as e:
        logger.error(f"Ошибка в chat_redlist_command: {e}")

@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, Command("черный_список"))
@moderation_router.message(F.chat.type.in_(["group", "supergroup"]), moderator_filter, F.text.lower() == "черный список")
async def chat_blacklist_command(message: Message, bot: Bot) -> None:
    """Выводит список граждан с рейтингом < 150."""
    try:
        users = await get_users_by_rate_range(-999999, 149)
        if not users:
            await message.reply("📋 Черный список пуст. Молодцы, товарищи!")
            return

        res = f"⚫ <b>Черный список сомнительных граждан:</b>\n\n"
        for user in users:
            res += f"• {escape(str(user['nickname']))} | Рейтинг: {escape(str(user['reputation']))}\n"
        
        await message.answer(res)
    except Exception as e:
        logger.error(f"Ошибка в chat_blacklist_command: {e}")

@moderation_router.message(F.chat.type == "private", Command("причина_бана"))
@moderation_router.message(F.chat.type == "private", F.text.lower().startswith("причина бана"))
async def dm_ban_reason(message: Message) -> None:
    """Показывает причину бана в ЛС."""
    try:
        details = await get_last_punishment_details(message.from_user.id, "ban")
        if not details:
            await message.reply("❌ У вас нет активных записей о бане в моей системе.")
            return
        
        res = (
            f"🚫 <b>Информация о вашем бане:</b>\n\n"
            f"📝 Причина: {escape(str(details['reason']))}\n"
            f"👮 Модератор: {escape(str(details['moderator_name']))}\n"
        )
        if details['expires_at']:
            res += f"⏳ Срок истекает: {escape(str(details['expires_at'][:16]))}"
        else:
            res += "⏳ Срок: Перманентно"
        
        await message.reply(res)
    except Exception as e:
        logger.error(f"Ошибка в dm_ban_reason: {e}")

@moderation_router.message(F.chat.type == "private", Command("причина_мута"))
@moderation_router.message(F.chat.type == "private", F.text.lower().startswith("причина мута"))
async def dm_mute_reason(message: Message) -> None:
    """Показывает причину мута в ЛС."""
    try:
        details = await get_last_punishment_details(message.from_user.id, "mute")
        if not details:
            await message.reply("❌ У вас нет активных записей о муте в моей системе.")
            return
        
        res = (
            f"🤐 <b>Информация о вашем муте:</b>\n\n"
            f"📝 Причина: {escape(str(details['reason']))}\n"
            f"👮 Модератор: {escape(str(details['moderator_name']))}\n"
        )
        if details['expires_at']:
            res += f"⏳ Срок истекает: {escape(str(details['expires_at'][:16]))}"
        else:
            res += "⏳ Срок: Перманентно"
        
        await message.reply(res)
    except Exception as e:
        logger.error(f"Ошибка в dm_mute_reason: {e}")

async def cleanup_expired_punishments_task(bot: Bot):
    """Фоновая задача для автоматического снятия истекших наказаний."""
    while True:
        try:
            cleaned_count, expired_list = await cleanup_expired_punishments()
            if cleaned_count > 0:
                logger.info(f"Автоматически удалено {cleaned_count} истекших наказаний.")
                for entry in expired_list:
                    user_id, chat_id, p_type = entry
                    try:
                        p_name = "бан" if p_type == "ban" else "мут"
                        await bot.send_message(
                            chat_id=user_id, 
                            text=f"🕊️ Срок вашего <b>{p_name}а</b> в чате истек. Вы снова можете общаться!"
                        )
                    except Exception as e:
                        logger.debug(f"Не удалось уведомить пользователя {user_id} о разбане: {e}")
        except Exception as e:
            logger.error(f"Ошибка в задаче очистки наказаний: {e}")
        await asyncio.sleep(60)
