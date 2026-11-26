"""Модуль помощи: пошаговая справка по каждому модулю бота.

Административные и модераторские команды здесь намеренно не описаны —
это отдельная справка для смотрителей.
"""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters.command import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

logger = logging.getLogger(__name__)

help_router = Router()

# Порядок разделов и их подписи на кнопках.
SECTION_ORDER = ("start", "profile", "cat", "shelter", "economy", "activity", "rules")

SECTION_TITLES = {
    "start": "🚀 С чего начать",
    "profile": "👤 Профиль",
    "cat": "🐾 Кошко-жена",
    "shelter": "🏡 Приют",
    "economy": "🎒 Еда и хэбао",
    "activity": "📊 Активность",
    "rules": "📋 Правила",
}

SECTION_TEXT = {
    "start": """
🚀 <b>С чего начать</b>

<b>1. Зарегистрируйся</b>
Открой личные сообщения с ботом и напиши <code>/start</code>.
Бот спросит имя, город и пару слов о себе — это твоё досье.

<b>2. Получи кошко-жену</b>
Она появляется сама, когда социальный рейтинг достигает <b>500</b>.
Новому гражданину сразу дают <b>300</b>, остальное приходит за активность.

<b>3. Загляни в кладовую</b>
<code>получить корм</code> — бесплатная еда раз в день.

<b>4. Покорми кошку</b>
<code>дать корм</code> — кошка сыта и довольна.

<b>Дальше:</b> листай разделы кнопками ниже — в каждом объяснено,
что делать и какие команды использовать.
""",
    "profile": """
👤 <b>Профиль и досье</b>

<b>Регистрация</b>
<code>/start</code> — в личных сообщениях с ботом

<b>Досье</b>
<code>анкета</code> — посмотреть своё досье целиком
<code>.ник Имя</code> — сменить имя
<code>ник</code> — показать текущее имя
<code>.описание Текст</code> — рассказать о себе
<code>описание</code> — показать описание
<code>.город Город</code> — указать город
<code>погода</code> — прогноз по твоему городу

<b>Рейтинг и связь</b>
<code>мой рейтинг</code> — социальный рейтинг и звание
<code>пинг</code> — проверить, на связи ли бот
<code>ид @username</code> — узнать ID гражданина
<code>.партия</code> — список смотрителей

<i>Команды с точкой работают и в чатах, и в личных сообщениях.</i>
""",
    "cat": """
🐾 <b>Кошко-жена</b>

<b>Осмотр</b>
<code>моя кошка</code> — профиль своей кошки
<code>кошка @username</code> — посмотреть чужую

<b>Забота</b>
<code>дать корм</code> — покормить (корм или рис из хэбао)
Кормить можно раз в <b>3 часа</b>. Утром и вечером сытость
восстанавливается сильнее, и кошка больше доверяет.

<b>Имя и отношения</b>
<code>изменить кличку Луна</code> — переименовать
<code>сделать предложение</code> — позвать замуж
Шанс согласия равен уровню доверия: чем чаще кормишь, тем выше.

<code>отказаться от жены</code> — отпустить кошку навсегда

<b>Что важно</b>
Сытость постепенно падает, настроение зависит от неё.
Если кошка голодна, бот напомнит об этом.
""",
    "shelter": """
🏡 <b>Приют</b>

Уезжаешь или не успеваешь кормить? Сдай кошку в приют за еду.

<b>Цена</b>
<b>2 корма</b> или <b>3 миски риса</b> за сутки.
Максимальный срок — <b>30 дней</b>.

<b>Команды</b>
<code>приют</code> — условия и статус твоей кошки
<code>сдать кошку 3</code> — сдать на 3 дня
<code>продлить приют 2</code> — добавить 2 дня
<code>забрать из приюта</code> — вернуть домой раньше срока
<code>список приюта</code> — кто сейчас в приюте
<code>моя кошка в приюте</code> — сколько осталось

<b>Что даёт приют</b>
Кошка не голодает: сытость замирает, напоминания не приходят.
По окончании срока она возвращается сама, бот напишет об этом.

<b>Возврат еды</b>
Забираешь раньше — еда за <b>неиспользованные полные сутки</b>
возвращается тем же продуктом. Забрал через час — вернётся всё.
""",
    "economy": """
🎒 <b>Еда и хэбао</b>

Всё имущество хранится в хэбао — это твой инвентарь.

<b>Команды</b>
<code>хэбао</code> — посмотреть содержимое
<code>получить корм</code> — бесплатная еда раз в день

<b>Виды еды</b>
🥫 <b>Корм кошко-жены</b> — для кормления и оплаты приюта
🍚 <b>Миска риса</b> — то же самое, но рис дороже в приюте

<b>Сколько дают</b>
Обычно <b>5 штук</b> в день.
Пока кошка в приюте — <b>2 штуки</b>: расход еды там нулевой,
поэтому выдача меньше.

<i>Еда тратится на кормление и на приют. Копится она только
за счёт ежедневной выдачи.</i>
""",
    "activity": """
📊 <b>Активность</b>

Бот считает, сколько сообщений ты пишешь в чатах.

<b>Команды</b>
<code>стата</code> — топ самых активных граждан

<b>Зачем это нужно</b>
Активность — источник социального рейтинга.
Написал за день <b>150+ сообщений</b> — получил <b>+10</b> к рейтингу.
Доведёшь рейтинг до <b>500</b> — появится кошко-жена.

<i>Статистика работает только в тех чатах, где её включили.</i>
""",
    "rules": """
📋 <b>Правила чата</b>

<b>Команда</b>
<code>правила</code> — показать правила текущего чата

<i>Команда работает только в группах и супергруппах.
В личных сообщениях бот ответит отказом.</i>

<b>Совет новичку</b>
Прочитай правила чата до того, как писать — это экономит
время и тебе, и смотрителям.
""",
}

