from aiogram import Router, F
from aiogram.filters.command import Command, CommandObject
from aiogram.types import Message
import logging

from database import get_hebao_overview
from routers.utils import extract_target_user, resolve_user_id, get_user_display_name

logger = logging.getLogger(__name__)
hebao_router = Router()

def get_hebao_icon(item_key: str) -> str:
    icons = {
        "miska_risa": "🍚",
        "korm_waifu": "🥫",
    }
    return icons.get(item_key, "📦")

def _format_hebao_message(user_id: int, user_display: str, items: list[dict], is_own: bool = True) -> str:
    valid_items = [i for i in items if i.get("quantity", 0) > 0]
    
    if is_own:
        header = "🎒 <b>Твой Хэбао:</b>\n"
        empty_msg = "🎒 <b>Твой Хэбао пуст...</b>\n\n<i>Здесь пока ничего нет.</i>"
    else:
        user_link = f"<a href='tg://user?id={user_id}'>{user_display}</a>"
        header = f"🎒 <b>Хэбао гражданина {user_link}:</b>\n"
        empty_msg = f"🎒 <b>Хэбао гражданина {user_link} пуст.</b>\n\n<i>У него пока ничего нет.</i>"

    if not valid_items:
        return empty_msg

    lines = [header]
    for item in valid_items:
        qty = item.get("quantity", 0)
        item_key = item.get("item_key", "")
        name = item.get("item_name") or item_key
        name = str(name).capitalize()
        
        icon = get_hebao_icon(item_key)
        lines.append(f"  {icon} <b>{name}</b>: {qty} шт.")
        
    return "\n".join(lines)

@hebao_router.message(Command("hebao"))
@hebao_router.message(F.text.lower().startswith("хэбао") | F.text.lower().startswith("hebao") | F.text.lower().in_(["мой хэбао", "что в хэбао"]))
async def show_hebao_command(message: Message, command: CommandObject = None) -> None:
    try:
        target_id, mention = await extract_target_user(message, command)
        
        # Если не смогли вытащить меншн стандартно, проверяем ручной ввод
        if not target_id and not message.reply_to_message:
            text = message.text or ""
            parts = text.split()
            if len(parts) > 1 and parts[0].lower() in ["хэбао", "hebao"]:
                target_id = await resolve_user_id(parts[1])
                
        # Проверяем, смотрит ли пользователь свой хэбао или чужой
        if not target_id:
            text = message.text or ""
            parts = text.split()
            # Если команда содержит текст после "хэбао", но id не найден, значит указан неверный юзер
            if len(parts) > 1 and parts[0].lower() in ["хэбао", "hebao"]:
                await message.answer("⚠️ Пользователь не найден. Проверьте правильность написания или используйте ответ на сообщение.")
                return
            
            target_id = message.from_user.id
            target_display = message.from_user.full_name or "пользователь"
            is_own = True
        else:
            is_own = (target_id == message.from_user.id)
            if is_own:
                target_display = message.from_user.full_name or "пользователь"
            else:
                target_display = await get_user_display_name(target_id)

        items = await get_hebao_overview(target_id)
        response = _format_hebao_message(target_id, target_display, items, is_own=is_own)

        await message.answer(response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в show_hebao_command: {e}")
        await message.answer("Ошибка при просмотре хэбао.")
