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
    get_user_by_username,
    reset_all_rice_to_one,
    get_rate_display,
    reset_all_ratings_to_default,
)
from routers.moderation_commands import moderation_app

ADMIN_IDS = [1534963580, 1103985703, 5806584445] # - ИД главаистраторов, у кого есть доступ к командам. Нужно будет настроить через бд.

admin_router = Router() # подключение роутеров
admin_router.message.filter(F.from_user.id.in_(ADMIN_IDS))
# Позволяет использовать команды ТОЛЬКО главаистраторам из бд.
# (Сделать разницу между простыми главаистраторами(префикс) и главаистрации чата)

logger = logging.getLogger(__name__)


def _ensure_user_exists(user_id: int, first_name: str | None = None) -> None:
    """
    Гарантирует наличие Гражданина в таблице users,
    чтобы обновление рейтинга не пропускало запись.
    """
    add_user(user_id, first_name or "Гражданин")


# Роутер на добавление главаа
@admin_router.message(F.text.lower().startswith('+глава'))
async def add_admin_command(message: Message, bot: 'Bot'): # type: ignore
    # Проверяем, что команда вызвана в групповом чате
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в групповых чатах!")
        return
    print(f"Команда +глава вызвана Гражданином {message.from_user.id} в чате {message.chat.id}")  # Отладка

    # Проверяем, находится ли Гражданин в списке ADMIN_IDS
    if message.from_user.id not in ADMIN_IDS:
        print(f"Гражданин {message.from_user.id} не в ADMIN_IDS")  # Отладка
        await message.answer("У вас нет прав для добавления главы.")
        return

    new_admin = None

    # 1. Проверяем, есть ли ответ на сообщение
    if message.reply_to_message:
        new_admin = message.reply_to_message.from_user
        print(f"Новый глава (через ответ): {new_admin.id}")  # Отладка
    # 2. Проверяем, есть ли упоминание @username
    else:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Укажите Гражданина для назначения главой, ответив на его сообщение или указав @username.")
            return

        username = args[1]
        if username.startswith('@'):
            username = username[1:]  # Убираем @
            try:
                chat_member = await bot.get_chat_member(chat_id=message.chat.id, user_id=username)
                new_admin = chat_member.user
                print(f"Новый глава (через @username): {new_admin.id}")  # Отладка
            except TelegramBadRequest:
                print(f"Гражданин @{username} не найден")  # Отладка
                await message.answer(f"Гражданин @{username} не найден в этом чате.")
                return
        else:
            await message.answer("Пожалуйста, укажите @username или ответьте на сообщение Гражданина.")
            return

    # Проверяем, что new_admin найден
    if not new_admin:
        print("new_admin не определён")  # Отладка
        await message.answer("Не удалось определить Гражданина для назначения главой.")
        return

    # Проверяем, не является ли Гражданин уже главаом
    if is_admin(new_admin.id):
        await message.answer(f"Гражданин <a href='tg://user?id={new_admin.id}'>{new_admin.first_name}</a> уже глава!", parse_mode='HTML')
        return

    # Добавляем главаистратора
    add_admin(new_admin.id, new_admin.first_name)
    await message.answer(
        f"Гражданин <a href='tg://user?id={new_admin.id}'>{new_admin.first_name}</a> назначен глава!",
        parse_mode='HTML'
    )

