from aiogram import Router, F
from aiogram.filters.command import Command, CommandObject
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import datetime
from database import (
    add_user,
    get_user_nickname,
    set_user_nickname,
    set_user_description,
    get_user_description,
    get_user_rate,
    get_all_admins,
    get_rate_status,
    get_user_by_username,
    get_user_city,
    set_user_city,
)
from routers.utils import (
    extract_user_from_text,
    resolve_user_id,
    get_user_link,
    get_profile_text,
    get_rate_display,
    extract_args,
)
from routers.weather_service import get_weather_string
from routers.strings import HELP_TEXT

import logging

logger = logging.getLogger(__name__)

user_router = Router()  # подключение роутеров


class RegistrationStates(StatesGroup):
    waiting_for_nickname = State()
    waiting_for_city = State()
    waiting_for_description = State()


# Utility functions moved to routers/utils.py


@user_router.message(Command("start"), F.chat.type == "private")
async def start_handler(message: Message, state: FSMContext) -> None:
    try:
        user_id = message.from_user.id
        first_name = message.from_user.first_name or "гражданин"

        nickname = await get_user_nickname(user_id)
        city = await get_user_city(user_id)
        description = await get_user_description(user_id)

        if not nickname and not city and not description:
            # Полностью новый гражданин
            await add_user(user_id, first_name, message.from_user.username)
            await message.answer(
                f"🌸 Добро пожаловать, {first_name}. Ваш профиль загружен в систему. Партия гордится Вами!\n\n"
                f"Для начала давайте составим Ваше досье. Это обязательно для каждого достойного гражданина. 🇨🇳\n\n"
                f"<b>Как нам к Вам обращаться? (Ваш ник):</b>"
            )
            await state.set_state(RegistrationStates.waiting_for_nickname)
            return

        # Пользователь уже есть в системе, проверяем недостающие данные
        greeting_name = nickname or first_name
        missing_parts = []
        if not nickname:
            missing_parts.append(
                "ника (используйте команду <code>.ник [Ваш ник]</code>)"
            )
        if not city:
            missing_parts.append(
                "гОрода (поможет узнавать погоду утром, используйте команду <code>.город [Ваш город]</code>)"
            )
        if not description:
            missing_parts.append(
                "описания (расскажите о себе, используя команду <code>.описание [Ваш текст]</code>)"
            )

        if missing_parts:
            missing_text = "\n• ".join(missing_parts)
            if len(missing_parts) == 1:
                intro_text = (
                    "Мы заметили, что в Вашем досье не хватает следующего пункта:"
                )
            else:
                intro_text = (
                    "Мы заметили, что в Вашем досье не хватает некоторых данных:"
                )

            await message.answer(
                f"Приветствуем Вас снова, {greeting_name}! 👋\nПартия рада Вашему возвращению.\n\n"
                f"{intro_text}\n"
                f"• {missing_text}\n\n"
                f"Пожалуйста, заполните их для полноценного участия в жизни общества! 🇨🇳"
            )
        else:
            await message.answer(
                f"Приветствуем Вас снова, {greeting_name}! 👋\nПартия рада Вашему возвращению.\n\n"
                f"Ваше досье полностью заполнено! Партия гордится Вами. 🌟\n\n"
                f"Если захотите обновить данные, Вы всегда можете использовать команды:\n"
                f"<code>.ник [Ник]</code>\n<code>.город [Город]</code>\n<code>.описание [Описание]</code>"
            )
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка в start_handler: {e}")
        await message.answer("Произошла ошибка при запуске. Попробуйте позже.")


# Хендлеры анкеты (Регистрация)


