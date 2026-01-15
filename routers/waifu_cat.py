from aiogram import Router, F
from aiogram.filters.command import Command, CommandObject
from aiogram.types import Message, FSInputFile
from datetime import datetime
import os
import random
import logging

from database import (
    create_waifu_for_user,
    get_waifu_by_user,
    update_cat_name,
    update_waifu_age,
    update_cat_image,
    update_cat_state,
    add_user,
    get_user_by_username,
    get_user_rice_count,
    upsert_hebao_item,
)
from routers.utils import extract_user_from_text, resolve_user_id

logger = logging.getLogger(__name__)

waifu_cat_router = Router()


# Utility functions moved to routers/utils.py or unified in resolve_user_id


def _format_waifu_profile(waifu: dict) -> str:
    """Готовит текстовое описание кошко-жены по полям БД."""
    cat_name = waifu.get("cat_name") or "мяу"
    raw_category = waifu.get("category_cats") or "students"
    date_cat = waifu.get("date_cat")
    satiety = waifu.get("satiety") or 0
    mood = waifu.get("mood") or "счастливый"
    age_days = waifu.get("age_days") or 1

    # Пытаемся посчитать, сколько времени прошло
    try:
        start_dt = datetime.fromisoformat(date_cat) if date_cat else None
        days_together = (datetime.utcnow() - start_dt).days if start_dt else "?"
    except Exception:
        days_together = "?"

    def format_date(date_str: str | None) -> str:
        if not date_str:
            return "когда-то"
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%d.%m.%Y")
        except Exception:
            return date_str

    def format_miska(n: int) -> str:
        n_abs = abs(n)
        last_two = n_abs % 100
        last = n_abs % 10
        if last_two in (11, 12, 13, 14):
            word = "мисок"
        elif last == 1:
            word = "миска"
        elif last in (2, 3, 4):
            word = "миски"
        else:
            word = "мисок"
        return f"{n} {word} риса"

    def display_category(category: str, age: int) -> str:
        # Пока для "students" выводим "котёнок". Позже можно развить по возрасту.
        if category == "students":
            return "котёнок"
        return category

    hunger_line = (
        "Сейчас я не хочу есть" # высокая сытость
        if satiety >= 60
        else "Сейчас я голодна" # низкая сытость
    )

    return (
        f"Мяу, хозяин.\n\n"
        f"Меня зовут {cat_name}, я {display_category(raw_category, age_days)}\n"
        f"Я рядом с тобой с {format_date(date_cat)}\n"
        f"С того дня мы с тобой {days_together} дней\n"
        f"Мой возраст: {age_days} дней\n\n"
        f"{hunger_line}\n"
        f"Моё настроение: {mood}\n"
        f"Если тебе интересно, что ещё можно со мной сделать — *ссылка на гайд*"
    )


def _norm(text: str | None) -> str:
    return (text or "").lower().replace("ё", "е").strip()


