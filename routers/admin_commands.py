from aiogram import Router, F
from aiogram.filters.command import Command, CommandObject
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from aiogram import Bot
import logging
import asyncio

from database import (
    is_admin, add_admin, remove_admin,
    get_user_rate, update_user_rate, unrate_user,
    add_user, delete_user_completely, get_user_by_username,
    reset_all_rice_to_one, reset_all_ratings_to_default,
    get_all_waifus_with_owners, clear_all_waifus,
    get_all_users
)
from routers.utils import (
    resolve_user_id, get_user_link, get_user_display_name,
    extract_target_user, extract_args, get_rate_display
)
from routers.moderation_commands import check_and_apply_auto_moderation

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
async def add_admin_command(message: Message, command: CommandObject = None) -> None:
    try:
        if message.chat.type not in ["group", "supergroup"]:
            await message.answer("Эта команда работает только в групповых чатах!")
            return

        target_user_id, target_name = await extract_target_user(message, command)

        if not target_user_id:
            await message.answer("Укажите Гражданина для назначения главой (реплай или @username).")
            return

        if await is_admin(target_user_id):
            await message.answer(f"{get_user_link(target_user_id)} уже является главой!")
            return

        await add_admin(target_user_id, target_name)
        await message.answer(f"Гражданин {get_user_link(target_user_id, target_name)} назначен главой!")
    except Exception as e:
        logger.error(f"Ошибка в add_admin_command: {e}")
        await message.answer("Ошибка при назначении главы.")

# Роутер снимающий с должности главаа
@admin_router.message(F.text.lower().startswith('-глава'))
async def remove_admin_command(message: Message, command: CommandObject = None) -> None:
    try:
        if message.chat.type not in ["group", "supergroup"]:
            await message.answer("Эта команда работает только в групповых чатах!")
            return

        target_user_id, _ = await extract_target_user(message, command)

        if not target_user_id:
            await message.answer("Укажите Гражданина для удаления из глав.")
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
    except Exception as e:
        logger.error(f"Ошибка в remove_admin_command: {e}")
        await message.answer("Ошибка при снятии с должности главы.")


async def _modify_rate(message: Message, command: CommandObject | None, multiply: int) -> None:
    """Вспомогательная функция для изменения рейтинга."""
    try:
        text = message.text or ""
        args_text = extract_args(text, ['+рейтинг', '-рейтинг'])
        if not args_text:
            await message.reply("Вы не указали количество рейтинга!")
            return

        try:
            parts = args_text.split()
            rate_amount = int(parts[0])
            if rate_amount <= 0:
                await message.reply("Количество рейтинга должно быть положительным числом!")
                return
            
            # Если есть второй аргумент, это может быть меншн
            target_id = None
            target_name = None
            if len(parts) > 1:
                target_id = await resolve_user_id(parts[1])
                target_name = parts[1]
            
            # Если не нашли в аргументах, проверяем реплай
            if not target_id and message.reply_to_message:
                target_id = message.reply_to_message.from_user.id
                target_name = message.reply_to_message.from_user.first_name
            
            # Если всё еще нет, меняем себе
            if not target_id:
                target_id = message.from_user.id
                target_name = message.from_user.first_name

            await _ensure_user_exists(target_id, target_name)
            old_rate = await get_user_rate(target_id) or 100
            diff = rate_amount * multiply
            new_rate = old_rate + diff
            
            cat_created = await update_user_rate(target_id, new_rate)
            if message.chat.type in ["group", "supergroup"]:
                await check_and_apply_auto_moderation(target_id, message.chat.id, message.bot)
            
            rate_display = await get_rate_display(target_id)
            action = "выдано" if multiply > 0 else "снято"
            msg_text = f"Гражданину {action} {rate_amount} рейтинга.\n{rate_display}"
            if cat_created:
                msg_text += "\n\n🎊 <b>Партия гордится вами! За ваши заслуги вам выдан котёнок!</b>"
            await message.reply(msg_text)

        except (ValueError, IndexError):
            await message.reply("Количество рейтинга должно быть числом!")
    except Exception as e:
        logger.error(f"Ошибка в _modify_rate: {e}")
        await message.answer("Произошла ошибка при изменении рейтинга.")

@admin_router.message(F.text.lower().startswith("+рейтинг"))
async def add_rate(message: Message, command: CommandObject = None) -> None:
    await _modify_rate(message, command, 1)

@admin_router.message(F.text.lower().startswith("-рейтинг"))
async def remove_rate(message: Message, command: CommandObject = None) -> None:
    await _modify_rate(message, command, -1)