# Роутер снимающий с должности главаа
@admin_router.message(F.text.lower().startswith('-глава'))
async def remove_admin_command(message: Message, bot: 'Bot'): # type: ignore
    # Проверяем, что команда вызвана в групповом чате
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в групповых чатах!")
        print(f"Команда -глава вызвана в {message.chat.type}, отклонена")  # Отладка
        return

    print(f"Команда -глава вызвана Гражданином {message.from_user.id} в чате {message.chat.id}")  # Отладка

    # Проверяем, находится ли Гражданин в списке ADMIN_IDS
    if message.from_user.id not in ADMIN_IDS:
        print(f"Гражданин {message.from_user.id} не в ADMIN_IDS")  # Отладка
        await message.answer("У вас нет прав для удаления главы.")
        return

    target_user = None

    # 1. Проверяем, есть ли ответ на сообщение
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        print(f"глава для удаления (через ответ): {target_user.id}")  # Отладка
    # 2. Проверяем, есть ли упоминание @username
    else:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Укажите Гражданина для удаления из главы, ответив на его сообщение или указав @username.")
            return

        username = args[1]
        if username.startswith('@'):
            username = username[1:]  # Убираем @
            try:
                chat_member = await bot.get_chat_member(chat_id=message.chat.id, user_id=username)
                target_user = chat_member.user
                print(f"глава для удаления (через @username): {target_user.id}")  # Отладка
            except TelegramBadRequest:
                print(f"Гражданин @{username} не найден")  # Отладка
                await message.answer(f"Гражданин @{username} не найден в этом чате.")
                return
        else:
            await message.answer("Пожалуйста, укажите @username или ответьте на сообщение Гражданина.")
            return

    # Проверяем, что target_user найден
    if not target_user:
        print("target_user не определён")  # Отладка
        await message.answer("Не удалось определить Гражданина для удаления из глав.")
        return

    # Проверяем, является ли Гражданин главаом
    if not is_admin(target_user.id):
        await message.answer(f"Гражданин <a href='tg://user?id={target_user.id}'>{target_user.first_name}</a> не является главой!", parse_mode='HTML')
        return

    # Проверяем, не пытается ли Гражданин удалить сам себя
    if target_user.id == message.from_user.id:
        await message.answer("Вы не можете удалить себя из глав!")
        return

    # Удаляем главаистратораf
    remove_admin(target_user.id)
    await message.answer(
        f"Гражданин <a href='tg://user?id={target_user.id}'>{target_user.first_name}</a> удалён из глав!",
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
                    old_rate = get_user_rate(user_id)
                    new_rate = old_rate + rate_to_add
                    update_user_rate(user_id, new_rate)

                    rate_display = get_rate_display(user_id)
                    await message.reply(f"Гражданину выдано {rate_to_add} рейтинга.\n{rate_display}")
                else:
                    user_id = message.from_user.id
                    _ensure_user_exists(user_id, message.from_user.first_name)
                    old_rate = get_user_rate(user_id)
                    new_rate = old_rate + rate_to_add
                    update_user_rate(user_id, new_rate)

                    rate_display = get_rate_display(user_id)
                    await message.reply(f"Вы выдали себе {rate_to_add} рейтинга.\n{rate_display}")
            
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
                    old_rate = get_user_rate(user_id)
                    new_rate = old_rate - rate_to_remove  # Не даем уйти в минус
                    update_user_rate(user_id, new_rate)

                    rate_display = get_rate_display(user_id)
                    await message.reply(f"У гражданина снято {rate_to_remove} рейтинга.\n{rate_display}")
                else:
                    user_id = message.from_user.id
                    _ensure_user_exists(user_id, message.from_user.first_name)
                    old_rate = get_user_rate(user_id)
                    new_rate = old_rate - rate_to_remove
                    update_user_rate(user_id, new_rate)

                    rate_display = get_rate_display(user_id)
                    await message.reply(f"Вы сняли себе {rate_to_remove} рейтинга.\n{rate_display}")
            
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
                f"✅ Партия обнулила рейтинг Гражданина\n"
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
                        f"✅ Партия обнулила рейтинг Гражданина\n"
                        f"👤 ID: {user_id}\n"
                        f"📛 Username: @{username}"
                    )
                else:
                    await message.reply("❌ Гражданин с таким username не найден в базе")
            else:
        
                try:
                    user_id = int(args)
                    _ensure_user_exists(user_id)
                    unrate_user(user_id, 0)
                    await message.reply(f"✅ Партия обнулила рейтинг Гражданина с ID: {user_id}")
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
    Команда для главаистраторов: полностью удаляет Гражданина из системы.
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
    logger.info(f"главаистратор {message.from_user.id} начинает удаление Гражданина @{username}")
    success = delete_user_completely(username)

    if success:
        logger.info(f"главаистратор {message.from_user.id} успешно удалил Гражданина @{username}")
        await message.reply(
            f"✅ Гражданин @{username} полностью удален из системы.\n"
            f"Удалены все данные: профиль, кошко-жена, хэбао, главаские права."
        )
    else:
        logger.warning(f"главаистратор {message.from_user.id} не смог удалить Гражданина @{username} - Гражданин не найден")
        await message.reply(f"❌ Гражданин @{username} не найден в базе данных.")