def _pick_default_image() -> str | None:
    """Берёт случайное фото из папки cats_pic."""
    folder = os.path.join(os.getcwd(), "cats_pic")
    if not os.path.isdir(folder):
        return None
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    image_files = [f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    if not image_files:
        return None
    chosen = random.choice(image_files)
    return os.path.join(folder, chosen)


def _compute_mood(satiety: int) -> str:
    if satiety >= 70:
        return "отличное"
    if satiety >= 40:
        return "хорошее"
    if satiety >= 15:
        return "среднее"
    return "грустное"


async def _apply_satiety_decay(waifu: dict) -> bool:
    """
    Уменьшает сытость за прошедшее время блоками по 5 часов (-10).
    Возвращает True, если данные изменились.
    """
    last_update_str = waifu.get("last_satiety_update")
    try:
        last_dt = datetime.fromisoformat(last_update_str) if last_update_str else None
    except Exception:
        last_dt = None

    if not last_dt:
        return False

    now = datetime.utcnow()
    hours = (now - last_dt).total_seconds() // 3600
    steps = int(hours // 5)  # каждые 5 часов минус 10
    if steps <= 0:
        return False

    new_satiety = max(0, (waifu.get("satiety") or 0) - steps * 10)
    waifu["satiety"] = new_satiety
    waifu["last_satiety_update"] = now.isoformat()
    waifu["mood"] = _compute_mood(new_satiety)

    await update_cat_state(
        waifu["user_id"],
        satiety=new_satiety,
        mood=waifu["mood"],
        last_satiety_update=waifu["last_satiety_update"],
    )
    return True


@waifu_cat_router.message(Command("catch_cat"))
@waifu_cat_router.message(F.text.func(lambda t: _norm(t).startswith("поймать котенка")))
async def catch_cat(message: Message):
    """Создаёт кошко-жену для пользователя, если её ещё нет."""
    user_id = message.from_user.id
    created = await create_waifu_for_user(user_id)
    if created:
        await message.answer("Ты подобрал котёнка! Теперь у тебя есть Кошкожена.")
    else:
        await message.answer("У тебя уже есть Кошкожена. Загляни к ней!")


@waifu_cat_router.message(Command("my_cat"))
@waifu_cat_router.message(F.text.lower().in_(["моя кошка", "моя кошкожена", "мой котёнок"]))
async def show_my_cat(message: Message):
    """
    Показывает информацию о своей кошко-жене.
    """
    viewer_id = message.from_user.id
    target_id = viewer_id

    waifu = await get_waifu_by_user(target_id)
    if not waifu:
        await message.answer("Сначала поймай котёнка: напиши «Поймать котёнка».")
        return

    # Декремент сытости по времени
    await _apply_satiety_decay(waifu)

    # Обновляем возраст только если пользователь в чате (для групп/супергрупп)
    chat = message.chat
    is_member = True
    if chat.type in {"group", "supergroup"}:
        try:
            member = await message.bot.get_chat_member(chat.id, target_id)
            is_member = member.status not in {"left", "kicked"}
        except Exception:
            is_member = False

    if is_member:
        now = datetime.utcnow()
        last_update_str = waifu.get("last_age_update")
        try:
            last_dt = datetime.fromisoformat(last_update_str) if last_update_str else None
        except Exception:
            last_dt = None
        delta_days = (now - last_dt).days if last_dt else 0
        if delta_days > 0:
            new_age = (waifu.get("age_days") or 1) + delta_days
            if await update_waifu_age(target_id, new_age, now.isoformat()):
                waifu["age_days"] = new_age
                waifu["last_age_update"] = now.isoformat()

    # Подтянуть/установить изображение
    image_path = waifu.get("image_cats")
    if not image_path:
        image_path = _pick_default_image()
        if image_path:
            await update_cat_image(target_id, image_path)
            waifu["image_cats"] = image_path

    caption = _format_waifu_profile(waifu)

    if image_path and os.path.isfile(image_path):
        photo = FSInputFile(image_path)
        await message.answer_photo(photo, caption=caption, parse_mode="Markdown")
    else:
        await message.answer(caption, parse_mode="Markdown")


@waifu_cat_router.message(F.text.lower().func(lambda t: t.startswith("кошка ") and ("@" in t or "https://" in t)))
async def show_user_cat(message: Message, command: CommandObject = None):
    """
    Показывает информацию о кошко-жене другого пользователя.
    """
    text = message.text.strip()
    target_id = None
    extracted_username = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_id = target_user.id
        extracted_username = target_user.username
    else:
        if command and command.args:
            mention_part = command.args.strip()
        elif text.startswith("кошка "):
            mention_part = text[6:].strip()
        else:
            await message.answer("Укажите пользователя. Пример: Кошка @username")
            return

        target_id = await resolve_user_id(mention_part)
        if not target_id:
            await message.answer(f"Не удалось найти гражданина '{mention_part}' в системе.")
            return

    waifu = await get_waifu_by_user(target_id)
    if not waifu:
        await message.answer("У этого пользователя пока нет кошки.")
        return

    await _apply_satiety_decay(waifu)

    chat = message.chat
    is_member = True
    if chat.type in {"group", "supergroup"}:
        try:
            member = await message.bot.get_chat_member(chat.id, target_id)
            is_member = member.status not in {"left", "kicked"}
        except Exception:
            is_member = False

    if is_member:
        now = datetime.utcnow()
        last_update_str = waifu.get("last_age_update")
        try:
            last_dt = datetime.fromisoformat(last_update_str) if last_update_str else None
        except Exception:
            last_dt = None
        delta_days = (now - last_dt).days if last_dt else 0
        if delta_days > 0:
            new_age = (waifu.get("age_days") or 1) + delta_days
            if await update_waifu_age(target_id, new_age, now.isoformat()):
                waifu["age_days"] = new_age
                waifu["last_age_update"] = now.isoformat()

    image_path = waifu.get("image_cats")
    if not image_path:
        image_path = _pick_default_image()
        if image_path:
            await update_cat_image(target_id, image_path)
            waifu["image_cats"] = image_path

    caption = _format_waifu_profile(waifu)
    owner_ref = f"<a href='tg://user?id={target_id}'>гражданин</a>"
    caption = f"Кошка {owner_ref}\n\n" + caption

    if image_path and os.path.isfile(image_path):
        photo = FSInputFile(image_path)
        await message.answer_photo(photo, caption=caption, parse_mode="HTML")
    else:
        await message.answer(caption, parse_mode="HTML")


@waifu_cat_router.message(Command("rename_cat"))
@waifu_cat_router.message(F.text.lower().startswith("изменить кличку"))
async def rename_cat(message: Message, command: CommandObject = None):
    """
    Меняет кличку кошко-жены. Пользователь может менять только свою.
    """
    user_id = message.from_user.id
    
    if command and command.args:
        new_name = command.args.strip()
    elif message.text.lower().startswith("изменить кличку"):
        new_name = message.text[len("изменить кличку"):].strip()
    else:
        await message.answer("Укажи новую кличку. Пример: Изменить кличку Луна")
        return

    if not new_name:
        await message.answer("Кличка не может быть пустой.")
        return

    waifu = await get_waifu_by_user(user_id)
    if not waifu:
        await message.answer("У тебя пока нет кошко-жены. Сначала поймай котёнка.")
        return

    updated = await update_cat_name(user_id, new_name)
    if updated:
        await message.answer(f"Кличка обновлена: теперь её зовут {new_name}.")
    else:
        await message.answer("Не удалось изменить кличку. Попробуй ещё раз.")


@waifu_cat_router.message(Command("feed_cat"))
@waifu_cat_router.message(F.text.lower().in_(["покормить", "покормить кошку", "дать рис", "миска риса"]))
async def feed_cat(message: Message):
    """
    Кормление: тратит 1 миску риса, сытость становится 100, настроение пересчитывается.
    """
    user_id = message.from_user.id
    waifu = await get_waifu_by_user(user_id)
    if not waifu:
        await message.answer("У тебя пока нет кошко-жены. Сначала поймай котёнка.")
        return

    # Декремент сытости по времени перед кормлением
    await _apply_satiety_decay(waifu)

    # Проверяем количество риса в хэбао
    bowls = await get_user_rice_count(user_id)
    if bowls <= 0:
        await message.answer("У нас закончился рис. Нечем накормить кошку.")
        return

    current_satiety = waifu.get("satiety") or 0
    if current_satiety >= 100:
        await message.answer("Она уже сыта. Не будем перекармливать.")
        return

    new_satiety = 100
    new_mood = _compute_mood(new_satiety)
    now_iso = datetime.utcnow().isoformat()

    # Обновляем состояние кошки
    cat_updated = await update_cat_state(
        user_id,
        satiety=new_satiety,
        mood=new_mood,
        last_satiety_update=now_iso,
    )

    # Уменьшаем количество риса в хэбао
    rice_updated = await upsert_hebao_item(user_id, "miska_risa", "миска риса", delta=-1)

    if cat_updated and rice_updated:
        logger.info(f"Пользователь {user_id} покормил кошку, потратив 1 миску риса")
        await message.answer(f"Кошка покормлена. Сытость: 100. Осталось мисок: {bowls - 1}.")
    else:
        logger.warning(f"Не удалось покормить кошку пользователю {user_id}: cat_updated={cat_updated}, rice_updated={rice_updated}")
        await message.answer("Не удалось накормить кошку. Попробуй ещё раз.")

