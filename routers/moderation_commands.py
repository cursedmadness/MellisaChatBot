import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, ChatPermissions
from pyrogram.enums import ChatMemberStatus
from database import (
    is_admin,
    add_warning,
    remove_warning,
    get_warnings_count,
    add_punishment,
    remove_punishment,
    get_active_punishments,
    get_user_by_username,
    add_user,
    cleanup_expired_punishments,
    get_user_nickname
)
from config import BOT_TOKEN, API_ID, API_HASH
import logging

logger = logging.getLogger(__name__)

# Инициализация pyrogram клиента для модерации
if API_ID and API_HASH:
    moderation_app = Client(
        "moderation_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN
    )
    logger.info("Pyrogram клиент инициализирован для модерации")
else:
    moderation_app = None
    logger.warning("Pyrogram клиент не инициализирован - отсутствуют API_ID или API_HASH")
    logger.warning("Команды модерации будут недоступны. Настройте API_ID и API_HASH в .env файле")


def extract_user_from_text(text: str, message: Message) -> tuple[int | str | None, str]:
    """
    Извлекает информацию о пользователе из текста команды.
    Возвращает (user_id, username) или (None, None) если не найдено.
    """
    text = text.strip()

    # Проверка на реплай
    if message.reply_to_message:
        user = message.reply_to_message.from_user
        return user.id, user.username

    # Проверка на @username
    username_match = re.search(r'@([a-zA-Z0-9_]{5,32})', text)
    if username_match:
        username = username_match.group(1)
        return username, username

    # Проверка на user_id (числовое значение)
    user_id_match = re.search(r'(\d{5,15})', text)
    if user_id_match:
        user_id = int(user_id_match.group(1))
        return user_id, None

    # Проверка на t.me/username
    tme_match = re.search(r't\.me/([a-zA-Z0-9_]{5,32})', text)
    if tme_match:
        username = tme_match.group(1)
        return username, username

    return None, None


async def resolve_user_id(user_identifier: int | str, message: Message) -> tuple[int | None, str | None]:
    """
    Преобразует идентификатор пользователя в user_id.
    Возвращает (user_id, error_message) или (None, error_message).
    """
    try:
        if isinstance(user_identifier, int):
            # Уже числовой ID
            return user_identifier, None

        elif isinstance(user_identifier, str):
            # Поиск по username
            user_id = get_user_by_username(user_identifier)
            if user_id:
                return user_id, None
            else:
                # Попытка получить информацию через pyrogram
                try:
                    user = await moderation_app.get_users(user_identifier)
                    if user:
                        # Добавляем пользователя в БД если нашли
                        add_user(user.id, user.first_name or "Unknown", user.username)
                        return user.id, None
                except Exception as e:
                    logger.warning(f"Не удалось получить пользователя {user_identifier}: {e}")

        return None, f"❌ Гражданин не найден: {user_identifier}"

    except Exception as e:
        logger.error(f"Ошибка при разрешении пользователя {user_identifier}: {e}")
        return None, f"❌ Ошибка при поиске гражданина: {user_identifier}"


async def check_moderator_permissions(message: Message) -> bool:
    """
    Проверяет, имеет ли пользователь права модератора.
    """
    user_id = message.from_user.id

    # Проверка через нашу БД админов
    if is_admin(user_id):
        return True

    # Проверка через Telegram права в чате
    try:
        member = await moderation_app.get_chat_member(message.chat.id, user_id)
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return True
    except Exception as e:
        logger.error(f"Ошибка при проверке прав модератора {user_id}: {e}")

    return False