@admin_router.message(F.text.lower().startswith("сбросить рис"))
async def reset_rice_command(message: Message):
    """
    Команда для главаистраторов: сбрасывает количество риса у всех пользователей до 1 миски.
    Формат: сбросить рис
    """
    if not is_admin(message.from_user.id):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"главаистратор {message.from_user.id} начинает сброс риса всем Гражданинам")

    await message.reply("🔄 Начинаю сброс количества риса до 1 миски у всех пользователей...")

    reset_count = reset_all_rice_to_one()

    logger.info(f"главаистратор {message.from_user.id} сбросил рис {reset_count} Гражданинам")

    await message.reply(
        f"✅ Сброс риса завершен!\n\n"
        f"📊 Результаты:\n"
        f"• Обновлено пользователей: {reset_count}\n\n"
        f"Теперь у каждого Гражданина ровно 1 миска риса."
    )


@admin_router.message(F.text.lower().startswith("сбросить рейтинг"))
async def reset_rating_command(message: Message):
    """
    Команда для администраторов: сбрасывает рейтинг всех граждан до 100.
    Формат: сбросить рейтинг
    """
    if not is_admin(message.from_user.id):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    logger.info(f"Администратор {message.from_user.id} начинает сброс рейтинга всем гражданам")

    await message.reply("🔄 Начинаю сброс рейтинга до 100 у всех граждан...")

    reset_count = reset_all_ratings_to_default(100)

    logger.info(f"Администратор {message.from_user.id} сбросил рейтинг {reset_count} гражданам")

    await message.reply(
        f"✅ Сброс рейтинга завершен!\n\n"
        f"📊 Результаты:\n"
        f"• Обновлено граждан: {reset_count}\n\n"
        f"Теперь у каждого гражданина рейтинг равен 100."
    )


@admin_router.message(F.text.lower().startswith("статус модерации"))
async def moderation_status_command(message: Message):
    """
    Команда для администраторов: проверка статуса системы модерации.
    Формат: статус модерации
    """
    if not is_admin(message.from_user.id):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    status_msg = "📊 Статус системы модерации:\n\n"

    if moderation_app is not None:
        status_msg += "✅ Pyrogram бот: инициализирован\n"
        status_msg += "✅ Команды модерации: доступны\n\n"
        status_msg += "🛠️ Доступные команды:\n"
        status_msg += "• /бан @username - забанить\n"
        status_msg += "• /разбан @username - разбанить\n"
        status_msg += "• /мут @username [мин] - замутить\n"
        status_msg += "• /размут @username - размутить\n"
        status_msg += "• /варн @username - выдать предупреждение\n"
        status_msg += "• /снять_варн @username - снять предупреждение\n"
        status_msg += "• /наказания @username - просмотреть наказания\n"
    else:
        status_msg += "❌ Pyrogram бот: НЕ инициализирован\n"
        status_msg += "❌ Команды модерации: недоступны\n\n"
        status_msg += "🔧 Для активации:\n"
        status_msg += "1. Перейдите на https://my.telegram.org/\n"
        status_msg += "2. Создайте приложение\n"
        status_msg += "3. Добавьте в .env файл:\n"
        status_msg += "   API_ID=ваш_api_id\n"
        status_msg += "   API_HASH=ваш_api_hash\n"
        status_msg += "4. Перезапустите бота"

    await message.reply(status_msg)