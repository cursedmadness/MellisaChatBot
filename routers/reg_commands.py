from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters.command import Command

# Импорт бд
from database import (
    get_user_profile
)

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