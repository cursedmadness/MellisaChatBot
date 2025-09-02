from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters.command import Command
import time, datetime
from aiogram.enums import ChatType
import asyncio
from aiogram.enums import ParseMode

# Импорт бд
from database import (
    add_user, get_user_nickname, set_user_nickname,
    set_user_description, get_user_profile, get_user_description
)

reg_router = Router()

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
            f"👤 **Твоя анкета**\n\n"
            f"📝 **Никнейм:** `{profile_data['nickname']}`\n"
            f"🆔 **ID:** `{user_id}`\n\n"
            f"⭐ **Репутация:** {profile_data['reputation']}\n"
            f"📊 **Активность:** {profile_data['activity']}\n\n"
            f"📄 **Описание:**\n_{description}_"
        )
        return text
    else:
        return "Не удалось найти твой профиль. Попробуй написать /start"


# Стартовый хендлер для запуска регистрации анкеты и профиля(надо переделать графически)
@reg_router.message(Command('start'))
async def start_handler(message: Message):
    # ... (код без изменений)
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "пользователь"
    
    nickname = get_user_nickname(user_id)
    
    if nickname:
        await message.answer(f"{nickname}, мы Вас узнали! 👋")
    else:
        add_user(user_id, first_name)
        await message.answer(f"Привет, {first_name}! Ты успешно зарегистрирован.")
        await message.answer(f"{first_name}, теперь ты можешь использовать команду\n"
                             f"<code>сменить ник</code> или/и <code>сменить описание</code>\n"
                             f"чтобы добавить оформление анкете.")

# Роутер на смену ника в анкете(и профиле)

@reg_router.message(Command('set_nickname'))
@reg_router.message(F.text.lower().startswith('сменить ник'))
async def set_nickname_handler(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text.startswith('/set_nickname'):
        nick = text[13:].strip()
    elif text.lower().startswith('сменить ник'):
        nick = text[11:].strip()
    else:
        nick = ""       

    if not nick:
        await message.answer("📝 Ошибка: Пожалуйста, укажите новый ник после команды.\n"
                             "Пример: /set_nickname Любитель Пива")
        return
    else:
        new_nickname = nick
        set_user_nickname(user_id, new_nickname)
        await message.answer(f"👍 Ваш ник успешно изменен на: {new_nickname}")

# Роутер на смену описания для анкеты(и профиля)

@reg_router.message(Command('set_description'))
@reg_router.message(F.text.lower().startswith('сменить описание'))
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
        await message.answer(f"👍 Ваше описание успешно изменено на: {new_description}")


# Роутер 'Анкета' - выводит анкету с данными в лс бота(будет отличаться от профиля внутри чата(возможно))

@reg_router.message(Command('anketa'))
@reg_router.message(F.text.lower().in_(['анкета','моя анкета']))
async def profile_handler(message: Message):
    """
    Отправляет пользователю его анкету.
    """
    user_id = message.from_user.id
    # Просто вызываем нашу универсальную функцию для получения текста
    profile_text = await get_profile_text(user_id)
    
    await message.answer(profile_text, parse_mode="Markdown")
    await message.answer(f'Изменить данные своей анкеты Вы можете в личных сообщениях бота.')

@reg_router.message(Command('delete_nickname'))
@reg_router.message(F.text.lower().in_(['удалить ник','очистить ник']))
async def reset_nickname_handler(message: Message):
    """
    Сбрасывает ник пользователя к его имени в Telegram.
    """
    user_id = message.from_user.id
    # Получаем first_name, чтобы использовать его как ник по умолчанию
    first_name = message.from_user.first_name or "пользователь"
    
    set_user_nickname(user_id, first_name)
    
    await message.answer(f"✅ Ваш ник сброшен. Теперь он: **{first_name}**", parse_mode="Markdown")

# --- НОВЫЙ ХЭНДЛЕР для очистки описания ---
@reg_router.message(Command('delete_description'))
@reg_router.message(F.text.lower().in_(['удалить описание','очистить описание']))
async def clear_description_handler(message: Message):
    """
    Очищает описание профиля пользователя.
    """
    user_id = message.from_user.id
    
    # Устанавливаем в базе данных значение None (которое мы потом интерпретируем как "Не указано")
    # Либо можно передать пустую строку "", результат будет тот же.
    set_user_description(user_id, None) 
    
    await message.answer("🗑️ Ваше описание было очищено.")


@reg_router.message(F.text.lower().in_(['мой ник','ник']))
async def show_my_nickname(message: Message):
    user_id = message.from_user.id
    nickname = get_user_nickname(user_id)
    
    # Проверяем, зарегистрирован ли пользователь
    if nickname:
        await message.answer(f"📝 Твой текущий ник: **{nickname}**", parse_mode="Markdown")
    else:
        await message.answer("Я тебя ещё не знаю. Напиши /start для регистрации.")


# --- НОВЫЙ ХЭНДЛЕР для вывода описания ---
@reg_router.message(F.text.lower().in_(['моё описание','описание']))
async def show_my_description(message: Message):
    user_id = message.from_user.id
    description = get_user_description(user_id)
    
    # Проверяем, есть ли описание
    if description:
        await message.answer(f"📄 Твоё описание:\n_{description}_", parse_mode="Markdown")
    else:
        # Эта ветка сработает, если описание None или если пользователь не зарегистрирован
        await message.answer("У тебя пока нет описания. Можешь добавить его командой `/set_description`.", parse_mode="Markdown")