@moderation_app.on_message(filters.command("бан") & filters.group)
async def ban_command(_: Client, message: Message):
    """
    Команда для бана пользователя.
    Использование: /бан @username или /бан user_id или реплай
    """
    if moderation_app is None:
        await message.reply("❌ Система модерации не настроена. Обратитесь к администратору.")
        return

    if not await check_moderator_permissions(message):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    # Извлекаем информацию о цели
    user_identifier, username = extract_user_from_text(message.text.replace("/бан", "").strip(), message)

    if not user_identifier:
        await message.reply(
            "❌ Укажите гражданина для бана:\n"
            "• Ответьте на сообщение гражданина\n"
            "• Используйте @username\n"
            "• Укажите числовой ID\n"
            "• Используйте ссылку t.me/username"
        )
        return

    # Разрешаем user_id
    target_user_id, error_msg = await resolve_user_id(user_identifier, message)
    if not target_user_id:
        await message.reply(error_msg)
        return

    # Проверяем, что не пытаемся забанить себя
    if target_user_id == message.from_user.id:
        await message.reply("❌ Вы не можете забанить самого себя!")
        return

    # Извлекаем причину
    reason = message.text.replace("/бан", "").strip()
    if user_identifier:
        # Убираем упоминание пользователя из причины
        if isinstance(user_identifier, str):
            reason = reason.replace(f"@{user_identifier}", "").replace(user_identifier, "").strip()
        else:
            reason = reason.replace(str(user_identifier), "").strip()

    if not reason:
        reason = "Не указана"

    try:
        # Баним пользователя через pyrogram
        await moderation_app.ban_chat_member(
            chat_id=message.chat.id,
            user_id=target_user_id
        )

        # Добавляем запись в БД
        add_punishment(target_user_id, message.chat.id, "ban", reason, message.from_user.id)

        # Получаем имя пользователя для ответа
        target_name = get_user_nickname(target_user_id) or f"ID:{target_user_id}"

        await message.reply(
            f"✅ Гражданин {target_name} забанен!\n"
            f"📝 Причина: {reason}\n"
            f"👮 Модератор: {message.from_user.first_name}"
        )

        logger.info(f"Модератор {message.from_user.id} забанил гражданина {target_user_id} в чате {message.chat.id}")

    except Exception as e:
        logger.error(f"Ошибка при бане гражданина {target_user_id}: {e}")
        await message.reply(f"❌ Ошибка при бане гражданина: {str(e)}")


@moderation_app.on_message(filters.command("разбан") & filters.group)
async def unban_command(_: Client, message: Message):
    """
    Команда для разбана пользователя.
    Использование: /разбан @username или /разбан user_id
    """
    if moderation_app is None:
        await message.reply("❌ Система модерации не настроена. Обратитесь к администратору.")
        return

    if not await check_moderator_permissions(message):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    # Извлекаем информацию о цели
    user_identifier, username = extract_user_from_text(message.text.replace("/разбан", "").strip(), message)

    if not user_identifier:
        await message.reply(
            "❌ Укажите гражданина для разбана:\n"
            "• Используйте @username\n"
            "• Укажите числовой ID\n"
            "• Используйте ссылку t.me/username"
        )
        return

    # Разрешаем user_id
    target_user_id, error_msg = await resolve_user_id(user_identifier, message)
    if not target_user_id:
        await message.reply(error_msg)
        return

    try:
        # Разбаниваем пользователя через pyrogram
        await moderation_app.unban_chat_member(
            chat_id=message.chat.id,
            user_id=target_user_id
        )

        # Удаляем запись о бане из БД
        remove_punishment(target_user_id, message.chat.id, "ban", message.from_user.id)

        # Получаем имя пользователя для ответа
        target_name = get_user_nickname(target_user_id) or f"ID:{target_user_id}"

        await message.reply(
            f"✅ Гражданин {target_name} разбанен!\n"
            f"👮 Модератор: {message.from_user.first_name}"
        )

        logger.info(f"Модератор {message.from_user.id} разбанил гражданина {target_user_id} в чате {message.chat.id}")

    except Exception as e:
        logger.error(f"Ошибка при разбане гражданина {target_user_id}: {e}")
        await message.reply(f"❌ Ошибка при разбане гражданина: {str(e)}")


