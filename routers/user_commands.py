from aiogram import Router, F
from aiogram.filters.command import Command
from aiogram.types import Message
from aiogram.enums import ChatType
import os
import time, datetime
from routers.admin_commands import ADMIN_IDS
from database import get_all_admins
from database import (
    add_user, get_user_nickname, set_user_nickname,
    set_user_description, get_user_profile, get_user_description,
    get_user_rate
)

user_router = Router() # подключение роутеров

# Регистрация самой анкеты, берет информацию из БД(будет использоваться и для профиля частично)
async def get_profile_text(user_id: int) -> str:
    """
    Получает данные из БД и возвращает готовый текст для анкеты.
    Эту функцию можно будет использовать в любом роутере.
    """
    profile_data = get_user_profile(user_id)
    
    if profile_data:
        # Если в поле описания ничего нет (None), заменяем на "Не указано"
        description = profile_data.get("description") or "Не указано"

        # Собираем красивое сообщение
        text = (
            f"👤 **Досье гражданина**\n\n"
            f"🗃️ **Учётное имя:** `{profile_data['nickname']}`\n"
            f"🆔 **Публичный цифровой идентификатор:** `{user_id}`\n\n"
            f"🍚 **Социальный рейтинг:** {profile_data['reputation']}\n"
            f"☀️ **Активность:** {profile_data['activity']}\n\n"
            f"📄 **Описание:**\n_{description}_"
        )
        return text
    else:
        return "Не удалось найти твой профиль. Попробуй написать /start"

