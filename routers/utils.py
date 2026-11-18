import re
from html import escape
from aiogram.types import Message
from aiogram.filters.command import CommandObject
from database import get_user_by_username, get_user_rate, get_user_profile

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
    # Адресат slash-команды — бот, а не целевой пользователь.
    text = re.sub(r'^/[\w]+(?:@[a-zA-Z0-9_]+)?(?:\s+|$)', '', text)
    
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
    display_name = escape(str(name)) if name else f"ID:{user_id}"
    return f"<a href='tg://user?id={user_id}'>{display_name}</a>"

async def get_user_display_name(user_id: int) -> str:
    """
    Пытается получить ник пользователя из БД, иначе возвращает ссылку по ID.
    """
    from database import get_user_nickname
    nickname = await get_user_nickname(user_id)
    return get_user_link(user_id, nickname)
def pluralize(n: int, singular: str, plural1: str, plural2: str) -> str:
    """
    Склонение слов по числам.
    n: число
    singular: 1 предмет (миска)
    plural1: 2-4 предмета (миски)
    plural2: 5+ предметов (мисок)
    """
    n_abs = abs(n)
    last_two = n_abs % 100
    last = n_abs % 10
    if last_two in (11, 12, 13, 14):
        return plural2
    if last == 1:
        return singular
    if last in (2, 3, 4):
        return plural1
    return plural2

def format_count(n: int, singular: str, plural1: str, plural2: str) -> str:
    """Форматирует число и склонение."""
    return f"{n} {pluralize(n, singular, plural1, plural2)}"

def format_iso_date(date_str: str | None, format_str: str = "%d.%m.%Y") -> str:
    """Форматирует ISO дату в читаемый вид."""
    if not date_str:
        return "когда-то"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(date_str)
        return dt.strftime(format_str)
    except Exception:
        return date_str
async def get_rate_display(user_id: int) -> str:
    """Возвращает красивое отображение рейтинга с эмодзи и текстом"""
    rate = await get_user_rate(user_id)
    if rate is None:
        return f"❓ Ваш социальный рейтинг: Не указан (N/A)"
        
    if rate >= 5000:
        return f"👑 Ваш социальный рейтинг: {rate} (S)"
    elif 3500 <= rate <= 4999:
        return f"🐉 Ваш социальный рейтинг: {rate} (A)"
    elif 1000 <= rate <= 3499:
        return f"☀️ Ваш социальный рейтинг: {rate} (B)"
    elif 51 <= rate <= 999:
        return f"🍀 Ваш социальный рейтинг: {rate} (C)"
    elif -499 <= rate <= 50:
        return f"😈 Ваш социальный рейтинг: {rate} (D)"
    elif rate <= -500:
        return f"☠️ Ваш социальный рейтинг: {rate} (F)"
    else:
        return f"❓ Ваш социальный рейтинг: {rate} (N/A)"

async def get_profile_text(user_id: int) -> str:
    """
    Получает данные из БД и возвращает готовый текст для анкеты.
    """
    profile_data = await get_user_profile(user_id)
    rate_display = await get_rate_display(user_id)

    if profile_data:
        nickname = escape(str(profile_data.get("nickname") or "Не указано"))
        activity = escape(str(profile_data.get("activity", "Не указано")))
        description = escape(str(profile_data.get("description") or "Не указано"))
        city = escape(str(profile_data.get("city") or "Не указано"))

        return (
            f"👤 <b>Досье гражданина</b>\n\n"
            f"🗃️ <b>Учётное имя:</b> <code>{nickname}</code>\n"
            f"🆔 <b>Публичный цифровой идентификатор:</b> <code>{user_id}</code>\n\n"
            f"{rate_display}\n"
            f"☀️ <b>Активность:</b> {activity}\n"
            f"📍 <b>Местоположение:</b> {city}\n\n"
            f"📄 <b>Описание:</b>\n<i>{description}</i>"
        )
    return "Не удалось найти твой профиль. Попробуй написать /start"

def extract_args(text: str, prefixes: list[str]) -> str:
    """
    Извлекает аргументы из текста, убирая первый найденный префикс из списка.
    """
    if not text:
        return ""
    text = text.strip()
    for p in prefixes:
        # Не съедаем части слов; /command@bot также имеет аргументы после пробела.
        bot_suffix = r'(?:@[a-zA-Z0-9_]+)?' if p.startswith('/') else ''
        match = re.match(re.escape(p) + bot_suffix + r'(?:\s+|$)', text, re.IGNORECASE)
        if match:
            return text[match.end():].strip()
    return text
async def extract_target_user(message: Message, command: CommandObject = None) -> tuple[int | None, str | None]:
    """
    Унифицированно извлекает user_id и имя/ничейм цели команды.
    Проверяет реплай, затем аргументы команды, затем текст сообщения.
    Возвращает (user_id, name).
    """
    target_id = None
    target_name = "Гражданин"

    # 1. Реплай
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name
        return target_id, target_name

    # 2. Аргументы команды или текст
    mention = None
    if command is not None:
        args = (command.args or "").split()
        mention = args[0] if args else None
    else:
        # Пытаемся вычленить из текста вручную (для текстовых префиксов типа +рейтинг)
        text = message.text or ""
        parts = text.split()
        if len(parts) > 1:
            # Проверяем, не число ли это (для команд типа +рейтинг 100, где нет меншна)
            if parts[0].lower() in ("+рейтинг", "-рейтинг") and parts[1].lstrip('-').isdigit():
                mention = parts[2] if len(parts) > 2 else None
            else:
                mention = parts[1]

    if mention:
        target_id = await resolve_user_id(mention)
        target_name = mention

    return target_id, target_name
