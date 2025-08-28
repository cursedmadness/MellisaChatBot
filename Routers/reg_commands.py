from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters.command import Command
import time, datetime
from aiogram.enums import ChatType
from aiogram.enums import ParseMode

# --- ИЗМЕНЕНИЕ 1: Импортируем новую функцию ---
from database import (
    add_user, get_user_nickname, set_user_nickname,
    set_user_description, get_user_profile  # Добавили get_user_profile
)

reg_router = Router()


# --- НОВАЯ ФУНКЦИЯ для формирования текста анкеты ---
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


# --- Хэндлеры, которые у вас уже были ---
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



@reg_router.message(Command('set_nickname'))
@reg_router.message(F.text.lower().in_('сменить ник'), F.chat.type == ChatType.PRIVATE)
async def set_nickname_handler(message: Message):
    # ... (код без изменений)
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    
    if len(parts) > 1:
        new_nickname = parts[1].strip()
        set_user_nickname(user_id, new_nickname)
        await message.answer(f"👍 Ваш ник успешно изменен на: **{new_nickname}**")
    else:
        await message.answer("📝 **Ошибка:** Пожалуйста, укажите новый ник после команды.\n"
                             "Пример: `/set_nickname Ваш_ник`")


@reg_router.message(Command('set_description'))
@reg_router.message(F.text.lower().in_('сменить описание'), F.chat.type == ChatType.PRIVATE)
async def set_description_handler(message: Message):
    # ... (код без изменений)
    user_id = message.from_user.id
    parts = message.text.split(maxsplit=1)
    
    if len(parts) > 1:
        new_description = parts[1].strip()
        
        if len(new_description) <= 25:
            set_user_description(user_id, new_description)
            await message.answer(f"✅ Ваше описание установлено:\n_{new_description}_", parse_mode="Markdown")
        else:
            await message.answer(f"❌ **Ошибка:** Описание слишком длинное!\n"
                                 f"Максимум **25** символов (у вас {len(new_description)}).")
    else:
        await message.answer("📝 **Ошибка:** Пожалуйста, напишите описание после команды.\n"
                             "Пример: `/set_description Я люблю пива")


# --- НОВЫЙ ХЭНДЛЕР для команды /anketa ---

@reg_router.message(Command('anketa'))
@reg_router.message(F.text.lower().in_(['анкета']), F.chat.type == ChatType.PRIVATE)
async def profile_handler(message: Message):
    """
    Отправляет пользователю его анкету.
    """
    user_id = message.from_user.id
    # Просто вызываем нашу универсальную функцию для получения текста
    profile_text = await get_profile_text(user_id)
    
    await message.answer(profile_text, parse_mode="Markdown")