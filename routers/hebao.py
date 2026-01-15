from aiogram import Router, F
from aiogram.filters.command import Command, CommandObject
from aiogram.types import Message
import logging

from database import get_hebao_overview, add_user, get_user_by_username
from routers.utils import resolve_user_id, get_user_display_name

logger = logging.getLogger(__name__)
hebao_router = Router()

def _format_hebao_message(user_id: int, user_display: str, items: list[dict], is_own: bool = True) -> str:
    if is_own:
        header = "У тебя в хэбао есть:"
        empty_msg = "У тебя в хэбао пусто."
    else:
        user_link = f"<a href='tg://user?id={user_id}'>{user_display}</a>"
        header = f"У {user_link} в хэбао есть:"
        empty_msg = f"У {user_link} в хэбао пусто."

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
async def show_hebao(message: Message, command: CommandObject = None):
    # Если есть аргумент @username или ID - показываем чужой хэбао
    if command and command.args:
        return await show_user_hebao(message, command)
    
    parts = message.text.split()
    if len(parts) > 1 and parts[0].lower() in ["хэбао", "hebao"]:
        return await show_user_hebao(message)

    viewer_id = message.from_user.id
    target_id = viewer_id
    target_display = message.from_user.full_name or "пользователь"

    items = await get_hebao_overview(target_id)
    response = _format_hebao_message(target_id, target_display, items, is_own=True)

    await message.answer(response, parse_mode="HTML")

@hebao_router.message(F.text.lower().startswith("хэбао"))
async def show_user_hebao(message: Message, command: CommandObject = None):
    target_id = await resolve_user_id(message)
    
    if not target_id:
        # Если не удалось разрешить из сообщения, возможно это аргумент команды
        if command and command.args:
            target_id = await resolve_user_id(command.args.split()[0])
        elif not message.reply_to_message:
            # Если просто "хэбао", показываем свой
            parts = message.text.split()
            if len(parts) == 1:
                return await show_hebao(message)
            target_id = await resolve_user_id(parts[1])

    if not target_id:
        await message.answer("Укажите пользователя. Пример: Хэбао @username")
        return

    items = await get_hebao_overview(target_id)
    target_display = await get_user_display_name(target_id)
    response = _format_hebao_message(target_id, target_display, items, is_own=(target_id == message.from_user.id))

    await message.answer(response, parse_mode="HTML")
