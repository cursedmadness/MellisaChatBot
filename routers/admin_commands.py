from aiogram import Router, F
from aiogram.filters.command import Command
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from aiogram import Bot
import logging

from database import (
    is_admin,
    add_admin,
    remove_admin,
    get_user_rate,
    update_user_rate,
    unrate_user,
    add_user,
    delete_user_completely,
    get_all_users,
    get_user_by_username,
    update_user_username,
)

ADMIN_IDS = [1534963580, 1103985703, 5806584445] # - ИД администраторов, у кого есть доступ к командам. Нужно будет настроить через бд.

admin_router = Router() # подключение роутеров
admin_router.message.filter(F.from_user.id.in_(ADMIN_IDS))
# Позволяет использовать команды ТОЛЬКО администраторам из бд.
# (Сделать разницу между простыми администраторами(префикс) и администрации чата)

logger = logging.getLogger(__name__)


def _ensure_user_exists(user_id: int, first_name: str | None = None) -> None:
    """
    Гарантирует наличие пользователя в таблице users,
    чтобы обновление рейтинга не пропускало запись.
    """
    add_user(user_id, first_name or "пользователь")

@admin_router.message(Command('ban'))
@admin_router.message(F.text.lower().startswith('бан')) 
# Новый для меня модуль .startswith - улавливает начало команды. Нужен для настройки других аргументов. 
async def ban_user(message: Message, bot: Bot): # type: ignore
        banned_user = None
        # 1. Проверяем, есть ли ответ на сообщение
        if message.reply_to_message:
            banned_user = message.reply_to_message.from_user
        # 2. Проверяем, есть ли упоминание @username в команде
        else:
            args = message.text.split()
            if len(args) < 2:
                await message.answer("Укажите пользователя для бана, ответив на его сообщение или указав @username.")
                return

            username = args[1]
            if username.startswith('@'):
                username = username[1:]  # Убираем @

                try:
                    chat_member = await bot.get_chat_member(chat_id=message.chat.id, user_id=username)
                    banned_user = chat_member.user
                except TelegramBadRequest as e:
                    print(e)
                    await message.answer(f"Пользователь @{username} не найден в этом чате.")
                    return
            else:
                await message.answer("Пожалуйста, укажите @username или ответьте на сообщение пользователя.")
                return

        # Проверяем, что banned_user найден
        if not banned_user:
            logger.warning(f"Не удалось определить пользователя для бана в чате {message.chat.id}")
            await message.answer("Не удалось определить пользователя для бана.")
            return

        # Проверяем, что пользователь не пытается забанить сам себя
        if banned_user.id == message.from_user.id:
            logger.warning(f"Пользователь {message.from_user.id} попытался забанить сам себя")
            await message.answer("❌ Партия не одобряет самовыпил")
            return

        # Выполняем бан
        try:
            await bot.ban_chat_member(chat_id=message.chat.id, user_id=banned_user.id)
            logger.info(f"Пользователь {banned_user.id} забанен администратором {message.from_user.id} в чате {message.chat.id}")
        except TelegramBadRequest as e:
            logger.error(f"Ошибка при бане пользователя {banned_user.id}: {str(e)}")
            await message.answer(f"Ошибка при бане пользователя: {str(e)}")
            return

        # Отправляем сообщение с HTML-разметкой
        await message.answer(
            f'🌲Смотритель <a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a> '
            f'заблокировал гражданина <a href="tg://user?id={banned_user.id}">{banned_user.first_name}</a>\n\n'
            f'Воля партии – исправительное перевоспитание.'
        )

# Роутер на добавление админа
@admin_router.message(F.text.lower().startswith('+админ'))
async def add_admin_command(message: Message, bot: 'Bot'): # type: ignore
    # Проверяем, что команда вызвана в групповом чате
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в групповых чатах!")
        return
    print(f"Команда +админ вызвана пользователем {message.from_user.id} в чате {message.chat.id}")  # Отладка

    # Проверяем, находится ли пользователь в списке ADMIN_IDS
    if message.from_user.id not in ADMIN_IDS:
        print(f"Пользователь {message.from_user.id} не в ADMIN_IDS")  # Отладка
        await message.answer("У вас нет прав для добавления администраторов.")
        return

    new_admin = None

    # 1. Проверяем, есть ли ответ на сообщение
    if message.reply_to_message:
        new_admin = message.reply_to_message.from_user
        print(f"Новый админ (через ответ): {new_admin.id}")  # Отладка
    # 2. Проверяем, есть ли упоминание @username
    else:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Укажите пользователя для назначения админом, ответив на его сообщение или указав @username.")
            return

        username = args[1]
        if username.startswith('@'):
            username = username[1:]  # Убираем @
            try:
                chat_member = await bot.get_chat_member(chat_id=message.chat.id, user_id=username)
                new_admin = chat_member.user
                print(f"Новый админ (через @username): {new_admin.id}")  # Отладка
            except TelegramBadRequest:
                print(f"Пользователь @{username} не найден")  # Отладка
                await message.answer(f"Пользователь @{username} не найден в этом чате.")
                return
        else:
            await message.answer("Пожалуйста, укажите @username или ответьте на сообщение пользователя.")
            return

    # Проверяем, что new_admin найден
    if not new_admin:
        print("new_admin не определён")  # Отладка
        await message.answer("Не удалось определить пользователя для назначения админом.")
        return

    # Проверяем, не является ли пользователь уже админом
    if is_admin(new_admin.id):
        await message.answer(f"Пользователь <a href='tg://user?id={new_admin.id}'>{new_admin.first_name}</a> уже администратор!", parse_mode='HTML')
        return

    # Добавляем администратора
    add_admin(new_admin.id, new_admin.first_name)
    await message.answer(
        f"Пользователь <a href='tg://user?id={new_admin.id}'>{new_admin.first_name}</a> назначен администратором!",
        parse_mode='HTML'
    )