@moderation_app.on_message(filters.command("мут") & filters.group)
async def mute_command(_: Client, message: Message):
    """
    Команда для мута пользователя.
    Использование: /мут @username [время] или /мут user_id [время] или реплай [время]
    Время указывается в минутах, если не указано - перманентный мут
    """
    if moderation_app is None:
        await message.reply("❌ Система модерации не настроена. Обратитесь к администратору.")
        return

    if not await check_moderator_permissions(message):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    # Извлекаем информацию о цели и времени
    text_without_command = message.text.replace("/мут", "").strip()

    # Парсим время (ищем числа в конце)
    duration_minutes = None
    duration_match = re.search(r'(\d+)\s*$', text_without_command)
    if duration_match:
        duration_minutes = int(duration_match.group(1))
        text_without_command = re.sub(r'\d+\s*$', '', text_without_command).strip()

    user_identifier, username = extract_user_from_text(text_without_command, message)

    if not user_identifier:
        await message.reply(
            "❌ Укажите гражданина для мута:\n"
            "• Ответьте на сообщение гражданина\n"
            "• Используйте @username\n"
            "• Укажите числовой ID\n"
            "• Используйте ссылку t.me/username\n\n"
            "📝 Опционально укажите время в минутах в конце команды"
        )
        return

    # Разрешаем user_id
    target_user_id, error_msg = await resolve_user_id(user_identifier, message)
    if not target_user_id:
        await message.reply(error_msg)
        return

    # Проверяем, что не пытаемся замутить себя
    if target_user_id == message.from_user.id:
        await message.reply("❌ Вы не можете замутить самого себя!")
        return

    # Извлекаем причину
    reason = text_without_command
    if user_identifier:
        if isinstance(user_identifier, str):
            reason = reason.replace(f"@{user_identifier}", "").replace(user_identifier, "").strip()
        else:
            reason = reason.replace(str(user_identifier), "").strip()

    if not reason or reason.isdigit():
        reason = "Не указана"

    try:
        # Определяем время мута
        until_date = None
        if duration_minutes:
            from datetime import datetime, timedelta
            until_date = datetime.utcnow() + timedelta(minutes=duration_minutes)

        # Муттим пользователя через pyrogram
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_send_polls=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )

        await moderation_app.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_user_id,
            permissions=permissions,
            until_date=until_date
        )

        # Добавляем запись в БД
        add_punishment(target_user_id, message.chat.id, "mute", reason, message.from_user.id, duration_minutes)

        # Получаем имя пользователя для ответа
        target_name = get_user_nickname(target_user_id) or f"ID:{target_user_id}"

        duration_text = f"на {duration_minutes} минут" if duration_minutes else "перманентно"

        await message.reply(
            f"✅ Гражданин {target_name} замучен {duration_text}!\n"
            f"📝 Причина: {reason}\n"
            f"👮 Модератор: {message.from_user.first_name}"
        )

        logger.info(f"Модератор {message.from_user.id} замуттил гражданина {target_user_id} в чате {message.chat.id} {duration_text}")

    except Exception as e:
        logger.error(f"Ошибка при муте гражданина {target_user_id}: {e}")
        await message.reply(f"❌ Ошибка при муте гражданина: {str(e)}")


@moderation_app.on_message(filters.command("размут") & filters.group)
async def unmute_command(client: Client, message: Message):
    """
    Команда для размута пользователя.
    Использование: /размут @username или /размут user_id
    """
    if moderation_app is None:
        await message.reply("❌ Система модерации не настроена. Обратитесь к администратору.")
        return

    if not await check_moderator_permissions(message):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    # Извлекаем информацию о цели
    user_identifier, username = extract_user_from_text(message.text.replace("/размут", "").strip(), message)

    if not user_identifier:
        await message.reply(
            "❌ Укажите гражданина для размута:\n"
            "• Используйте @username\n"
            "• Укажите числовой ID\n"
            "• Используйте ссылку t.me/username"
        )
        return

    # Разрешаем user_id
    target_user_id, error_msg = await resolve_user_id(user_identifier, message)
    if not target_user_id:
        await message.reply(error_msg)
        return

    try:
        # Размутываем пользователя через pyrogram
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_send_polls=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )

        await moderation_app.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_user_id,
            permissions=permissions
        )

        # Удаляем запись о муте из БД
        remove_punishment(target_user_id, message.chat.id, "mute", message.from_user.id)

        # Получаем имя пользователя для ответа
        target_name = get_user_nickname(target_user_id) or f"ID:{target_user_id}"

        await message.reply(
            f"✅ Гражданин {target_name} размучен!\n"
            f"👮 Модератор: {message.from_user.first_name}"
        )

        logger.info(f"Модератор {message.from_user.id} размуттил гражданина {target_user_id} в чате {message.chat.id}")

    except Exception as e:
        logger.error(f"Ошибка при размуте гражданина {target_user_id}: {e}")
        await message.reply(f"❌ Ошибка при размуте гражданина: {str(e)}")


