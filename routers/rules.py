from aiogram import Router, F
from aiogram.filters.command import Command
from aiogram.types import Message
from datetime import datetime
import logging

from database import save_chat_rules, get_chat_rules, is_admin

logger = logging.getLogger(__name__)

rules_router = Router()


@rules_router.message(F.text.lower().startswith("создать правила"))
async def create_rules(message: Message):
    """
    Создает правила чата.
    Формат: Создать правила
    [текст правил с новой строки]
    """
    # Проверяем, что команда вызвана в групповом чате
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply("❌ Правила можно создавать только в групповых чатах!")
        return

    # Проверяем, что пользователь является администратором
    if not is_admin(message.from_user.id):
        await message.reply("❌ Только администраторы могут создавать правила чата!")
        return

    # Получаем текст правил (после команды)
    text = message.text.strip()
    if not text.lower().startswith("создать правила"):
        return

    # Извлекаем текст правил (после команды)
    rules_text = text[len("создать правила"):].strip()

    if not rules_text:
        await message.reply("❌ Укажите текст правил после команды!\n\nПример:\nСоздать правила\n1. Не спамить\n2. Быть вежливым")
        return

    # Сохраняем правила
    success = save_chat_rules(message.chat.id, rules_text, message.from_user.id)

    if success:
        logger.info(f"Правила чата {message.chat.id} созданы/обновлены пользователем {message.from_user.id}")
        await message.reply("✅ Правила чата успешно созданы/обновлены!")
    else:
        logger.error(f"Ошибка сохранения правил чата {message.chat.id} пользователем {message.from_user.id}")
        await message.reply("❌ Ошибка при сохранении правил. Попробуйте еще раз.")


@rules_router.message(F.text.lower().in_(["правила", "правила чата", "rules"]))
async def show_rules(message: Message):
    """
    Показывает правила чата.
    """
    # Проверяем, что команда вызвана в групповом чате
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply("❌ Правила доступны только в групповых чатах!")
        return

    # Получаем правила чата
    rules_text = get_chat_rules(message.chat.id)

    if rules_text:
        await message.reply(f"📋 Правила чата:\n\n{rules_text}")
    else:
        await message.reply("📝 В этом чате пока нет правил.\n\nАдминистраторы могут создать их командой:\nСоздать правила\n[текст правил]")