# Роутер снимающий с должности админа
@admin_router.message(F.text.lower().startswith('-админ'))
async def remove_admin_command(message: Message, bot: 'Bot'): # type: ignore
    # Проверяем, что команда вызвана в групповом чате
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в групповых чатах!")
        print(f"Команда -админ вызвана в {message.chat.type}, отклонена")  # Отладка
        return

    print(f"Команда -админ вызвана пользователем {message.from_user.id} в чате {message.chat.id}")  # Отладка

    # Проверяем, находится ли пользователь в списке ADMIN_IDS
    if message.from_user.id not in ADMIN_IDS:
        print(f"Пользователь {message.from_user.id} не в ADMIN_IDS")  # Отладка
        await message.answer("У вас нет прав для удаления администраторов.")
        return

    target_user = None

    # 1. Проверяем, есть ли ответ на сообщение
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        print(f"Админ для удаления (через ответ): {target_user.id}")  # Отладка
    # 2. Проверяем, есть ли упоминание @username
    else:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Укажите пользователя для удаления из админов, ответив на его сообщение или указав @username.")
            return

        username = args[1]
        if username.startswith('@'):
            username = username[1:]  # Убираем @
            try:
                chat_member = await bot.get_chat_member(chat_id=message.chat.id, user_id=username)
                target_user = chat_member.user
                print(f"Админ для удаления (через @username): {target_user.id}")  # Отладка
            except TelegramBadRequest:
                print(f"Пользователь @{username} не найден")  # Отладка
                await message.answer(f"Пользователь @{username} не найден в этом чате.")
                return
        else:
            await message.answer("Пожалуйста, укажите @username или ответьте на сообщение пользователя.")
            return

    # Проверяем, что target_user найден
    if not target_user:
        print("target_user не определён")  # Отладка
        await message.answer("Не удалось определить пользователя для удаления из админов.")
        return

    # Проверяем, является ли пользователь админом
    if not is_admin(target_user.id):
        await message.answer(f"Пользователь <a href='tg://user?id={target_user.id}'>{target_user.first_name}</a> не является администратором!", parse_mode='HTML')
        return

    # Проверяем, не пытается ли пользователь удалить сам себя
    if target_user.id == message.from_user.id:
        await message.answer("Вы не можете удалить себя из администраторов!")
        return

    # Удаляем администратораf
    remove_admin(target_user.id)
    await message.answer(
        f"Пользователь <a href='tg://user?id={target_user.id}'>{target_user.first_name}</a> удалён из администраторов!",
        parse_mode='HTML'
    )


@admin_router.message(F.text.lower().startswith("+рейтинг"))
async def add_rate(message: Message):
    try:
        text = message.text.strip()
        
        if text.lower().startswith("+рейтинг"):
            args = text[8:].strip()
            
            if not args:
                await message.reply("Вы не указали количество выдаваемого рейтинга!")
                return
            
            try:
                rate_to_add = int(args)
                
                if rate_to_add <= 0:
                    await message.reply("Количество рейтинга должно быть положительным числом!")
                    return
                
                if message.reply_to_message:
                    user_id = message.reply_to_message.from_user.id
                    first_name = message.reply_to_message.from_user.first_name
                    _ensure_user_exists(user_id, first_name)
                    new_rate = get_user_rate(user_id) + rate_to_add
                    update_user_rate(user_id, new_rate)
                    
                    await message.reply(f"Пользователю выдано {rate_to_add} рейтинга. Новый рейтинг: {new_rate}")
                else:
                    user_id = message.from_user.id
                    _ensure_user_exists(user_id, message.from_user.first_name)
                    new_rate = get_user_rate(user_id) + rate_to_add
                    update_user_rate(user_id, new_rate)
                    
                    await message.reply(f"Вы выдали себе {rate_to_add} рейтинга. Новый рейтинг: {new_rate}")
            
            except ValueError:
                await message.reply("Количество рейтинга должно быть числом!")
    
    except Exception as e:
        await message.answer(f'Ошибка: {e}')

