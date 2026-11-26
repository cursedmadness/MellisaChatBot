"""Приют для кошко-жен: сдать кошку, продлить, забрать, посмотреть список."""

import logging
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.filters.command import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import SHELTER_MAX_DAYS, SHELTER_PRICE_KORM_PER_DAY, SHELTER_PRICE_RICE_PER_DAY
from database import (
    count_shelter_cats,
    extend_shelter_atomic,
    get_shelter_cats,
    get_shelter_entry,
    place_in_shelter_atomic,
    process_expired_shelter,
    shelter_price,
    take_from_shelter_atomic,
)
from routers.utils import format_count, get_user_link

logger = logging.getLogger(__name__)

shelter_router = Router()

ITEM_ICONS = {"korm_waifu": ("🥫", "корм"), "miska_risa": ("🍚", "мисок риса")}


def _parse_days(args: str | None) -> int | None:
    """Достаёт количество дней из аргументов команды."""
    if not args:
        return None
    for part in args.split():
        if part.isdigit():
            return int(part)
    return None


def _left_text(expires_at: str) -> str:
    """Сколько осталось до конца срока пребывания."""
    try:
        expires = datetime.fromisoformat(expires_at)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return "неизвестно"
    left = expires - datetime.now(timezone.utc)
    if left.total_seconds() <= 0:
        return "срок истёк, кошку пора забирать"
    days, remainder = divmod(int(left.total_seconds()), 86400)
    hours = remainder // 3600
    if days:
        return f"{days} дн. {hours} ч."
    minutes = (remainder % 3600) // 60
    return f"{hours} ч. {minutes} мин."


def _price_text(days: int) -> str:
    prices = shelter_price(days)
    korm = prices["korm_waifu"]
    rice = prices["miska_risa"]
    return (
        f"🥫 <b>{korm}</b> корма <i>или</i> 🍚 <b>{rice}</b> мисок риса"
    )


def _stock_text(stock: dict) -> str:
    parts = []
    for key, (icon, name) in ITEM_ICONS.items():
        parts.append(f"{icon} {stock.get(key, 0)}")
    return " · ".join(parts)


async def _shelter_state_text(entry: dict) -> str:
    """Подробный отчёт о пребывании кошки в приюте."""
    cat_name = escape(entry.get("cat_name") or "кошка")
    paid_icon, paid_name = ITEM_ICONS.get(
        entry.get("food_key") or "", ("🍽️", "смешанная еда")
    )
    return (
        f"🏡 <b>Приют</b>\n\n"
        f"Твоя кошка <b>{cat_name}</b> сейчас в приюте.\n\n"
        f"📅 Сдана: {_fmt(entry.get('placed_at'))}\n"
        f"⏳ Осталось: <b>{_left_text(entry.get('expires_at'))}</b>\n"
        f"💳 Оплачено дней: <b>{entry.get('days')}</b>\n"
        f"🍽️ Оплата: {paid_icon} {paid_name} — {entry.get('food_paid')} шт.\n\n"
        f"<i>В приюте кошку кормят: сытость не падает, настроение не портится.</i>\n"
        f"Забрать раньше: /shelter_take"
    )


def _fmt(value: str | None) -> str:
    """Дата из ISO в читаемый вид."""
    if not value:
        return "неизвестно"
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return "неизвестно"
    return moment.strftime("%d.%m.%Y %H:%M")


def _info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Кто в приюте", callback_data="shelter:list"),
                InlineKeyboardButton(text="🐾 Моя кошка", callback_data="shelter:mine"),
            ]
        ]
    )


@shelter_router.message(Command("shelter"))
@shelter_router.message(F.text.lower().in_(["приют", "мой приют"]))
async def shelter_info(message: Message) -> None:
    """Рассказывает правила приюта и показывает статус пользователя."""
    try:
        user_id = message.from_user.id
        await process_expired_shelter()
        total = await count_shelter_cats()
        entry = await get_shelter_entry(user_id)

        text = (
            "🏡 <b>Приют для кошко-жен</b>\n\n"
            f"Сейчас в приюте: <b>{total}</b> кошек.\n\n"
            "<b>Условия:</b>\n"
            f"• Срок: от 1 до {SHELTER_MAX_DAYS} дней\n"
            f"• Цена: {SHELTER_PRICE_KORM_PER_DAY} корма или "
            f"{SHELTER_PRICE_RICE_PER_DAY} мисок риса за сутки\n"
            "• В приюте кошку кормят: голод замирает\n\n"
            "<b>Команды:</b>\n"
            "<code>/shelter_place [дней]</code> — сдать кошку\n"
            "<code>/shelter_extend [дней]</code> — продлить срок\n"
            "<code>/shelter_take</code> — забрать кошку\n"
            "<code>/shelter_list</code> — кто сейчас в приюте\n"
            "<code>/shelter_my</code> — как дела у твоей кошки"
        )
        if entry:
            text += f"\n\n{await _shelter_state_text(entry)}"

        await message.answer(text, reply_markup=_info_keyboard())
    except Exception as e:
        logger.error(f"Ошибка в shelter_info: {e}")
        await message.answer("Не удалось открыть приют.")


