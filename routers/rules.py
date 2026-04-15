from aiogram import Router, F
from aiogram.types import Message
import logging

from database import save_chat_rules, get_chat_rules, is_admin, delete_chat_rules

logger = logging.getLogger(__name__)
rules_router = Router()

@rules_router.message(F.text.lower().startswith("установить правила"))
async def create_rules(message: Message) -> None:
    """
    Создает правила чата.
    Формат: Установить правила
    [текст правил с новой строки]
    """
    try:
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("❌ Правила можно создавать только в групповых чатах!")
            return

        if not await is_admin(message.from_user.id):
            await message.reply("❌ Установка правила возможна только членам Партии")
            return

        text = message.text.strip()
        rules_text = text[len("Установить правила"):].strip()

        if not rules_text:
            await message.reply("❌ Партия забыла как верно устанавливать правила.\n\nПример:\nУстановить правила\n1. Не спамить\n2. Быть вежливым")
            return

        if await save_chat_rules(message.chat.id, rules_text, message.from_user.id):
            logger.info(f"Правила для чата {message.chat.id} обновлены пользователем {message.from_user.id}")
            await message.reply("✅ Партия установила новую сводку правил.")
        else:
            logger.error(f"Ошибка сохранения правил для чата {message.chat.id}")
            await message.reply("❌ Партия не смогла установить сводку правил.")
    except Exception as e:
        logger.error(f"Ошибка в create_rules: {e}")
        await message.answer("Ошибка при создании правил.")

@rules_router.message(F.text.lower() == "удалить правила")
async def delete_rules(message: Message) -> None:
    """
    Удаляет правила чата.
    Команда: Удалить правила
    """
    try:
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("❌ Правила можно удалять только в групповых чатах!")
            return

        if not await is_admin(message.from_user.id):
            await message.reply("❌ Только партия руководит письменами правил!")
            return

        if await delete_chat_rules(message.chat.id):
            await message.reply("🗑️ Партия убрала сводку правил.")
        else:
            await message.reply("❌ В этом чате нет правил для удаления или произошла ошибка.")
    except Exception as e:
        logger.error(f"Ошибка в delete_rules: {e}")
        await message.answer("Ошибка при удалении правил.")

@rules_router.message(F.text.lower().in_(["правила", "правила чата", "rules"]))
async def show_rules(message: Message) -> None:
    """
    Показывает правила чата.
    """
    try:
        if message.chat.type not in ["group", "supergroup"]:
            await message.reply("❌ Партия запрещает узнавать правила вне чатов!")
            return

        rules_text = await get_chat_rules(message.chat.id)

        if rules_text:
            await message.reply(f"📋 Партия установила следующие правила:\n\n{rules_text}")
        else:
            await message.reply("📝 Партия временно разрешила анархию.")
    except Exception as e:
        logger.error(f"Ошибка в show_rules: {e}")
        await message.answer("Ошибка при показе правил.")