# Стартовый хендлер для запуска регистрации анкеты
@user_router.message(Command('start'))
async def start_handler(message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "пользователь"
    nickname = get_user_nickname(user_id)
    
    if nickname:
        await message.answer(f"{nickname}, мы Вас узнали! 👋")
    else:
        add_user(user_id, first_name)
        await message.answer(f" 🌸 Добро пожаловать, {first_name}. Ваш профиль загружен в систему. Партия гордится Вами!\n"
                            f"Чтобы узнать больше о нас, можете перейти по этим ссылкам:\n"
                            f"*ссылки*")

# Роутер на смену ника в анкете

@user_router.message(Command('set_nickname'))
@user_router.message(F.text.lower().startswith('сменить имя'))
async def set_nickname_handler(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text.startswith('/set_nickname'):
        nick = text[13:].strip()
    elif text.lower().startswith('сменить имя'):
        nick = text[11:].strip()
    else:
        nick = ""       

    if not nick:
        await message.answer("📝 Ошибка: Пожалуйста, укажите новое имя после команды.\n"
                             "Пример: /set_nickname Любитель Пива")
        return
    else:
        new_nickname = nick
        set_user_nickname(user_id, new_nickname)
        await message.answer(f"✅ Ваше учётное имя успешно изменено на {new_nickname}")

# Роутер на смену описания для анкеты(и профиля)

@user_router.message(Command('set_description'))
@user_router.message(F.text.lower().startswith('сменить описание'))
async def set_description_handler(message: Message):
    # ... (код без изменений)
    user_id = message.from_user.id
    parts = message.text.strip()
    
    if parts.startswith('/set_description'):
        description = parts[16:].strip()
    elif parts.lower().startswith('сменить описание'):
        description = parts[16:].strip()
    else:
        description = ""   
    if not description:
        await message.answer("📝 Ошибка: Пожалуйста, укажите новое описание после команды.\n"
                             "Пример: /set_nickname Люблю светлое пиво")
        return
    else:
        new_description = description
        set_user_description(user_id, description)
        await message.answer(f"✅ Ваше описание успешно изменено.")


# Роутер 'Анкета' - выводит анкету с данными в лс бота(будет отличаться от профиля внутри чата(возможно))

@user_router.message(Command('anketa'))
@user_router.message(F.text.lower().in_(['анкета','досье']))
async def profile_handler(message: Message):
    """
    Отправляет пользователю его анкету.
    """
    user_id = message.from_user.id
    # Просто вызываем нашу универсальную функцию для получения текста
    profile_text = await get_profile_text(user_id)
    
    await message.answer(profile_text, parse_mode="Markdown")
    #await message.answer(f'Изменить данные своей анкеты Вы можете в личных сообщениях бота.')

# Роутер удаляет ник
@user_router.message(Command('delete_nickname'))
@user_router.message(F.text.lower().in_(['удалить ник','удалить имя']))
async def reset_nickname_handler(message: Message):
    """
    Сбрасывает ник пользователя к его имени в Telegram.
    """
    user_id = message.from_user.id
    # Получаем first_name, чтобы использовать его как ник по умолчанию
    first_name = message.from_user.first_name or "пользователь"
    
    set_user_nickname(user_id, first_name)
    
    await message.answer(f"🗑️ Ваше имя успешно отправлено в ссылку.", parse_mode="Markdown")

# Роутер удаляет описание
@user_router.message(Command('delete_description'))
@user_router.message(F.text.lower().in_(['удалить описание','очистить описание']))
async def clear_description_handler(message: Message):
    """
    Очищает описание профиля пользователя.
    """
    user_id = message.from_user.id
    
    # Устанавливаем в базе данных значение None (которое мы потом интерпретируем как "Не указано")
    # Либо можно передать пустую строку "", результат будет тот же.
    set_user_description(user_id, None) 
    
    await message.answer("🗑️ Ваше описание успешно отправлено в ссылку.")

# Роутер выводит ник пользователя
@user_router.message(F.text.lower().in_(['мой ник','ник']))
async def show_my_nickname(message: Message):
    user_id = message.from_user.id
    nickname = get_user_nickname(user_id)
    
    # Проверяем, зарегистрирован ли пользователь
    if nickname:
        await message.answer(f"📝 Твой текущий ник: **{nickname}**", parse_mode="Markdown")
    else:
        await message.answer("Я тебя ещё не знаю. Напиши /start для регистрации.")


# Роутер выводит описание пользователя
@user_router.message(F.text.lower().in_(['моё описание','описание']))
async def show_my_description(message: Message):
    user_id = message.from_user.id
    description = get_user_description(user_id)
    
    # Проверяем, есть ли описание
    if description:
        await message.answer(f"📄 Твоё описание:\n_{description}_", parse_mode="Markdown")
    else:
        # Эта ветка сработает, если описание None или если пользователь не зарегистрирован
        await message.answer("У тебя пока нет описания. Можешь добавить его командой `/set_description`.", parse_mode="Markdown")

@user_router.message(Command('my_rate'))
@user_router.message(F.text.lower().in_(['мой рейтинг']))
async def my_rate(message: Message):
    user_id = message.from_user.id
    rate = get_user_rate(user_id)

    # Достаем рейтинг
    if 5001 <= rate <= 10000:
        rank = "S"
        await message.reply(f"👑 Ваш социальный рейтинг: 5001-10000 и выше\nТекущий ранг в партии: {rank}")

    elif 3501 <= rate <= 5000:
        rank = "A"
        await message.reply(f"🐉 Ваш социальный рейтинг: 3501-5000\nТекущий ранг в партии: {rank}")

    elif 1001 <= rate <= 3500:
        rank = "B"
        await message.reply(f"☀️ Ваш социальный рейтинг: 1001-3500\nТекущий ранг в партии: {rank}")

    elif 51 <= rate <= 1000:
        rank = "C"
        await message.reply(f"🍀 Ваш социальный рейтинг: 51-1000\nТекущий ранг в партии: {rank}")

    elif -500 <= rate <= 50:
        rank = "D"
        await message.reply(f"🍀 Ваш социальный рейтинг: 51-1000\nТекущий ранг в партии: {rank}")

    elif rate <= -500:
        rank = "F"
        await message.reply(f"☠️ Ваш социальный рейтинг: -500 и ниже\nТекущий ранг в партии: {rank}")        

# Роутер-пинг. банально.
@user_router.message(Command('ping'))
@user_router.message(F.text.lower().in_(['пинг','социальный пинг-понг']))
async def ping_bot(message: Message): # type: ignore
    ev = (datetime.datetime.now(tz=datetime.timezone.utc) - message.date).microseconds / 1000000
    sent_message = await message.answer("🤖 Измеряю пинг...")
     # Устанавливаем порог для пинга
    ping_threshold_sec = 0.05

    # Проверяем значение пинга и выбираем текст ответа
    if ev < ping_threshold_sec:
        out = f"🏓 Партия выиграла в пинг-понг за <code>{ev}</code> с"
    else:
        out = f"🏓 Партия проиграла в пинг-понг за <code>{ev}</code> с"
    
    # Редактируем сообщение с окончательным ответом
    await sent_message.edit_text(out)
    
# Роутер вывода списка администраторов
@user_router.message(Command("adminlist"))
@user_router.message(F.text.lower().in_(['кто админ','админы','кто администратор','кто смотритель','.партия']))
async def admin_list_command(message: Message):
    # Получаем список администраторов
    admins = get_all_admins()
    if not admins:
        await message.answer("Список администраторов пуст.")
        return

    # Формируем ответ с HTML-разметкой
    admin_list_text = "<b>🎓 Наши смотрители:</b>\n"
    for user_id, first_name in admins:
        admin_list_text += f"- <a href='tg://user?id={user_id}'>{first_name}</a> (ID: {user_id})\n"

    await message.answer(admin_list_text, parse_mode='HTML')
