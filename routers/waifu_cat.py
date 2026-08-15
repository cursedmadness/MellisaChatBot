from aiogram import Router, F
from aiogram.filters.command import Command, CommandObject
from aiogram.types import Message, FSInputFile
from datetime import datetime, timezone
import os
import random
import logging
import asyncio

from database import (
    create_waifu_for_user,
    get_waifu_by_user,
    update_cat_name,
    update_waifu_age,
    update_cat_image,
    update_cat_state,
    update_waifu_trust,
    get_marriage,
    register_marriage,
    add_user,
    get_user_by_username,
    get_user_rice_count,
    upsert_hebao_item,
    get_hebao_items,
    get_user_rate,
    get_all_waifus_with_owners,
    clear_all_waifus,
    is_admin,
    delete_waifu_by_user,
    can_receive_daily_food,
    update_daily_food_time,
)
from routers.utils import (
    extract_user_from_text,
    resolve_user_id,
    get_user_link,
    format_iso_date,
    format_count,
)

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
        if start_dt and start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - start_dt if start_dt else None
        days_together = diff.days if diff else "?"
    except Exception:
        days_together = "?"

    def display_category(age: int) -> str:
        if age <= 30:
            return "котёнок"
        elif age <= 120:
            return "кошка-студентка"
        else:
            return "милфа-кошка"

    hunger_line = "Сейчас я не хочу есть" if satiety >= 60 else "Сейчас я голодна"

    trust = waifu.get("trust") or 0

    marriage_text = (
        "💍 Состоит в браке с хозяином"
        if waifu.get("is_married")
        else "Холост/Не замужем"
    )

    days_together_str = (
        format_count(days_together, "день", "дня", "дней")
        if isinstance(days_together, int)
        else "?"
    )

    return (
        f"Мяу, хозяин.\n\n"
        f"Меня зовут {cat_name}, я {display_category(age_days)}\n"
        f"Я с тобой с {format_iso_date(date_cat)} — уже {days_together_str}!\n"
        f"Мой возраст: {format_count(age_days, 'день', 'дня', 'дней')}\n"
        f"Наш уровень доверия: {trust}%\n"
        f"{marriage_text}\n\n"
        f"{hunger_line}, поэтому моё настроение {mood}\n"
        f"Если тебе интересно, что ещё можно со мной сделать — <i>ссылка на гайд</i>"
    )


def _norm(text: str | None) -> str:
    return (text or "").lower().replace("ё", "е").strip()