@user_router.message(RegistrationStates.waiting_for_nickname, F.chat.type == "private")
async def process_nickname(message: Message, state: FSMContext) -> None:
    try:
        if not message.text:
            return
        new_nickname = message.text.strip()
        if not new_nickname:
            await message.answer(
                "❌ Ошибка: Имя не может быть пустым. Пожалуйста, напишите Ваш ник:"
            )
            return

        await set_user_nickname(message.from_user.id, new_nickname)
        await message.answer(
            f"✅ Принято, {new_nickname}! Теперь Партии нужно знать Ваше местоположение для точного прогноза погоды. 📍\n"
            f"<b>Напишите Ваш город:</b>"
        )
        await state.set_state(RegistrationStates.waiting_for_city)
    except Exception as e:
        logger.error(f"Ошибка в process_nickname: {e}")
        await message.answer("Ошибка сохранения ника.")


@user_router.message(RegistrationStates.waiting_for_city, F.chat.type == "private")
async def process_city(message: Message, state: FSMContext) -> None:
    try:
        if not message.text:
            return
        city = message.text.strip()
        if not city:
            await message.answer(
                "❌ Ошибка: Город не может быть пустым. Пожалуйста, напишите Ваш город:"
            )
            return

        await set_user_city(message.from_user.id, city)
        await message.answer(
            f"✅ Город {city} закреплен за Вами. И последнее — расскажите немного о себе для Вашего досье. 📄\n"
            f"<b>Напишите Ваше описание:</b>"
        )
        await state.set_state(RegistrationStates.waiting_for_description)
    except Exception as e:
        logger.error(f"Ошибка в process_city: {e}")
        await message.answer("Ошибка сохранения города.")


@user_router.message(
    RegistrationStates.waiting_for_description, F.chat.type == "private"
)
async def process_description(message: Message, state: FSMContext) -> None:
    try:
        if not message.text:
            return
        description = message.text.strip()
        if not description:
            await message.answer(
                "❌ Ошибка: Описание не может быть пустым. Пожалуйста, расскажите о себе:"
            )
            return

        await set_user_description(message.from_user.id, description)
        await state.clear()

        # Вывод досье в конце регистрации
        profile_text = await get_profile_text(message.from_user.id)
        await message.answer(
            f"🎊 Поздравляем! Ваша регистрация завершена. Партия гордится Вами! 🇨🇳\n\n{profile_text}"
        )
    except Exception as e:
        logger.error(f"Ошибка в process_description: {e}")
        await message.answer("Ошибка сохранения описания.")


# Команды изменения профиля (только в ЛС)


@user_router.message(Command("set_nickname"), F.chat.type == "private")
@user_router.message(
    F.text.lower().startswith((".ник ", "ник ", "/set_nickname ")),
    F.chat.type == "private",
)
async def set_nickname_handler(message: Message) -> None:
    try:
        user_id = message.from_user.id
        text = message.text or ""

        new_nickname = extract_args(text, ["/set_nickname", ".ник", "ник"])

        if not new_nickname:
            await message.answer(
                "📝 Ошибка: Пожалуйста, укажите новое имя после команды.\nПример: <code>.ник Любитель Пива</code>"
            )
            return

        await set_user_nickname(user_id, new_nickname)
        await message.answer(f"✅ Ваше учётное имя успешно изменено на {new_nickname}")
    except Exception as e:
        logger.error(f"Ошибка в set_nickname_handler: {e}")
        await message.answer("Не удалось сменить ник.")


@user_router.message(
    F.text.lower().startswith((".ник ", "ник ")), F.chat.type != "private"
)
async def set_nickname_group_stub(message: Message) -> None:
    """Заглушка для попытки сменить ник в группе."""
    await message.reply(
        "⚠️ Гражданин, изменение учётных данных (ника, описания, города) разрешено только в <b>личных сообщениях</b> бота. 🇨🇳"
    )


@user_router.message(F.text.lower().in_([".ник", "ник", "мой ник"]))
async def show_my_nickname(message: Message) -> None:
    """Просмотр ника работает везде."""
    try:
        user_id = message.from_user.id
        nickname = await get_user_nickname(user_id)

        if nickname:
            await message.answer(f"📝 Твой текущий ник: <b>{nickname}</b>")
        else:
            await message.answer("Я тебя ещё не знаю. Напиши /start для регистрации.")
    except Exception as e:
        logger.error(f"Ошибка в show_my_nickname: {e}")