@moderation_app.on_message(filters.command("варн"))
async def warn_command(_: Client, message: Message):
    """
    Команда для выдачи предупреждения пользователю.
    Использование: /варн @username [причина] или /варн user_id [причина] или реплай [причина]
    """
    if moderation_app is None:
        await message.reply("❌ Система модерации не настроена. Обратитесь к администратору.")
        return

    if not await check_moderator_permissions(message):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    # Извлекаем информацию о цели
    user_identifier, username = extract_user_from_text(message.text.replace("/варн", "").strip(), message)

    if not user_identifier:
        await message.reply(
            "❌ Укажите гражданина для предупреждения:\n"
            "• Ответьте на сообщение гражданина\n"
            "• Используйте @username\n"
            "• Укажите числовой ID\n"
            "• Используйте ссылку t.me/username"
        )
        return

    # Разрешаем user_id
    target_user_id, error_msg = await resolve_user_id(user_identifier, message)
    if not target_user_id:
        await message.reply(error_msg)
        return

    # Проверяем, что не пытаемся выдать варн себе
    if target_user_id == message.from_user.id:
        await message.reply("❌ Вы не можете выдать предупреждение самому себе!")
        return

    # Извлекаем причину
    reason = message.text.replace("/варн", "").strip()
    if user_identifier:
        if isinstance(user_identifier, str):
            reason = reason.replace(f"@{user_identifier}", "").replace(user_identifier, "").strip()
        else:
            reason = reason.replace(str(user_identifier), "").strip()

    if not reason:
        reason = "Не указана"

    # Добавляем предупреждение в БД
    if add_warning(target_user_id, message.chat.id, reason, message.from_user.id):
        # Получаем имя пользователя для ответа
        target_name = get_user_nickname(target_user_id) or f"ID:{target_user_id}"

        # Получаем количество предупреждений
        warnings_count = get_warnings_count(target_user_id, message.chat.id)

        await message.reply(
            f"⚠️ Гражданину {target_name} выдано предупреждение!\n"
            f"📝 Причина: {reason}\n"
            f"🔢 Всего предупреждений: {warnings_count}\n"
            f"👮 Модератор: {message.from_user.first_name}"
        )

        logger.info(f"Модератор {message.from_user.id} выдал предупреждение гражданину {target_user_id} в чате {message.chat.id}")
    else:
        await message.reply("❌ Ошибка при выдаче предупреждения.")


@moderation_app.on_message(filters.command("снять_варн") & filters.group)
async def unwarn_command(_: Client, message: Message):
    """
    Команда для снятия предупреждения с пользователя.
    Использование: /снять_варн @username или /снять_варн user_id
    """
    if moderation_app is None:
        await message.reply("❌ Система модерации не настроена. Обратитесь к администратору.")
        return

    if not await check_moderator_permissions(message):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    # Извлекаем информацию о цели
    user_identifier, username = extract_user_from_text(message.text.replace("/снять_варн", "").strip(), message)

    if not user_identifier:
        await message.reply(
            "❌ Укажите гражданина для снятия предупреждения:\n"
            "• Используйте @username\n"
            "• Укажите числовой ID\n"
            "• Используйте ссылку t.me/username"
        )
        return

    # Разрешаем user_id
    target_user_id, error_msg = await resolve_user_id(user_identifier, message)
    if not target_user_id:
        await message.reply(error_msg)
        return

    # Снимаем предупреждение из БД
    if remove_warning(target_user_id, message.chat.id, message.from_user.id):
        # Получаем имя пользователя для ответа
        target_name = get_user_nickname(target_user_id) or f"ID:{target_user_id}"

        # Получаем количество оставшихся предупреждений
        warnings_count = get_warnings_count(target_user_id, message.chat.id)

        await message.reply(
            f"✅ С гражданина {target_name} снято предупреждение!\n"
            f"🔢 Осталось предупреждений: {warnings_count}\n"
            f"👮 Модератор: {message.from_user.first_name}"
        )

        logger.info(f"Модератор {message.from_user.id} снял предупреждение с гражданина {target_user_id} в чате {message.chat.id}")
    else:
        await message.reply("❌ У гражданина нет активных предупреждений или произошла ошибка.")


