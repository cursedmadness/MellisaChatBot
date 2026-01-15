from aiogram import Router, F
from aiogram.types import Message
import logging

from database import save_chat_rules, get_chat_rules, is_admin, delete_chat_rules

logger = logging.getLogger(__name__)
rules_router = Router()

@rules_router.message(F.text.lower().startswith("Установить правила"))
async def create_rules(message: Message):
    """
    Создает правила чата.
    Формат: Установить правила
    [текст правил с новой строки]
    """
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply("❌ Правила можно создавать только в групповых чатах!")
        return

    if not await is_admin(message.from_user.id):
        await message.reply("❌ Только администраторы могут создавать правила чата!")
        return

    text = message.text.strip()
    rules_text = text[len("Установить правила"):].strip()

    if not rules_text:
        await message.reply("❌ Укажите текст правил после команды!\n\nПример:\nУстановить правила\n1. Не спамить\n2. Быть вежливым")
        return

    if await save_chat_rules(message.chat.id, rules_text, message.from_user.id):
        logger.info(f"Правила для чата {message.chat.id} обновлены пользователем {message.from_user.id}")
        await message.reply("✅ Правила чата успешно установлены/обновлены!")
    else:
        logger.error(f"Ошибка сохранения правил для чата {message.chat.id}")
        await message.reply("❌ Ошибка при установке правил.")

@rules_router.message(F.text.lower() == "удалить правила")
async def delete_rules(message: Message):
    """
    Удаляет правила чата.
    Команда: Удалить правила
    """
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply("❌ Правила можно удалять только в групповых чатах!")
        return

    if not await is_admin(message.from_user.id):
        await message.reply("❌ Только администраторы могут удалять правила чата!")
        return

    if await delete_chat_rules(message.chat.id):
        await message.reply("🗑️ Правила чата успешно удалены.")
    else:
        await message.reply("❌ В этом чате нет правил для удаления или произошла ошибка.")

@rules_router.message(F.text.lower().in_(["правила", "правила чата", "rules"]))
async def show_rules(message: Message):
    """
    Показывает правила чата.
    """
    if message.chat.type not in ["group", "supergroup"]:
        await message.reply("❌ Правила доступны только в групповых чатах!")
        return

    rules_text = await get_chat_rules(message.chat.id)

    if rules_text:
        await message.reply(f"📋 Правила чата:\n\n{rules_text}")
    else:
        await message.reply("📝 В этом чате пока нет правил.")