def _pick_default_image() -> str | None:
    """Берёт случайное фото из папки cats_pic."""
    folder = os.path.join(os.getcwd(), "cats_pic")
    if not os.path.isdir(folder):
        return None
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    image_files = [
        f for f in files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
    ]
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
    try:
        last_update_str = waifu.get("last_satiety_update")
        try:
            last_dt = (
                datetime.fromisoformat(last_update_str) if last_update_str else None
            )
            if last_dt and last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            last_dt = None

        if not last_dt:
            return False

        now = datetime.now(timezone.utc)
        age_days = waifu.get("age_days") or 1

        # Базовый интервал — 5 часов. Каждые 30 дней возраста добавляют 1 час к интервалу.
        # Максимум замедляем до 12 часов.
        interval_hours = min(12, 5 + (age_days // 30))

        hours = (now - last_dt).total_seconds() // 3600
        steps = int(hours // interval_hours)
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
    except Exception as e:
        logger.error(f"Ошибка при уменьшении сытости для {waifu.get('user_id')}: {e}")
        return False


@waifu_cat_router.message(Command("my_cat"))
@waifu_cat_router.message(
    F.text.lower().in_(["моя кошка", "моя кошкожена", "мой котёнок"])
)
async def show_my_cat(message: Message) -> None:
    """
    Показывает информацию о своей кошко-жене.
    """
    try:
        viewer_id = message.from_user.id
        target_id = viewer_id

        waifu = await get_waifu_by_user(target_id)
        if not waifu:
            await message.answer(
                "Мяу! У тебя пока нет кошко-жены. 😿\n\n"
                "Она появится автоматически, когда твой рейтинг социального кредита достигнет <b>500</b>!"
            )
            return

        # Декремент сытости по времени
        await _apply_satiety_decay(waifu)

        # Проверяем брак
        marriage = await get_marriage(target_id)
        waifu["is_married"] = marriage is not None

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
            now = datetime.now(timezone.utc)
            last_update_str = waifu.get("last_age_update")
            try:
                last_dt = (
                    datetime.fromisoformat(last_update_str) if last_update_str else None
                )
                if last_dt and last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                last_dt = None
            delta_days = (now - last_dt).days if last_dt else 0
            if delta_days > 0:
                new_age = (waifu.get("age_days") or 1) + delta_days
                if await update_waifu_age(target_id, new_age, now.isoformat()):
                    waifu["age_days"] = new_age
                    waifu["last_age_update"] = now.isoformat()

        # Подтянуть/установить изображение
        image_path = waifu.get("cats_pic")
        if not image_path:
            image_path = _pick_default_image()
            if image_path:
                await update_cat_image(target_id, image_path)
                waifu["cats_pic"] = image_path

        caption = _format_waifu_profile(waifu)

        if image_path and os.path.isfile(image_path):
            photo = FSInputFile(image_path)
            await message.answer_photo(photo, caption=caption)
        else:
            await message.answer(caption)
    except Exception as e:
        logger.error(f"Ошибка в show_my_cat: {e}")
        await message.answer("Не удалось загрузить профиль кошки.")


@waifu_cat_router.message(Command("abandon_waifu"))
@waifu_cat_router.message(F.text.lower() == "отказаться от жены")
async def abandon_waifu_request(message: Message) -> None:
    """Инициирует процесс отказа от кошко-жены."""
    try:
        user_id = message.from_user.id
        waifu = await get_waifu_by_user(user_id)

        if not waifu:
            await message.answer(
                "У вас нет кошко-жены, от которой можно было бы отказаться."
            )
            return

        await message.reply(
            "⚠️ <b>ПРЕДУПРЕЖДЕНИЕ</b>\n\n"
            "Вы собираетесь отказаться от своей кошко-жены. Это действие необратимо и она навсегда покинет вас.\n\n"
            "Если вы уверены в своем решении, <b>ответьте на это сообщение</b> текстом:\n"
            "<code>точно отказываюсь</code>"
        )
    except Exception as e:
        logger.error(f"Ошибка в abandon_waifu_request: {e}")
        await message.answer(
            "Произошла ошибка при обработке запроса. Попробуйте позже."
        )


@waifu_cat_router.message(F.reply_to_message & F.text.lower() == "точно отказываюсь")
async def abandon_waifu_confirm(message: Message) -> None:
    """Подтверждение отказа от кошко-жены через reply."""
    try:
        user_id = message.from_user.id

        # Проверяем, что это ответ именно на сообщение бота (опционально, но желательно)
        if not message.reply_to_message.from_user.is_bot:
            return

        # Проверяем, что в сообщении бота было слово "отказаться" (чтобы не сработало на любой реплай)
        if (
            not message.reply_to_message.text
            or "отказаться" not in message.reply_to_message.text.lower()
        ):
            return

        deleted = await delete_waifu_by_user(user_id)
        if deleted:
            await message.answer(
                "💔 Ваша кошко-жена грустно мяукнула на прощание и ушла... Теперь вы снова один."
            )
        else:
            await message.answer(
                "Техническая ошибка: не удалось удалить запись. Возможно, у вас уже нет жены."
            )
    except Exception as e:
        logger.error(f"Ошибка в abandon_waifu_confirm: {e}")
        await message.answer("Произошла ошибка при подтверждении. Попробуйте позже.")


@waifu_cat_router.message(Command("all_waifus"))
@waifu_cat_router.message(F.text.lower() == "список жен")
async def show_all_waifus_command(message: Message) -> None:
    """Выводит список всех жен (только для админов)."""
    try:
        if not await is_admin(message.from_user.id):
            return

        waifus = await get_all_waifus_with_owners()
        if not waifus:
            await message.answer("В базе данных пока нет ни одной кошко-жены.")
            return

        text = "📂 <b>Список всех кошко-жен в системе:</b>\n\n"
        for w in waifus:
            # Пытаемся получить имя или ссылку
            owner_name = w.get("nickname") or w.get("username") or str(w.get("user_id"))
            owner_link = get_user_link(w["user_id"], owner_name)

            # Определяем статус по возрасту
            age = w.get("age_days", 0)
            if age <= 30:
                status = "котенок"
            elif age <= 120:
                status = "кошка-студентка"
            else:
                status = "милфа-кошка"

            text += f"• {owner_link} — {w.get('cat_name', 'без имени')} — {age} дн. ({status})\n"

        await message.answer(text)
    except Exception as e:
        logger.error(f"Ошибка в show_all_waifus_command: {e}")
        await message.answer("Ошибка при получении списка.")


@waifu_cat_router.message(Command("clear_waifus"))
@waifu_cat_router.message(F.text.lower() == "сброс жен")
async def clear_waifus_command(message: Message) -> None:
    """Полностью очищает базу жен (только для админов)."""
    try:
        if not await is_admin(message.from_user.id):
            return

        count = await clear_all_waifus()
        await message.answer(
            f"✅ База данных очищена. Удалено {count} записей о женах."
        )
    except Exception as e:
        logger.error(f"Ошибка в clear_waifus_command: {e}")
        await message.answer("Ошибка при очистке базы.")


@waifu_cat_router.message(
    F.text.lower().func(
        lambda t: t.startswith("кошка ") and ("@" in t or "https://" in t)
    )
)
async def show_user_cat(message: Message, command: CommandObject = None) -> None:
    """
    Показывает информацию о кошко-жене другого пользователя.
    """
    try:
        text = message.text.strip() if message.text else ""
        target_id = None

        if message.reply_to_message:
            target_user = message.reply_to_message.from_user
            target_id = target_user.id
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
                await message.answer(
                    f"Не удалось найти гражданина '{mention_part}' в системе."
                )
                return

        waifu = await get_waifu_by_user(target_id)
        if not waifu:
            await message.answer("У этого пользователя пока нет кошки.")
            return

        await _apply_satiety_decay(waifu)

        marriage = await get_marriage(target_id)
        waifu["is_married"] = marriage is not None

        chat = message.chat
        is_member = True
        if chat.type in {"group", "supergroup"}:
            try:
                member = await message.bot.get_chat_member(chat.id, target_id)
                is_member = member.status not in {"left", "kicked"}
            except Exception:
                is_member = False

        if is_member:
            now = datetime.now(timezone.utc)
            last_update_str = waifu.get("last_age_update")
            try:
                last_dt = (
                    datetime.fromisoformat(last_update_str) if last_update_str else None
                )
                if last_dt and last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                last_dt = None
            delta_days = (now - last_dt).days if last_dt else 0
            if delta_days > 0:
                new_age = (waifu.get("age_days") or 1) + delta_days
                if await update_waifu_age(target_id, new_age, now.isoformat()):
                    waifu["age_days"] = new_age
                    waifu["last_age_update"] = now.isoformat()

        image_path = waifu.get("cats_pic")
        if not image_path:
            image_path = _pick_default_image()
            if image_path:
                await update_cat_image(target_id, image_path)
                waifu["cats_pic"] = image_path

        caption = _format_waifu_profile(waifu)
        owner_ref = get_user_link(target_id, "гражданин")
        caption = f"Кошка {owner_ref}\n\n" + caption

        if image_path and os.path.isfile(image_path):
            photo = FSInputFile(image_path)
            await message.answer_photo(photo, caption=caption, parse_mode="HTML")
        else:
            await message.answer(caption, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в show_user_cat: {e}")
        await message.answer("Не удалось загрузить профиль кошки этого пользователя.")


@waifu_cat_router.message(Command("rename_cat"))
@waifu_cat_router.message(F.text.lower().startswith("изменить кличку"))
async def rename_cat(message: Message, command: CommandObject = None) -> None:
    """
    Меняет кличку кошко-жены. Пользователь может менять только свою.
    """
    try:
        user_id = message.from_user.id

        if command and command.args:
            new_name = command.args.strip()
        elif message.text and message.text.lower().startswith("изменить кличку"):
            new_name = message.text[len("изменить кличку") :].strip()
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
            await message.answer(f"Хорошо, теперь меня зовут {new_name}.")
        else:
            await message.answer("Не удалось изменить кличку. Попробуй ещё раз.")
    except Exception as e:
        logger.error(f"Ошибка в rename_cat: {e}")
        await message.answer("Произошла ошибка при смене клички.")


FEED_COOLDOWN_HOURS = 3  # Минимальный интервал между кормлениями

# Шуточные фразы, когда кошка ещё не голодна
_TOO_EARLY_PHRASES = [
    "Мяу? Хозяин, я только что поела! Подожди немного, хорошо? 😾 Напомню, когда снова захочу кушать~",
    "*смотрит на миску, потом на тебя* Хозяин, ты меня что, откармливать собрался? Ещё рано! 🐾",
    "Мур-мур... Я благодарна, но я ещё сыта! Скоро сама дам знать, когда пора за стол~ 🍽️",
    "Нет-нет-нет! Кошки не едят когда попало, мы существа с расписанием! Подожди, хозяин 😤",
    "*отворачивает морду от миски* Спасибо, но рано. Я напомню, когда придёт время~ 🌸",
]


def _get_feeding_bonus(hour: int) -> tuple[int, str]:
    """
    Возвращает бонус к сытости в зависимости от времени суток.

    - Утро (6-12): +20 бонус → сытость 100
    - Вечер (18-24): +20 бонус → сытость 100
    - День/Ночь (остальное): 0 бонус → сытость 80

    Returns:
        (bonus, time_period_name)
    """
    if 6 <= hour < 12:
        return 20, "утром"
    elif 18 <= hour < 24:
        return 20, "вечером"
    else:
        return 0, "днём"


@waifu_cat_router.message(Command("feed_korm"))
@waifu_cat_router.message(
    F.text.lower().in_(["дать корм", "покормить кормом", "вкусняшка"])
)
async def feed_waifu_korm(message: Message) -> None:
    """
    Кормление кормом или рисом.

    Новая механика:
    - Можно кормить в любое время суток
    - Утром (6-12) и вечером (18-24): сытость восстанавливается до 100 + доверие +5
    - В другое время: сытость восстанавливается до 80 + доверие +3
    - Минимальный интервал между кормлениями: 3 часа
    """
    try:
        user_id = message.from_user.id
        waifu = await get_waifu_by_user(user_id)
        if not waifu:
            await message.answer("У тебя пока нет кошко-жены.")
            return

        cat_name = waifu.get("cat_name") or "мяу"
        now = datetime.now(timezone.utc)

        # Определяем локальное время для расчета бонусов
        local_now = now.astimezone()
        hour = local_now.hour

        from datetime import timedelta

        # Проверяем кулдаун (минимум 3 часа между кормлениями)
        last_feed_str = waifu.get("last_feed_time")
        if last_feed_str:
            try:
                last_feed_dt = datetime.fromisoformat(last_feed_str)
                if last_feed_dt.tzinfo is None:
                    last_feed_dt = last_feed_dt.replace(tzinfo=timezone.utc)

                time_since_feed = (now - last_feed_dt).total_seconds() / 3600  # в часах

                if time_since_feed < FEED_COOLDOWN_HOURS:
                    remaining_hours = FEED_COOLDOWN_HOURS - time_since_feed
                    remaining_h = int(remaining_hours)
                    remaining_m = int((remaining_hours - remaining_h) * 60)
                    time_str = (
                        f"{remaining_h} ч. {remaining_m} мин."
                        if remaining_h > 0
                        else f"{remaining_m} мин."
                    )

                    phrase = random.choice(_TOO_EARLY_PHRASES)
                    await message.answer(
                        f"{phrase}\n\n⏰ <b>Я снова проголодаюсь через:</b> {time_str}",
                        parse_mode="HTML",
                    )
                    return
            except (ValueError, TypeError):
                pass  # Если формат даты плохой — пропускаем проверку

        # --- Проверяем наличие корма или риса ---
        hebao = await get_hebao_items(user_id)
        korm_item = next((i for i in hebao if i["item_key"] == "korm_waifu"), None)
        korm_qty = korm_item["quantity"] if korm_item else 0

        rice_item = next((i for i in hebao if i["item_key"] == "miska_risa"), None)
        rice_qty = rice_item["quantity"] if rice_item else 0

        if korm_qty <= 0 and rice_qty <= 0:
            await message.answer(
                f"😿 {cat_name}: «Хозяин, еда закончилась... Мяу...»\n"
                "У вас нет корма или риса для кошко-жены!"
            )
            return

        # --- Тратим еду ---
        consumed_name = ""
        left_qty = 0
        if korm_qty > 0:
            await upsert_hebao_item(user_id, "korm_waifu", delta=-1)
            left_qty = korm_qty - 1
            consumed_name = "корм"
        else:
            await upsert_hebao_item(user_id, "miska_risa", delta=-1)
            left_qty = rice_qty - 1
            consumed_name = "миска риса"

        # --- Рассчитываем бонусы по времени суток ---
        satiety_bonus, time_period = _get_feeding_bonus(hour)
        base_satiety = 80
        final_satiety = min(100, base_satiety + satiety_bonus)

        trust_bonus = 5 if satiety_bonus > 0 else 3

        # --- Повышаем статы ---
        now_iso = now.isoformat()
        await update_cat_state(
            user_id,
            satiety=final_satiety,
            mood=_compute_mood(final_satiety),
            last_satiety_update=now_iso,
            last_feed_time=now_iso,
        )
        await update_waifu_trust(user_id, trust_bonus)

        # Получаем актуальное доверие после обновления
        waifu_updated = await get_waifu_by_user(user_id)
        new_trust = (
            (waifu_updated.get("trust") or 0)
            if waifu_updated
            else (waifu.get("trust") or 0) + trust_bonus
        )
        new_trust = min(100, new_trust)

        # --- Формируем сообщение ---
        bonus_text = ""
        if satiety_bonus > 0:
            bonus_text = f"\n✨ <b>Бонус за кормление {time_period}:</b> +{satiety_bonus}% сытости, +{trust_bonus} доверия!"
        else:
            bonus_text = f"\n💡 <i>Совет: кормите {cat_name} утром (6:00-12:00) или вечером (18:00-00:00) для максимального эффекта!</i>"

        await message.answer(
            f"✨ {cat_name} с урчанием набросилась на еду — <b>вкусняшка!</b>\n\n"
            f"🍽️ <b>Сытость:</b> {final_satiety}%\n"
            f"❤️ <b>Уровень доверия:</b> {new_trust}% (+{trust_bonus})\n"
            f"🎒 <b>Осталось ({consumed_name}):</b> {left_qty} шт."
            f"{bonus_text}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Ошибка в feed_waifu_korm: {e}")
        await message.answer("Ошибка при использовании корма.")


@waifu_cat_router.message(Command("propose"))
@waifu_cat_router.message(
    F.text.lower().in_(["сделать предложение", "выйди за меня", "стань моей женой"])
)
async def propose_handler(message: Message) -> None:
    """Команда предложения брака."""
    try:
        user_id = message.from_user.id
        waifu = await get_waifu_by_user(user_id)

        if not waifu:
            await message.answer(
                "У вас нет кошко-жены, кому вы хотите сделать предложение? 🧐"
            )
            return

        # Проверяем, не женаты ли уже
        marriage = await get_marriage(user_id)
        if marriage:
            await message.answer(
                f"Вы уже состоите в официальном браке с {waifu.get('cat_name', 'кошечкой')}! 💞"
            )
            return

        trust = waifu.get("trust") or 0
        cat_name = waifu.get("cat_name") or "кошечка"

        await message.answer(
            f"💖 Вы встаете на одно колено и протягиваете кольцо {cat_name}..."
        )
        await asyncio.sleep(2)  # Драматическая пауза

        # Шанс успеха = trust (минимум 5%, максимум 100%)
        chance = max(5, trust)
        roll = random.randint(1, 100)

        if roll <= chance:
            # Успех!
            await register_marriage(user_id, waifu["cats_id"])
            await message.answer(
                f"🎊 <b>ОНА СКАЗАЛА «ДА»!</b> 🎊\n\n"
                f"{cat_name} со слезами счастья на глазах принимает ваше предложение! "
                f"Теперь вы официально муж и жена. Поздравляем! 🥂💍✨"
            )
        else:
            # Отказ
            refusal_phrases = [
                f"{cat_name} смущенно отводит взгляд: «Извини, хозяин, я еще не готова к такому серьезному шагу...» 😿",
                f"«Мяу... Ты очень добр ко мне, но нам нужно узнать друг друга получше», — ответила {cat_name}. 🐾",
                f"{cat_name} хитро улыбнулась: «Моё сердце еще не полностью принадлежит тебе, постарайся получше!» 🎀",
            ]
            await message.answer(random.choice(refusal_phrases))
    except Exception as e:
        logger.error(f"Ошибка в propose_handler: {e}")
        await message.answer("Произошла ошибка при регистрации брака.")


@waifu_cat_router.message(Command("get_food"))
@waifu_cat_router.message(F.text.lower().in_(["получить корм", "взять корм"]))
async def get_daily_food_command(message: Message) -> None:
    """Команда для получения 5 корма или 5 риса (раз в день)."""
    try:
        user_id = message.from_user.id

        # Проверяем кулдаун
        can_receive = await can_receive_daily_food(user_id)
        if not can_receive:
            await message.answer(
                "🐾 Вы уже получали еду сегодня! Возвращайтесь завтра."
            )
            return

        # Рандом 50/50: 5 корма или 5 риса
        item_key = "korm_waifu" if random.random() < 0.5 else "miska_risa"
        item_name = "корм кошко-жены" if item_key == "korm_waifu" else "миска риса"
        item_icon = "🥫" if item_key == "korm_waifu" else "🍚"

        # Начисляем предметы
        await upsert_hebao_item(user_id, item_key, item_name, delta=5)

        # Обновляем таймер
        await update_daily_food_time(user_id)

        await message.answer(
            f"🎁 <b>Бесплатная еда получена!</b>\n\n"
            f"Вы заглянули в кладовую и взяли:\n"
            f"{item_icon} <b>{item_name}</b> (5 шт.)\n\n"
            f"<i>Заглядывайте завтра за новой порцией!</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Ошибка в get_daily_food_command: {e}")
        await message.answer("Произошла ошибка при получении корма.")