@admin_router.message(F.text.lower().startswith('анрейт'))
async def unrate(message: Message, command: CommandObject = None) -> None:
    try:
        target_id, target_name = await extract_target_user(message, command)
        if not target_id:
            target_id = message.from_user.id
            target_name = message.from_user.first_name
        
        await unrate_user(target_id, 0)
        if message.chat.type in ["group", "supergroup"]:
            await check_and_apply_auto_moderation(target_id, message.chat.id, message.bot)
        
        target_display = await get_user_display_name(target_id)
        await message.reply(f"✅ Партия обнулила рейтинг Гражданина {target_display}")
    except Exception as e:
        logger.error(f"Ошибка в unrate: {e}")
        await message.answer("Ошибка при обнулении рейтинга.")



@admin_router.message(Command("delete_user"))
@admin_router.message(F.text.lower().startswith("обнулить"))
async def delete_user_command(message: Message, command: CommandObject = None) -> None:
    """
    Команда для администраторов: полностью удаляет Гражданина из системы.
    """
    try:
        mention = None
        if command and command.args:
            mention = command.args.strip()
        else:
            text = message.text.strip().lower() if message.text else ""
            if text.startswith("обнулить"):
                mention = text[8:].strip()
            else:
                mention = text[12:].strip()

        if not mention:
            await message.reply("❌ Укажите гражданина. Пример: /delete_user @username")
            return

        username = None
        if mention.startswith("@"):
            username = mention[1:]
        else:
            await message.reply("❌ Для полного удаления используйте @username.")
            return

        success = await delete_user_completely(username)
        if success:
            await message.reply(f"✅ Гражданин @{username} полностью удален из системы.")
        else:
            await message.reply(f"❌ Гражданин @{username} не найден.")
    except Exception as e:
        logger.error(f"Ошибка в delete_user_command: {e}")
        await message.answer("Ошибка при удалении пользователя.")


@admin_router.message(F.text.lower().startswith("сбросить рис"))
async def reset_rice_command(message: Message) -> None:
    """
    Команда для администраторов: сбрасывает количество риса у всех пользователей до 1 миски.
    """
    try:
        await message.reply("🔄 Начинаю сброс количества риса до 1 миски у всех пользователей...")
        reset_count = await reset_all_rice_to_one()
        await message.reply(f"✅ Сброс риса завершен! Обновлено пользователей: {reset_count}")
    except Exception as e:
        logger.error(f"Ошибка в reset_rice_command: {e}")
        await message.answer("Ошибка при сбросе риса.")


@admin_router.message(F.text.lower().startswith("сбросить рейтинг"))
async def reset_rating_command(message: Message) -> None:
    """
    Команда для администраторов: сбрасывает рейтинг всех граждан до 100.
    """
    try:
        await message.reply("🔄 Начинаю сброс рейтинга до 100 у всех граждан...")
        reset_count = await reset_all_ratings_to_default(100)
        await message.reply(f"✅ Сброс рейтинга завершен! Обновлено граждан: {reset_count}")
    except Exception as e:
        logger.error(f"Ошибка в reset_rating_command: {e}")
        await message.answer("Ошибка при сбросе рейтинга.")


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
    status_msg += "• /рассылка <текст> - массовая рассылка гражданам\n"

    await message.reply(status_msg)

@admin_router.message(Command("рассылка"))
@admin_router.message(F.text.lower().startswith("рассылка"))
async def broadcast_command(message: Message, bot: Bot, command: CommandObject = None) -> None:
    """
    Команда для рассылки сообщений всем пользователям.
    Формат: /рассылка Текст сообщения
    """
    try:
        args_text = ""
        if command and command.args:
            args_text = command.args.strip()
        else:
            # Пытаемся вычленить текст из сообщения вручную
            text = message.text or ""
            text_parts = text.split(maxsplit=1)
            if len(text_parts) > 1:
                args_text = text_parts[1].strip()

        if not args_text:
            await message.reply("❌ Вы не ввели текст для рассылки!\nФормат: <code>/рассылка Всем привет!</code>")
            return

        await message.reply("🔄 Начинаю массовую рассылку. Это может занять некоторое время...")

        users = await get_all_users()
        total_users = len(users)
        success_count = 0
        fail_count = 0

        broadcast_text = (
            "📢 <b>ВАЖНОЕ СООБЩЕНИЕ ОТ ПАРТИИ:</b>\n"
            "────────────────────\n\n"
            f"{args_text}"
        )

        for i, user in enumerate(users):
            user_id = user["user_id"]
            try:
                await bot.send_message(user_id, broadcast_text)
                success_count += 1
            except Exception as e:
                logger.debug(f"Не удалось отправить рассылку пользователю {user_id}: {e}")
                fail_count += 1
            
            # Небольшая пауза каждые 15 сообщений, чтобы не попасть под спам-фильтр Telegram
            if (i + 1) % 15 == 0:
                await asyncio.sleep(1)

        await message.reply(
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"📊 Статистика:\n"
            f"• Всего граждан: {total_users}\n"
            f"• Успешно отправлено: {success_count}\n"
            f"• Ошибок (бот заблокирован/др.): {fail_count}"
        )
    except Exception as e:
        logger.error(f"Ошибка в broadcast_command: {e}")
        await message.answer("Ошибка при выполнении рассылки.")