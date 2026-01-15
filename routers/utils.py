import re
from aiogram.types import Message
from database import get_user_by_username

def extract_user_from_text(message: Message) -> str | int | None:
    """
    Извлекает идентификатор пользователя из сообщения (реплай или текст).
    Возвращает @username (как строку), user_id (как int) или None.
    """
    # 1. Если есть ответ на сообщение
    if message.reply_to_message:
        return message.reply_to_message.from_user.id

    # 2. Если есть упоминание в тексте
    text = (message.text or message.caption or "").strip()
    
    # Паттерн для @username
    username_match = re.search(r'@([a-zA-Z0-9_]{5,32})', text)
    if username_match:
        return f"@{username_match.group(1)}"

    # Паттерн для user_id (числовое значение)
    id_match = re.search(r'(\d{5,15})', text)
    if id_match:
        return int(id_match.group(1))

    # Паттерн для t.me/username
    tme_match = re.search(r't\.me/([a-zA-Z0-9_]{5,32})', text)
    if tme_match:
        return f"@{tme_match.group(1)}"

    return None

async def resolve_user_id(mention: str | int | Message) -> int | None:
    """
    Преобразует строку (@username, ID) или Message в числовой user_id.
    """
    if isinstance(mention, Message):
        user_id_or_ment = extract_user_from_text(mention)
        if user_id_or_ment is None:
            return None
        return await resolve_user_id(user_id_or_ment)

    if isinstance(mention, int):
        return mention

    mention = str(mention).strip()
    
    # Если это ID в строковом формате
    if mention.isdigit():
        return int(mention)

    # Если это @username
    if mention.startswith('@'):
        username = mention[1:]
        # Пробуем по БД
        user_id = await get_user_by_username(username)
        if user_id:
            return user_id
        
    return None

def get_user_link(user_id: int, name: str | None = None) -> str:
    """
    Возвращает HTML-ссылку на профиль пользователя.
    """
    display_name = name if name else f"ID:{user_id}"
    return f"<a href='tg://user?id={user_id}'>{display_name}</a>"

async def get_user_display_name(user_id: int) -> str:
    """
    Пытается получить ник пользователя из БД, иначе возвращает ссылку по ID.
    """
    from database import get_user_nickname
    nickname = await get_user_nickname(user_id)
    return get_user_link(user_id, nickname)
