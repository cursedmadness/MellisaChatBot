from aiogram import Router, F
from aiogram.filters.command import Command, CommandObject
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
from routers.utils import resolve_user_id, get_user_link, get_user_display_name

admin_router = Router()

async def admin_filter(message: Message) -> bool:
    """Проверяет, является ли пользователь администратором."""
    return await is_admin(message.from_user.id)

admin_router.message.filter(admin_filter)

logger = logging.getLogger(__name__)


async def _ensure_user_exists(user_id: int, first_name: str | None = None) -> None:
    """
    Гарантирует наличие Гражданина в таблице users,
    чтобы обновление рейтинга не пропускало запись.
    """
    await add_user(user_id, first_name or "Гражданин")


# Роутер на добавление главаа
@admin_router.message(F.text.lower().startswith('+глава'))
async def add_admin_command(message: Message, bot: Bot, command: CommandObject = None):
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в групповых чатах!")
        return

    target_user_id = None
    target_name = "Гражданин"

    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name
    else:
        mention = None
        if command and command.args:
            mention = command.args.strip()
        else:
            parts = message.text.split()
            if len(parts) > 1:
                mention = parts[1]
        
        if mention:
            target_user_id = await resolve_user_id(mention)
            target_name = mention
        else:
            await message.answer("Укажите Гражданина для назначения главой.")
            return

    if not target_user_id:
        await message.answer("Не удалось найти Гражданина в системе.")
        return

    if await is_admin(target_user_id):
        await message.answer(f"{get_user_link(target_user_id)} уже является главой!")
        return

    await add_admin(target_user_id, target_name)
    await message.answer(f"Гражданин {get_user_link(target_user_id, target_name)} назначен главой!")

# Роутер снимающий с должности главаа
@admin_router.message(F.text.lower().startswith('-глава'))
async def remove_admin_command(message: Message, bot: Bot, command: CommandObject = None):
    if message.chat.type not in ["group", "supergroup"]:
        await message.answer("Эта команда работает только в групповых чатах!")
        return

    target_user_id = None

    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
    else:
        mention = None
        if command and command.args:
            mention = command.args.strip()
        else:
            parts = message.text.split()
            if len(parts) > 1:
                mention = parts[1]
        
        if mention:
            target_user_id = await resolve_user_id(mention)
        else:
            await message.answer("Укажите Гражданина для удаления из глав.")
            return

    if not target_user_id:
        await message.answer("Не удалось найти Гражданина в системе.")
        return

    if not await is_admin(target_user_id):
        await message.answer(f"{get_user_link(target_user_id)} не является главой!")
        return

    if target_user_id == message.from_user.id:
        await message.answer("Вы не можете удалить сами себя!")
        return

    await remove_admin(target_user_id)
    target_display = await get_user_display_name(target_user_id)
    await message.answer(f"Гражданин {target_display} удалён из глав!")


@admin_router.message(F.text.lower().startswith("+рейтинг"))
async def add_rate(message: Message, command: CommandObject = None):
    try:
        text = message.text.strip()
        args_text = ""
        if command and command.args:
            args_text = command.args.strip()
        else:
            args_text = text[8:].strip()
            
        if not args_text:
            await message.reply("Вы не указали количество выдаваемого рейтинга!")
            return
        
        try:
            rate_to_add = int(args_text.split()[0])
            if rate_to_add <= 0:
                await message.reply("Количество рейтинга должно быть положительным числом!")
                return
            
            if message.reply_to_message:
                user_id = message.reply_to_message.from_user.id
                first_name = message.reply_to_message.from_user.first_name
                await _ensure_user_exists(user_id, first_name)
                old_rate = await get_user_rate(user_id) or 100
                new_rate = old_rate + rate_to_add
                await update_user_rate(user_id, new_rate)

                rate_display = await get_rate_display(user_id)
                await message.reply(f"Гражданину выдано {rate_to_add} рейтинга.\n{rate_display}")
            else:
                user_id = message.from_user.id
                await _ensure_user_exists(user_id, message.from_user.first_name)
                old_rate = await get_user_rate(user_id) or 100
                new_rate = old_rate + rate_to_add
                await update_user_rate(user_id, new_rate)

                rate_display = await get_rate_display(user_id)
                await message.reply(f"Вы выдали себе {rate_to_add} рейтинга.\n{rate_display}")
        
        except (ValueError, IndexError):
            await message.reply("Количество рейтинга должно быть числом!")
    
    except Exception as e:
        logger.error(f"Error in add_rate: {e}")
        await message.answer(f'Произошла ошибка при начислении рейтинга.')