@user_router.message(Command("set_description"), F.chat.type == "private")
@user_router.message(
    F.text.lower().startswith((".описание ", "описание ", "/set_description ")),
    F.chat.type == "private",
)
async def set_description_handler(message: Message) -> None:
    try:
        user_id = message.from_user.id
        text = message.text or ""

        description = extract_args(text, ["/set_description", ".описание", "описание"])

        if not description:
            await message.answer(
                "📝 Ошибка: Пожалуйста, укажите новое описание после команды.\nПример: <code>.описание Люблю светлое пиво</code>"
            )
            return

        await set_user_description(user_id, description)
        await message.answer(f"✅ Ваше описание успешно изменено.")
    except Exception as e:
        logger.error(f"Ошибка в set_description_handler: {e}")
        await message.answer("Не удалось сменить описание.")


@user_router.message(
    F.text.lower().startswith((".описание ", "описание ")), F.chat.type != "private"
)
async def set_description_group_stub(message: Message):
    await message.reply(
        "⚠️ Гражданин, изменение описания разрешено только в <b>личных сообщениях</b> бота. 🇨🇳"
    )


@user_router.message(Command("set_city"), F.chat.type == "private")
@user_router.message(
    F.text.lower().startswith((".город", "город", "/set_city", "сменить город")),
    F.chat.type == "private",
)
async def set_city_command_handler(message: Message, state: FSMContext) -> None:
    try:
        text = message.text or ""
        city = extract_args(text, ["/set_city", ".город", "город", "сменить город"])

        if city:
            await set_user_city(message.from_user.id, city)
            await message.answer(f"✅ Город <b>{city}</b> успешно закреплен за Вами.")
            await state.clear()
        else:
            await message.answer("📍 Напишите Ваш город:")
            await state.set_state(RegistrationStates.waiting_for_city)
    except Exception as e:
        logger.error(f"Ошибка в set_city_command_handler: {e}")
        await message.answer("Не удалось сменить город.")


@user_router.message(
    F.text.lower().startswith((".город ", "город ", "сменить город ")),
    F.chat.type != "private",
)
async def set_city_group_stub(message: Message):
    await message.reply(
        "⚠️ Гражданин, изменение города разрешено только в <b>личных сообщениях</b> бота. 🇨🇳"
    )


# Обработка города (уже есть выше в RegistrationStates)


@user_router.message(Command("weather", "weather", "погода"))
@user_router.message(F.text.lower().startswith("погода"))
async def weather_command_handler(
    message: Message, command: CommandObject = None
) -> None:
    """Хендлер для команды /weather {город} или сообщения 'погода {город}'."""
    try:
        city = None

        if command and command.args:
            city = command.args.strip()
        elif message.text:
            # Пытаемся извлечь город из текста "погода город"
            parts = message.text.split(maxsplit=1)
            if len(parts) > 1:
                city = parts[1].strip()

        if not city:
            # Если город не указан, попробуем взять из БД
            city = await get_user_city(message.from_user.id)

        if not city:
            await message.answer(
                "📍 Пожалуйста, укажите город после команды или установите его в профиле через /set_city.\nПример: <code>/weather Москва</code>"
            )
            return

        # Получаем погоду (краткую версию)
        weather_info = await get_weather_string(city_name=city, concise=True)

        if weather_info:
            await message.answer(weather_info)
        else:
            await message.answer(
                f"❌ Не удалось получить данные о погоде для города <b>{city}</b>. Проверьте правильность написания."
            )
    except Exception as e:
        logger.error(f"Ошибка в weather_command_handler: {e}")
        await message.answer("Ошибка при запросе погоды.")


# Роутер 'Анкета' - выводит анкету с данными в лс бота(будет отличаться от профиля внутри чата(возможно))