@shelter_router.message(Command("shelter_place"))
@shelter_router.message(F.text.lower().regexp(r"^сдать кошку"))
async def shelter_place(message: Message, command: CommandObject = None) -> None:
    """Сдаёт кошку в приют на указанное число дней."""
    try:
        user_id = message.from_user.id
        args = command.args if command else (message.text or "")[len("сдать кошку"):]
        days = _parse_days(args)

        if days is None:
            await message.answer(
                "Укажи срок в днях, например:\n"
                f"<code>/shelter_place 3</code>\n\n"
                f"Максимум — {SHELTER_MAX_DAYS} дней."
            )
            return

        result = await place_in_shelter_atomic(user_id, days)
        status = result["status"]

        if status == "no_cat":
            await message.answer("У тебя нет кошко-жены, сдавать в приют некого.")
            return
        if status == "already":
            await message.answer(
                f"Твоя кошка уже в приюте до {_fmt(result['until'])}.\n"
                "Продлить срок: /shelter_extend"
            )
            return
        if status == "bad_days":
            await message.answer(f"Срок должен быть от 1 до {result['max_days']} дней.")
            return
        if status == "no_food":
            need = result["need"]
            have = result["have"]
            await message.answer(
                "😿 Не хватает еды для оплаты приюта.\n\n"
                f"Нужно: {_price_text(days)}\n"
                f"У тебя: {_stock_text(have)}\n\n"
                "Еду можно получить командой /get_food или накормить кошку позже."
            )
            return

        icon, food_name = ITEM_ICONS[result["food_key"]]
        await message.answer(
            f"🏡 <b>Кошка сдана в приют</b>\n\n"
            f"🐾 {escape(result['cat_name'] or 'Кошка')} будет под присмотром "
            f"<b>{result['days']}</b> дн.\n"
            f"📅 Вернётся: {_fmt(result['expires_at'])}\n"
            f"💳 Списали: {icon} {food_name} — {result['food_paid']} шт. "
            f"(осталось {result['left']})\n\n"
            "Забрать раньше: /shelter_take\n"
            "Продлить: /shelter_extend [дней]"
        )
    except Exception as e:
        logger.error(f"Ошибка в shelter_place: {e}")
        await message.answer("Не удалось сдать кошку в приют.")


@shelter_router.message(Command("shelter_extend"))
@shelter_router.message(F.text.lower().regexp(r"^продлить приют"))
async def shelter_extend(message: Message, command: CommandObject = None) -> None:
    """Продлевает пребывание кошки в приюте."""
    try:
        user_id = message.from_user.id
        args = command.args if command else (message.text or "")[len("продлить приют"):]
        days = _parse_days(args)

        if days is None:
            await message.answer("Укажи, на сколько дней продлить: <code>/shelter_extend 2</code>")
            return

        result = await extend_shelter_atomic(user_id, days)
        status = result["status"]

        if status == "not_in_shelter":
            await message.answer("Твоей кошки нет в приюте. Сдать: /shelter_place [дней]")
            return
        if status == "bad_days":
            await message.answer(f"Срок должен быть от 1 до {result['max_days']} дней.")
            return
        if status == "too_long":
            await message.answer(
                f"Суммарный срок не может превышать {result['max_days']} дней."
            )
            return
        if status == "no_food":
            await message.answer(
                "😿 Не хватает еды для продления.\n\n"
                f"Нужно: {_price_text(days)}\n"
                f"У тебя: {_stock_text(result['have'])}"
            )
            return

        icon, food_name = ITEM_ICONS[result["food_key"]]
        await message.answer(
            f"✅ Продлено на <b>{days}</b> дн.\n"
            f"🐾 Всего оплачено: <b>{result['days']}</b> дн.\n"
            f"📅 Вернётся: {_fmt(result['expires_at'])}\n"
            f"💳 Списали: {icon} {food_name} — {result['food_paid']} шт."
        )
    except Exception as e:
        logger.error(f"Ошибка в shelter_extend: {e}")
        await message.answer("Не удалось продлить срок.")