START_MESSAGE = """
🎓 <b>Помощь по боту</b>

Привет! Это бот про кошко-жену: её надо кормить,
баловать и иногда сдавать в приют.

<b>Три шага для новичка:</b>
1️⃣ <code>/start</code> в личных сообщениях — регистрация
2️⃣ <code>получить корм</code> — забрать бесплатную еду
3️⃣ <code>моя кошка</code> — посмотреть на свою кошку

Выбери раздел — расскажу подробно про каждый модуль.
"""


def _keyboard(section: str) -> InlineKeyboardMarkup:
    """Кнопки навигации: на главной — все разделы, внутри раздела — возврат."""
    if section == "main":
        rows = []
        for index in range(0, len(SECTION_ORDER), 2):
            row = [
                InlineKeyboardButton(
                    text=SECTION_TITLES[key], callback_data=f"help:{key}"
                )
                for key in SECTION_ORDER[index : index + 2]
            ]
            rows.append(row)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    rows = [
        [
            InlineKeyboardButton(text="◀️ Все разделы", callback_data="help:main"),
        ]
    ]
    # Подсказка на соседние разделы, чтобы не возвращаться на главную.
    position = SECTION_ORDER.index(section) if section in SECTION_ORDER else -1
    if position >= 0:
        neighbours = []
        if position > 0:
            previous = SECTION_ORDER[position - 1]
            neighbours.append(
                InlineKeyboardButton(
                    text=f"◀ {SECTION_TITLES[previous]}", callback_data=f"help:{previous}"
                )
            )
        if position + 1 < len(SECTION_ORDER):
            following = SECTION_ORDER[position + 1]
            neighbours.append(
                InlineKeyboardButton(
                    text=f"{SECTION_TITLES[following]} ▶",
                    callback_data=f"help:{following}",
                )
            )
        if neighbours:
            rows.insert(0, neighbours)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render(section: str) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и кнопки для раздела. Неизвестный раздел показывает главную."""
    if section not in SECTION_TEXT:
        section = "main"
    if section == "main":
        return START_MESSAGE, _keyboard("main")
    return SECTION_TEXT[section], _keyboard(section)


@help_router.message(Command("help"))
@help_router.message(F.text.lower().in_(["помощь", ".помощь", "хелп", "help"]))
async def help_main(message: Message) -> None:
    """Главный экран помощи."""
    try:
        text, keyboard = render("main")
        await message.answer(text, reply_markup=keyboard)
    except Exception as error:
        logger.error(f"Ошибка в help_main: {error}")
        await message.answer("Не удалось открыть помощь.")


@help_router.message(Command("help_profile"))
@help_router.message(F.text.lower().in_(["помощь профиль", "помощь досье"]))
async def help_profile(message: Message) -> None:
    """Справка по профилю."""
    await _send_section(message, "profile")


@help_router.message(Command("help_cat"))
@help_router.message(F.text.lower().in_(["помощь кошка", "помощь кошкожена"]))
async def help_cat(message: Message) -> None:
    """Справка по кошко-жене."""
    await _send_section(message, "cat")


@help_router.message(Command("help_shelter"))
@help_router.message(F.text.lower().in_(["помощь приют"]))
async def help_shelter(message: Message) -> None:
    """Справка по приюту."""
    await _send_section(message, "shelter")


@help_router.message(Command("help_economy"))
@help_router.message(F.text.lower().in_(["помощь еда", "помощь хэбао"]))
async def help_economy(message: Message) -> None:
    """Справка по еде и инвентарю."""
    await _send_section(message, "economy")


@help_router.message(Command("help_activity"))
@help_router.message(F.text.lower().in_(["помощь активность", "помощь стата"]))
async def help_activity(message: Message) -> None:
    """Справка по активности."""
    await _send_section(message, "activity")


@help_router.message(Command("help_rules"))
@help_router.message(F.text.lower().in_(["помощь правила"]))
async def help_rules(message: Message) -> None:
    """Справка по правилам чата."""
    await _send_section(message, "rules")


async def _send_section(message: Message, section: str) -> None:
    try:
        text, keyboard = render(section)
        await message.answer(text, reply_markup=keyboard)
    except Exception as error:
        logger.error(f"Ошибка в справке раздела {section}: {error}")
        await message.answer("Не удалось открыть этот раздел помощи.")


@help_router.callback_query(F.data.startswith("help:"))
async def help_navigation(callback: CallbackQuery) -> None:
    """Переключение разделов кнопками без новых сообщений."""
    try:
        section = (callback.data or "").split(":", 1)[-1]
        text, keyboard = render(section)

        if callback.message is not None:
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except TelegramBadRequest as error:
                # Сообщение могли удалить или текст не изменился — шлём новое.
                if "message is not modified" in str(error).lower():
                    await callback.answer()
                    return
                await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
    except Exception as error:
        logger.error(f"Ошибка в навигации помощи: {error}")
        await callback.answer("Не удалось открыть раздел.", show_alert=True)