@user_router.message(Command("anketa"))
@user_router.message(F.text.lower().in_(["анкета", "досье", ".анкета", ".досье"]))
async def profile_handler(message: Message) -> None:
    """Отправляет гражданину его анкету (работает везде)."""
    try:
        user_id = message.from_user.id

        # Проверяем, зарегистрирован ли пользователь
        nickname = await get_user_nickname(user_id)
        if not nickname:
            await message.reply(
                "❓ У вас ещё нет досье в системе.\nНапишите /start для регистрации."
            )
            return

        profile_text = await get_profile_text(user_id)
        await message.answer(profile_text)
    except Exception as e:
        logger.error(f"Ошибка в profile_handler: {e}")
        await message.answer("Не удалось загрузить анкету.")


# Роутеры удаления (только в ЛС)


@user_router.message(Command("delete_nickname"), F.chat.type == "private")
@user_router.message(
    F.text.lower().in_(
        ["удалить ник", "удалить имя", ".удалить ник", ".удалить имя", "сбросить ник"]
    ),
    F.chat.type == "private",
)
async def reset_nickname_handler(message: Message) -> None:
    """Сбрасывает ник гражданина к его имени в Telegram (только в ЛС)."""
    try:
        user_id = message.from_user.id
        first_name = message.from_user.first_name or "гражданин"

        await set_user_nickname(user_id, first_name)
        await message.answer(
            f"🗑️ Ваше имя успешно отправлено в ссылку. Теперь Вы снова {first_name}."
        )
    except Exception as e:
        logger.error(f"Ошибка в reset_nickname_handler: {e}")
        await message.answer("Ошибка при удалении ника.")


@user_router.message(
    F.text.lower().in_(["удалить ник", "удалить имя", ".удалить ник", ".удалить имя"]),
    F.chat.type != "private",
)
async def reset_nickname_group_stub(message: Message):
    await message.reply(
        "⚠️ Гражданин, удаление ника разрешено только в <b>личных сообщениях</b> бота. 🇨🇳"
    )


@user_router.message(Command("delete_description"), F.chat.type == "private")
@user_router.message(
    F.text.lower().in_(
        [
            "удалить описание",
            "очистить описание",
            ".удалить описание",
            ".очистить описание",
        ]
    ),
    F.chat.type == "private",
)
async def clear_description_handler(message: Message):
    """Очищает описание профиля гражданина (только в ЛС)."""
    user_id = message.from_user.id
    await set_user_description(user_id, None)
    await message.answer("🗑️ Ваше описание успешно отправлено в ссылку.")


@user_router.message(
    F.text.lower().in_(
        [
            "удалить описание",
            "очистить описание",
            ".удалить описание",
            ".очистить описание",
        ]
    ),
    F.chat.type != "private",
)
async def clear_description_group_stub(message: Message):
    await message.reply(
        "⚠️ Гражданин, удаление описания разрешено только в <b>личных сообщениях</b> бота. 🇨🇳"
    )


# Роутер выводит ник гражданина - уже обработан выше как show_my_nickname


# Роутер выводит описание гражданина
@user_router.message(F.text.lower().in_(["моё описание", "описание"]))
async def show_my_description(message: Message) -> None:
    try:
        user_id = message.from_user.id
        description = await get_user_description(user_id)

        if description:
            await message.answer(f"📄 Твоё описание:\n<i>{description}</i>")
        else:
            await message.answer(
                "У тебя пока нет описания. Можешь добавить его командой <code>/set_description</code>."
            )
    except Exception as e:
        logger.error(f"Ошибка в show_my_description: {e}")


# Роутер выводит рейтинг гражданина
@user_router.message(Command("my_rate"))
@user_router.message(F.text.lower().in_(["мой рейтинг", "рейтинг"]))
async def my_rate(message: Message) -> None:
    try:
        user_id = message.from_user.id

        # Проверяем, зарегистрирован ли пользователь
        nickname = await get_user_nickname(user_id)
        if not nickname:
            await message.reply(
                "❓ Вы ещё не зарегистрированы в системе.\n"
                "Напишите /start для регистрации и получения социального рейтинга."
            )
            return

        rate_display = await get_rate_display(user_id)
        await message.reply(rate_display)
    except Exception as e:
        logger.error(f"Ошибка в my_rate: {e}")
        await message.answer("Не удалось загрузить рейтинг.")