@moderation_app.on_message(filters.command("наказания") & filters.group)
async def punishments_command(_: Client, message: Message):
    """
    Команда для просмотра активных наказаний пользователя.
    Использование: /наказания @username или /наказания user_id или реплай
    """
    if moderation_app is None:
        await message.reply("❌ Система модерации не настроена. Обратитесь к администратору.")
        return

    if not await check_moderator_permissions(message):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    # Извлекаем информацию о цели
    user_identifier, username = extract_user_from_text(message.text.replace("/наказания", "").strip(), message)

    if not user_identifier:
        await message.reply(
            "❌ Укажите гражданина для просмотра наказаний:\n"
            "• Ответьте на сообщение гражданина\n"
            "• Используйте @username\n"
            "• Укажите числовой ID\n"
            "• Используйте ссылку t.me/username"
        )
        return

    # Разрешаем user_id
    target_user_id, error_msg = await resolve_user_id(user_identifier, message)
    if not target_user_id:
        await message.reply(error_msg)
        return

    # Получаем активные наказания
    punishments = get_active_punishments(target_user_id, message.chat.id)
    warnings_count = get_warnings_count(target_user_id, message.chat.id)

    # Получаем имя пользователя для ответа
    target_name = get_user_nickname(target_user_id) or f"ID:{target_user_id}"

    if not punishments and warnings_count == 0:
        await message.reply(f"📋 Гражданин {target_name} не имеет активных наказаний или предупреждений.")
        return

    response = f"📋 Активные наказания гражданина {target_name}:\n\n"

    if warnings_count > 0:
        response += f"⚠️ Предупреждений: {warnings_count}\n"

    for punishment in punishments:
        punishment_type = {
            'ban': '🚫 Бан',
            'mute': '🔇 Мут',
            'warn': '⚠️ Варн'
        }.get(punishment['type'], punishment['type'])

        expires_text = ""
        if punishment['expires_at']:
            expires_text = f" (до {punishment['expires_at'][:19]})"
        else:
            expires_text = " (перманентно)"

        response += f"{punishment_type}{expires_text}\n"
        response += f"📝 Причина: {punishment['reason']}\n"
        response += f"🕐 Выдано: {punishment['punished_at'][:19]}\n\n"

    await message.reply(response)


async def start_moderation_bot():
    """
    Запускает pyrogram бота для модерации.
    """
    if moderation_app is None:
        logger.warning("Pyrogram бот для модерации не запущен - отсутствуют API_ID или API_HASH")
        logger.warning("Для работы команд /бан, /мут, /варн настройте API_ID и API_HASH в .env файле")
        logger.warning("Получите их на https://my.telegram.org/")
        return

    logger.info("Запуск бота модерации...")
    try:
        asyncio.create_task(moderation_app.start())
        logger.info("Pyrogram бот модерации запущен в фоне!")
        logger.info("Доступны команды: /бан, /разбан, /мут, /размут, /варн, /снять_варн, /наказания")
    except Exception as e:
        logger.error(f"Ошибка при запуске pyrogram бота модерации: {e}")
        logger.error("Команды модерации будут недоступны")
        return

    # Запускаем периодическую проверку истекших наказаний
    asyncio.create_task(cleanup_expired_punishments_task())


async def cleanup_expired_punishments_task():
    """
    Фоновая задача для автоматического снятия истекших наказаний.
    """
    while True:
        try:
            cleaned_count = cleanup_expired_punishments()
            if cleaned_count > 0:
                logger.info(f"Автоматически снято {cleaned_count} истекших наказаний")
        except Exception as e:
            logger.error(f"Ошибка при очистке истекших наказаний: {e}")

        # Проверяем каждые 5 минут
        await asyncio.sleep(300)


async def stop_moderation_bot():
    """
    Останавливает pyrogram бота для модерации.
    """
    if moderation_app is None:
        return

    logger.info("Остановка бота модерации...")
    try:
        await moderation_app.stop()
        logger.info("Pyrogram бот модерации остановлен")
    except Exception as e:
        logger.error(f"Ошибка при остановке pyrogram бота модерации: {e}")