@admin_router.message(F.text.lower().startswith("-рейтинг"))
async def remove_rate(message: Message, command: CommandObject = None):
    try:
        text = message.text.strip()
        args_text = ""
        if command and command.args:
            args_text = command.args.strip()
        else:
            args_text = text[8:].strip()

        if not args_text:
            await message.reply("Вы не указали количество снимаемого рейтинга!")
            return
        
        try:
            rate_to_remove = int(args_text.split()[0])
            if rate_to_remove <= 0:
                await message.reply("Количество рейтинга должно быть положительным числом!")
                return
            
            if message.reply_to_message:
                user_id = message.reply_to_message.from_user.id
                first_name = message.reply_to_message.from_user.first_name
                await _ensure_user_exists(user_id, first_name)
                old_rate = await get_user_rate(user_id) or 100
                new_rate = old_rate - rate_to_remove
                await update_user_rate(user_id, new_rate)

                rate_display = await get_rate_display(user_id)
                await message.reply(f"У гражданина снято {rate_to_remove} рейтинга.\n{rate_display}")
            else:
                user_id = message.from_user.id
                await _ensure_user_exists(user_id, message.from_user.first_name)
                old_rate = await get_user_rate(user_id) or 100
                new_rate = old_rate - rate_to_remove
                await update_user_rate(user_id, new_rate)

                rate_display = await get_rate_display(user_id)
                await message.reply(f"Вы сняли себе {rate_to_remove} рейтинга.\n{rate_display}")
        
        except (ValueError, IndexError):
            await message.reply("Количество рейтинга должно быть числом!")
    
    except Exception as e:
        logger.error(f"Error in remove_rate: {e}")
        await message.answer("Произошла ошибка при снятии рейтинга.")

@admin_router.message(F.text.lower().startswith('анрейт'))
async def unrate(message: Message, command: CommandObject = None):
    try:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            username = message.reply_to_message.from_user.username
            await unrate_user(user_id, 0)
            target_display = await get_user_display_name(user_id)
            await message.reply(f"✅ Партия обнулила рейтинг Гражданина {target_display}")
            return

        mention = None
        if command and command.args:
            mention = command.args.strip()
        else:
            text = message.text.strip().lower()
            if len(text) > 6:
                mention = text[6:].strip()

        if mention:
            target_id = await resolve_user_id(mention)
            if target_id:
                await unrate_user(target_id, 0)
                target_display = await get_user_display_name(target_id)
                await message.reply(f"✅ Партия обнулила рейтинг Гражданина {target_display}")
            else:
                await message.reply(f"❌ Гражданин '{mention}' не найден.")
        else:
            user_id = message.from_user.id
            await unrate_user(user_id, 0)
            await message.reply("✅ Партия обнулила ваш рейтинг.")
            
    except Exception as e:
        logger.error(f"Error in unrate: {e}")
        await message.reply("❌ Произошла ошибка при обнулении рейтинга.")



@admin_router.message(Command("delete_user"))
@admin_router.message(F.text.lower().startswith("обнулить"))
async def delete_user_command(message: Message, command: CommandObject = None):
    """
    Команда для администраторов: полностью удаляет Гражданина из системы.
    """
    mention = None
    if command and command.args:
        mention = command.args.strip()
    else:
        text = message.text.strip().lower()
        if text.startswith("обнулить"):
            mention = text[8:].strip()
        else:
            mention = text[12:].strip()

    if not mention:
        await message.reply("❌ Укажите гражданина. Пример: /delete_user @username")
        return

    # Нам нужен именно username для этой функции в database.py, либо мы должны переделать её на user_id
    # Проверим как работает delete_user_completely(username) в database.py
    # В database.py: async def delete_user_completely(username: str) -> bool:
    
    username = None
    if mention.startswith("@"):
        username = mention[1:]
    else:
        # Попытаемся разрешить ID в username? Нет, лучше пусть будет username.
        await message.reply("❌ Для полного удаления используйте @username.")
        return

    success = await delete_user_completely(username)
    if success:
        await message.reply(f"✅ Гражданин @{username} полностью удален из системы.")
    else:
        await message.reply(f"❌ Гражданин @{username} не найден.")


@admin_router.message(F.text.lower().startswith("сбросить рис"))
async def reset_rice_command(message: Message):
    """
    Команда для администраторов: сбрасывает количество риса у всех пользователей до 1 миски.
    """
    await message.reply("🔄 Начинаю сброс количества риса до 1 миски у всех пользователей...")
    reset_count = await reset_all_rice_to_one()
    await message.reply(f"✅ Сброс риса завершен! Обновлено пользователей: {reset_count}")


@admin_router.message(F.text.lower().startswith("сбросить рейтинг"))
async def reset_rating_command(message: Message):
    """
    Команда для администраторов: сбрасывает рейтинг всех граждан до 100.
    """
    await message.reply("🔄 Начинаю сброс рейтинга до 100 у всех граждан...")
    reset_count = await reset_all_ratings_to_default(100)
    await message.reply(f"✅ Сброс рейтинга завершен! Обновлено граждан: {reset_count}")


@admin_router.message(F.text.lower().startswith("статус модерации"))
async def moderation_status_command(message: Message):
    """
    Выводит статус системы модерации.
    """
    status_msg = "📊 Статус системы модерации:\n\n"
    status_msg += "✅ Система: Aiogram (унифицирована)\n"
    status_msg += "✅ Команды модерации: активны\n\n"
    status_msg += "🛠️ Доступные команды:\n"
    status_msg += "• /бан или бан - забанить\n"
    status_msg += "• /разбан - разбанить\n"
    status_msg += "• /мут - замутить\n"
    status_msg += "• /размут - размутить\n"
    status_msg += "• /варн - выдать предупреждение\n"
    status_msg += "• /снять_варн - снять предупреждение\n"
    status_msg += "• /наказания - просмотреть наказания\n"

    await message.reply(status_msg)