@admin_router.message(F.text.lower().startswith("-рейтинг"))
async def remove_rate(message: Message):
    try:
        text = message.text.strip()
        
        if text.lower().startswith("-рейтинг"):
            args = text[8:].strip()

            if not args:
                await message.reply("Вы не указали количество снимаемого рейтинга!")
                return
            
            try:
                rate_to_remove = int(args)
                
                if rate_to_remove <= 0:
                    await message.reply("Количество рейтинга должно быть положительным числом!")
                    return
                
                if message.reply_to_message:
                    user_id = message.reply_to_message.from_user.id
                    first_name = message.reply_to_message.from_user.first_name
                    _ensure_user_exists(user_id, first_name)
                    new_rate = get_user_rate(user_id) - rate_to_remove  # Не даем уйти в минус
                    update_user_rate(user_id, new_rate)
                    
                    await message.reply(f"У пользователя снято {rate_to_remove} рейтинга. Новый рейтинг: {new_rate}")
                else:
                    user_id = message.from_user.id
                    _ensure_user_exists(user_id, message.from_user.first_name)
                    new_rate = get_user_rate(user_id) - rate_to_remove
                    update_user_rate(user_id, new_rate)
                    
                    await message.reply(f"Вы сняли себе {rate_to_remove} рейтинга. Новый рейтинг: {new_rate}")
            
            except ValueError:
                await message.reply("Количество рейтинга должно быть числом!")
    
    except Exception as e:
        await message.answer(f'Ошибка: {e}')

@admin_router.message(F.text.lower().startswith('анрейт'))
async def unrate(message: Message):
    try:
        text = message.text.strip().lower()
        
        args = text[6:].strip() if len(text) > 6 else ""
        
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            username = message.reply_to_message.from_user.username
            rate = 0
            unrate_user(user_id, rate)
            
            await message.reply(
                f"✅ Партия обнулила рейтинг пользователя\n"
                f"👤 ID: {user_id}\n"
                f"📛 Username: @{username if username else 'нет'}"
            )
            
        elif args:
            # Случай 2: Команда с аргументом (@username)
            if args.startswith('@'):
                username = args[1:].strip()
                user_id = get_user_by_username(username)
                
                if user_id:
                    _ensure_user_exists(user_id, username)
                    unrate_user(user_id, 0)
                    await message.reply(
                        f"✅ Партия обнулила рейтинг пользователя\n"
                        f"👤 ID: {user_id}\n"
                        f"📛 Username: @{username}"
                    )
                else:
                    await message.reply("❌ Пользователь с таким username не найден в базе")
            else:
        
                try:
                    user_id = int(args)
                    _ensure_user_exists(user_id)
                    unrate_user(user_id, 0)
                    await message.reply(f"✅ Партия обнулила рейтинг пользователя с ID: {user_id}")
                except ValueError:
                    await message.reply("❌ Неверный формат. Используйте:\n• /анрейт в ответ на сообщение\n• /анрейт @username\n• /анрейт 123456")
        
        else:
            user_id = message.from_user.id
            username = message.from_user.username
            _ensure_user_exists(user_id, message.from_user.first_name)
            unrate_user(user_id, 0)
            
            await message.reply(
                f"✅ Партия обнулила ваш рейтинг\n"
                f"👤 ID: {user_id}\n"
                f"📛 Username: @{username if username else 'нет'}"
            )
            
    except Exception as e:
        await message.reply(f"❌ Ошибка: {str(e)}")



@admin_router.message(Command("delete_user"))
@admin_router.message(F.text.lower().startswith("обнулить"))
async def delete_user_command(message: Message):
    """
    Команда для администраторов: полностью удаляет пользователя из системы.
    Формат: /delete_user @username или обнулить @username
    """
    if not is_admin(message.from_user.id):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    text = message.text.strip()

    # Определяем username из команды
    if text.lower().startswith("обнулить"):
        username_part = text[8:].strip()  # Убираем "обнулить "
    else:
        username_part = text[12:].strip()  # Убираем "/delete_user "

    if not username_part.startswith("@"):
        await message.reply("❌ Укажите username в формате @username\nПример: /delete_user @username")
        return

    username = username_part[1:].strip()  # Убираем @

    if not username:
        await message.reply("❌ Укажите username после команды.\nПример: /delete_user @username")
        return

    # Выполняем удаление
    logger.info(f"Администратор {message.from_user.id} начинает удаление пользователя @{username}")
    success = delete_user_completely(username)

    if success:
        logger.info(f"Администратор {message.from_user.id} успешно удалил пользователя @{username}")
        await message.reply(
            f"✅ Пользователь @{username} полностью удален из системы.\n"
            f"Удалены все данные: профиль, кошко-жена, хэбао, админские права."
        )
    else:
        logger.warning(f"Администратор {message.from_user.id} не смог удалить пользователя @{username} - пользователь не найден")
        await message.reply(f"❌ Пользователь @{username} не найден в базе данных.")