# Роутер-пинг. банально.
@user_router.message(Command("ping"))
@user_router.message(F.text.lower().in_(["пинг", "социальный пинг-понг"]))
async def ping_bot(message: Message) -> None:
    try:
        # Засекаем время перед отправкой тестового сообщения
        start_time = datetime.datetime.now()
        sent_message = await message.answer("🤖 Измеряю пинг...")
        end_time = datetime.datetime.now()

        # Считаем точное время отклика серверов Telegram
        delta = end_time - start_time
        ev_ms = round(delta.total_seconds() * 1000, 2)

        # Устанавливаем порог (например, 500 мс)
        ping_threshold_ms = 500.0

        # Проверяем значение пинга и выбираем текст ответа
        if ev_ms < ping_threshold_ms:
            out = f"🏓 Партия выиграла в пинг-понг за <code>{ev_ms}</code> мс"
        else:
            out = f"🏓 Партия проиграла в пинг-понг за <code>{ev_ms}</code> мс"

        # Редактируем сообщение с окончательным ответом
        await sent_message.edit_text(out)
    except Exception as e:
        logger.error(f"Ошибка в ping_bot: {e}")


# Роутер вывода списка администраторов
@user_router.message(Command("adminlist"))
@user_router.message(
    F.text.lower().in_(
        ["кто админ", "админы", "кто администратор", "кто смотритель", ".партия"]
    )
)
async def admin_list_command(message: Message) -> None:
    try:
        admins = await get_all_admins()
        if not admins:
            await message.answer("Список смотрителей пуст.")
            return

        admin_list_text = "<b>🎓 Наши смотрители:</b>\n"
        for user_id, first_name in admins:
            admin_list_text += f"– {get_user_link(user_id, first_name)}\n"

        await message.answer(admin_list_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в admin_list_command: {e}")


@user_router.message(
    F.text.lower().func(lambda t: t.startswith("ид ") or t == "мой ид")
)
async def show_user_id(message: Message, command: CommandObject = None) -> None:
    """
    Показывает ID гражданина.
    Команды: "мой ид", "ид @username", "ид @user_id", "ид https://t.me/username"
    """
    try:
        text = message.text.strip().lower() if message.text else ""

        target_id = None
        target_display = None

        if text == "мой ид":
            target_id = message.from_user.id
            target_display = message.from_user.full_name or "пользователь"
        else:
            # Извлекаем упоминание
            if command and command.args:
                mention_part = command.args.strip()
            elif text.startswith("ид "):
                mention_part = text[3:].strip()
            else:
                await message.reply("Укажите гражданина. Пример: ид @username")
                return

            target_id = await resolve_user_id(mention_part)
            if target_id:
                target_display = f"user_{target_id}"
            else:
                # Если не нашли по ID/меншену, возможно это просто текст (попытка найти по базе будет в resolve_user_id)
                await message.reply(f"Гражданин '{mention_part}' не найден в системе.")
                return

        # Формируем ответ
        user_link = f"<a href='tg://user?id={target_id}'>{target_display}</a>"
        response = f"Ид гражданина {user_link} - <code>{target_id}</code>"
        await message.reply(response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в show_user_id: {e}")


@user_router.message(Command("help"))
@user_router.message(F.text.lower().in_(["помощь", ".помощь"]))
async def help_command(message: Message) -> None:
    """Отправляет гражданину список доступных команд."""
    try:
        await message.answer(HELP_TEXT, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в help_command: {e}")


@user_router.message(Command("Kill"))
@user_router.message(F.text.lower().in_(["самовыпил"]))
async def Kill_command(message: Message) -> None:
    try:
        await message.answer("❌ Партия не одобряет")
    except Exception as e:
        logger.error(f"Ошибка в Kill_command: {e}")