@shelter_router.message(Command("shelter_take"))
@shelter_router.message(F.text.lower().in_(["забрать кошку", "забрать из приюта"]))
async def shelter_take(message: Message) -> None:
    """Забирает кошку из приюта досрочно."""
    try:
        user_id = message.from_user.id
        result = await take_from_shelter_atomic(user_id)

        if result["status"] == "not_in_shelter":
            await message.answer("Твоей кошки нет в приюте — она уже дома.")
            return

        refund = result.get("refunded") or {}
        if refund:
            parts = []
            for key, amount in refund.items():
                icon, name = ITEM_ICONS.get(key, ("🍽️", key))
                parts.append(f"{icon} {name} — <b>{amount}</b> шт.")
            refund_text = (
                "\n\n💰 <b>Возврат за неиспользованные дни:</b>\n"
                + "\n".join(parts)
                + f"\n<i>Неиспользованных суток: {result.get('unused_days') or 0}</i>"
            )
        else:
            refund_text = "\n\n<i>Возврата нет: оплаченные сутки уже использованы.</i>"

        await message.answer(
            f"🐾 <b>{escape(result['cat_name'] or 'Кошка')}</b> вернулась домой!\n\n"
            f"🍽️ Сытость: <b>{result['satiety']}%</b>\n"
            "<i>Она отдохнула и снова рада тебя видеть.</i>"
            f"{refund_text}"
        )
    except Exception as e:
        logger.error(f"Ошибка в shelter_take: {e}")
        await message.answer("Не удалось забрать кошку из приюта.")


@shelter_router.message(Command("shelter_my"))
@shelter_router.message(F.text.lower().in_(["моя кошка в приюте"]))
async def shelter_my(message: Message) -> None:
    """Показывает состояние кошки пользователя в приюте."""
    try:
        user_id = message.from_user.id
        await process_expired_shelter()
        entry = await get_shelter_entry(user_id)
        if not entry:
            await message.answer(
                "Твоя кошка не в приюте.\n"
                "Сдать её: /shelter_place [дней]"
            )
            return
        await message.answer(await _shelter_state_text(entry))
    except Exception as e:
        logger.error(f"Ошибка в shelter_my: {e}")
        await message.answer("Не удалось посмотреть состояние кошки.")


def _format_shelter_list(cats: list[dict], total: int) -> str:
    """Текст списка кошек в приюте."""
    if not cats:
        return "🏡 Приют пуст. Сюда можно сдать свою кошку: /shelter_place [дней]"

    lines = [
        f"🏡 <b>В приюте сейчас {format_count(total, 'кошка', 'кошки', 'кошек')}:</b>\n"
    ]
    for cat in cats:
        owner_name = cat.get("nickname") or cat.get("username") or str(cat["user_id"])
        owner_link = get_user_link(cat["user_id"], owner_name)
        lines.append(
            f"• <b>{escape(cat.get('cat_name') or 'без имени')}</b> — {owner_link}\n"
            f"   ⏳ {_left_text(cat.get('expires_at'))} · 🍽️ {cat.get('satiety') or 0}%"
        )
    if total > len(cats):
        lines.append(f"\n<i>…и ещё {total - len(cats)}</i>")
    return "\n".join(lines)


@shelter_router.message(Command("shelter_list"))
@shelter_router.message(F.text.lower().in_(["список приюта", "кошки в приюте"]))
async def shelter_list(message: Message) -> None:
    """Показывает кошек, которые сейчас в приюте."""
    try:
        await process_expired_shelter()
        cats = await get_shelter_cats(limit=30)
        total = await count_shelter_cats()
        await message.answer(_format_shelter_list(cats, total))
    except Exception as e:
        logger.error(f"Ошибка в shelter_list: {e}")
        await message.answer("Не удалось получить список приюта.")


@shelter_router.callback_query(F.data == "shelter:list")
async def shelter_list_callback(callback: CallbackQuery) -> None:
    """Кнопка «Кто в приюте»."""
    try:
        cats = await get_shelter_cats(limit=30)
        total = await count_shelter_cats()
        await callback.message.answer(_format_shelter_list(cats, total))
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в shelter_list_callback: {e}")
        await callback.answer("Не удалось получить список.", show_alert=True)


@shelter_router.callback_query(F.data == "shelter:mine")
async def shelter_my_callback(callback: CallbackQuery) -> None:
    """Кнопка «Моя кошка»."""
    try:
        entry = await get_shelter_entry(callback.from_user.id)
        if not entry:
            await callback.message.answer(
                "Твоя кошка не в приюте.\nСдать её: /shelter_place [дней]"
            )
        else:
            await callback.message.answer(
                await _shelter_state_text(entry)
            )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в shelter_my_callback: {e}")
        await callback.answer("Не удалось посмотреть состояние.", show_alert=True)
