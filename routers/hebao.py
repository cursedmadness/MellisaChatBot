from aiogram import Router, F
from aiogram.filters.command import Command
from aiogram.types import Message
import re

from database import get_hebao_overview, add_user, get_user_by_username

hebao_router = Router()


def _extract_user_from_text(text: str, bot) -> tuple[int | None, str | None]:
    """
    Извлекает user_id из текста команды.
    Поддерживает: @username, @user_id, https://t.me/username
    Возвращает (user_id, username) или (None, None) если не найдено
    """
    text = text.strip()

    # Паттерн для @username или @user_id
    mention_pattern = r'@([a-zA-Z0-9_]+)'
    match = re.search(mention_pattern, text)
    if match:
        username_or_id = match.group(1)
        # Проверяем, является ли это числом (user_id)
        try:
            user_id = int(username_or_id)
            return user_id, None
        except ValueError:
            # Это username, попробуем найти в базе данных
            # Пока что возвращаем None, так как у нас нет прямого доступа к username->user_id
            # В будущем можно добавить кэширование или использовать API
            return None, username_or_id

    # Паттерн для ссылки https://t.me/username
    link_pattern = r'https?://t\.me/([a-zA-Z0-9_]+)'
    match = re.search(link_pattern, text)
    if match:
        username = match.group(1)
        return None, username

    return None, None


async def _resolve_user_id(username: str, message: Message) -> int | None:
    """
    Пытается разрешить username в user_id через базу данных или API.
    """
    # Сначала попробуем найти в базе данных
    user_id = get_user_by_username(username)
    if user_id:
        return user_id

    # Если не нашли в базе, попробуем через API если пользователь в чате
    if message.chat.type in {"group", "supergroup"}:
        try:
            # Попробуем получить информацию о пользователе через API
            chat_member = await message.bot.get_chat_member(message.chat.id, username)
            if chat_member.user:
                # Добавим пользователя в базу
                add_user(chat_member.user.id, chat_member.user.full_name or "пользователь", chat_member.user.username)
                return chat_member.user.id
        except Exception:
            pass

    return None


def _format_hebao_message(user_id: int, user_display: str, items: list[dict], is_own: bool = True) -> str:
    if is_own:
        # Для своего хэбао
        user_ref = "тебя"
        empty_msg = "У тебя в хэбао пусто."
        header = "У тебя в хэбао есть:"
    else:
        # Для чужого хэбао
        user_link = f"<a href='tg://user?id={user_id}'>{user_display}</a>"
        user_ref = user_link
        empty_msg = f"У {user_ref} в хэбао пусто."
        header = f"У {user_ref} в хэбао есть:"

    if not items:
        return empty_msg

    lines = [header]
    for item in items:
        qty = item.get("quantity", 0)
        name = item.get("item_name", "предмет")
        lines.append(f"— {name} ({qty})")
    return "\n".join(lines)


@hebao_router.message(Command("hebao"))
@hebao_router.message(F.text.lower().in_(["хэбао", "hebao", "мой хэбао", "что в хэбао"]))
async def show_hebao(message: Message):
    """
    Показывает содержимое своего хэбао.
    """
    viewer_id = message.from_user.id
    target_id = viewer_id
    target_display = message.from_user.full_name or "пользователь"

    items = get_hebao_overview(target_id)
    is_own = True
    response = _format_hebao_message(target_id, target_display, items, is_own)

    await message.answer(response, parse_mode="HTML")


@hebao_router.message(F.text.lower().func(lambda t: t.startswith("хэбао ") and ("@" in t or "https://" in t)))
async def show_user_hebao(message: Message):
    """
    Показывает содержимое хэбао другого пользователя.
    Формат: Хэбао @username или Хэбао @user_id или Хэбао https://t.me/username
    """
    viewer_id = message.from_user.id
    text = message.text.strip()

    target_id = None
    target_display = None
    extracted_username = None

    # Сначала проверяем reply_to_message
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_id = target_user.id
        target_display = target_user.full_name or "пользователь"
        extracted_username = target_user.username
    else:
        # Извлекаем упоминание после "хэбао "
        mention_part = text[6:].strip()  # Убираем "хэбао "

        # Проверяем упоминания в тексте
        extracted_user_id, extracted_username = _extract_user_from_text(mention_part, message.bot)

        if extracted_user_id:
            # Найден user_id напрямую
            target_id = extracted_user_id
            target_display = f"user_{target_id}"
        elif extracted_username:
            # Найден username, пытаемся разрешить
            resolved_id = await _resolve_user_id(extracted_username, message)
            if resolved_id:
                target_id = resolved_id
                target_display = f"@{extracted_username}"
            else:
                await message.answer(
                    f"Не удалось найти пользователя @{extracted_username}.\n\n"
                    f"Возможные причины:\n"
                    f"• Пользователь не зарегистрирован в боте (не писал /start)\n"
                    f"• Пользователь не состоит в этом чате\n\n"
                    f"Попробуйте использовать user_id вместо username: Хэбао @123456789\n"
                    f"Или попросите пользователя написать боту в личные сообщения."
                )
                return
        else:
            await message.answer("Укажите пользователя после команды. Пример: Хэбао @username")
            return

    items = get_hebao_overview(target_id)
    is_own = False
    response = _format_hebao_message(target_id, target_display, items, is_own)

    await message.answer(response, parse_mode="HTML")
