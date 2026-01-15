from aiogram import Router, F
from aiogram.filters.command import Command, CommandObject
from aiogram.types import Message
import datetime
from database import (
    add_user, get_user_nickname,
    set_user_nickname, set_user_description,
    get_user_description, get_user_rate,
    get_all_admins, get_profile_text, get_rate_status,
    get_user_by_username, get_rate_display
)
from routers.utils import extract_user_from_text, resolve_user_id, get_user_link

user_router = Router() # подключение роутеров


# Utility functions moved to routers/utils.py

# Стартовый хендлер для запуска регистрации анкеты
@user_router.message(Command('start'))
async def start_handler(message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "гражданин"
    nickname = await get_user_nickname(user_id)
    
    if nickname:
        await message.answer(f"{nickname}, мы Вас узнали! 👋")
    else:
        await add_user(user_id, first_name, message.from_user.username)
        await message.answer(f" 🌸 Добро пожаловать, {first_name}. Ваш профиль загружен в систему. Партия гордится Вами!\n"
                            f"Чтобы узнать больше о нас, можете перейти по этим ссылкам:\n"
                            f"*ссылки*")

# Роутер на смену ника в анкете

@user_router.message(Command('set_nickname'))
@user_router.message(F.text.lower().startswith('сменить имя'))
async def set_nickname_handler(message: Message, command: CommandObject = None):
    user_id = message.from_user.id
    
    if command and command.args:
        new_nickname = command.args.strip()
    elif message.text.lower().startswith('сменить имя'):
        new_nickname = message.text[11:].strip()
    else:
        await message.answer("📝 Ошибка: Пожалуйста, укажите новое имя после команды.\n"
                             "Пример: /set_nickname Любитель Пива")
        return

    if not new_nickname:
        await message.answer("📝 Ошибка: Имя не может быть пустым.")
        return

    await set_user_nickname(user_id, new_nickname)
    await message.answer(f"✅ Ваше учётное имя успешно изменено на {new_nickname}")

# Роутер на смену описания для анкеты(и профиля)

@user_router.message(Command('set_description'))
@user_router.message(F.text.lower().startswith('сменить описание'))
async def set_description_handler(message: Message, command: CommandObject = None):
    user_id = message.from_user.id
    
    if command and command.args:
        description = command.args.strip()
    elif message.text.lower().startswith('сменить описание'):
        description = message.text[16:].strip()
    else:
        await message.answer("📝 Ошибка: Пожалуйста, укажите новое описание после команды.\n"
                             "Пример: /set_description Люблю светлое пиво")
        return

    if not description:
        await message.answer("📝 Ошибка: Описание не может быть пустым.")
        return

    await set_user_description(user_id, description)
    await message.answer(f"✅ Ваше описание успешно изменено.")


# Роутер 'Анкета' - выводит анкету с данными в лс бота(будет отличаться от профиля внутри чата(возможно))

@user_router.message(Command('anketa'))
@user_router.message(F.text.lower().in_(['анкета','досье']))
async def profile_handler(message: Message):
    """
    Отправляет гражданину его анкету.
    """
    user_id = message.from_user.id
    # Просто вызываем нашу универсальную функцию для получения текста
    profile_text = await get_profile_text(user_id)
    
    await message.answer(profile_text, parse_mode="Markdown")

# Роутер удаляет ник
@user_router.message(Command('delete_nickname'))
@user_router.message(F.text.lower().in_(['удалить ник','удалить имя']))
async def reset_nickname_handler(message: Message):
    """
    Сбрасывает ник гражданина к его имени в Telegram.
    """
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "гражданин"
    
    await set_user_nickname(user_id, first_name)
    await message.answer(f"🗑️ Ваше имя успешно отправлено в ссылку.", parse_mode="Markdown")

# Роутер удаляет описание
@user_router.message(Command('delete_description'))
@user_router.message(F.text.lower().in_(['удалить описание','очистить описание']))
async def clear_description_handler(message: Message):
    """
    Очищает описание профиля гражданина.
    """
    user_id = message.from_user.id
    await set_user_description(user_id, None) 
    await message.answer("🗑️ Ваше описание успешно отправлено в ссылку.")

# Роутер выводит ник гражданина
@user_router.message(F.text.lower().in_(['мой ник','ник']))
async def show_my_nickname(message: Message):
    user_id = message.from_user.id
    nickname = await get_user_nickname(user_id)
    
    if nickname:
        await message.answer(f"📝 Твой текущий ник: **{nickname}**", parse_mode="Markdown")
    else:
        await message.answer("Я тебя ещё не знаю. Напиши /start для регистрации.")


# Роутер выводит описание гражданина
@user_router.message(F.text.lower().in_(['моё описание','описание']))
async def show_my_description(message: Message):
    user_id = message.from_user.id
    description = await get_user_description(user_id)
    
    if description:
        await message.answer(f"📄 Твоё описание:\n_{description}_", parse_mode="Markdown")
    else:
        await message.answer("У тебя пока нет описания. Можешь добавить его командой `/set_description`.", parse_mode="Markdown")

# Роутер выводит рейтинг гражданина
@user_router.message(Command('my_rate'))
@user_router.message(F.text.lower().in_(['мой рейтинг', 'рейтинг']))
async def my_rate(message: Message):
    user_id = message.from_user.id
    rate_display = await get_rate_display(user_id)
    await message.reply(rate_display)       

#Роутер-пинг. банально.
@user_router.message(Command('ping'))
@user_router.message(F.text.lower().in_(['пинг','социальный пинг-понг']))
async def ping_bot(message: Message): # type: ignore
    ev = (datetime.datetime.now(tz=datetime.timezone.utc) - message.date).microseconds / 1000000
    sent_message = await message.answer("🤖 Измеряю пинг...")
     # Устанавливаем порог для пинга
    ping_threshold_sec = 0.05

    # Проверяем значение пинга и выбираем текст ответа
    if ev < ping_threshold_sec:
        out = f"🏓 Партия выиграла в пинг-понг за <code>{ev}</code> мс"
    else:
        out = f"🏓 Партия проиграла в пинг-понг за <code>{ev}</code> мс"
    
    # Редактируем сообщение с окончательным ответом
    await sent_message.edit_text(out)
    
# Роутер вывода списка администраторов
@user_router.message(Command("adminlist"))
@user_router.message(F.text.lower().in_(['кто админ','админы','кто администратор','кто смотритель','.партия']))
async def admin_list_command(message: Message):
    admins = await get_all_admins()
    if not admins:
        await message.answer("Список администраторов пуст.")
        return

    admin_list_text = "<b>🎓 Наши смотрители:</b>\n"
    for user_id, first_name in admins:
        admin_list_text += f"- {get_user_link(user_id, first_name)}\n"

    await message.answer(admin_list_text, parse_mode='HTML')


@user_router.message(F.text.lower().func(lambda t: t.startswith("ид ") or t == "мой ид"))
async def show_user_id(message: Message, command: CommandObject = None):
    """
    Показывает ID гражданина.
    Команды: "мой ид", "ид @username", "ид @user_id", "ид https://t.me/username"
    """
    text = message.text.strip().lower()

    target_id = None
    target_display = None

    if text == "мой ид":
        target_id = message.from_user.id
        target_display = message.from_user.full_name or "пользователь"
    else:
        # Извлекаем упоминание
        if command and command.args:
            mention_part = command.args.strip()
        elif text.startswith("ид "):
            mention_part = text[3:].strip()
        else:
            await message.reply("Укажите гражданина. Пример: ид @username")
            return

        target_id = await resolve_user_id(mention_part)
        if target_id:
            target_display = f"user_{target_id}"
        else:
            # Если не нашли по ID/меншену, возможно это просто текст (попытка найти по базе будет в resolve_user_id)
            await message.reply(f"Гражданин '{mention_part}' не найден в системе.")
            return

    # Формируем ответ
    user_link = f"<a href='tg://user?id={target_id}'>{target_display}</a>"
    response = f"Ид гражданина {user_link} - <code>{target_id}</code>"
    await message.reply(response, parse_mode="HTML")
