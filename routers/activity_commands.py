from aiogram import Router, F
from aiogram.filters.command import Command
from aiogram.types import Message
from aiogram import Bot
# from aiogram.enums import ChatType
# from aiogram.exceptions import TelegramBadRequest
from database import increment_user_activity, get_chat_leaderboard, get_daily_top, get_monthly_top, reset_daily_activity
import asyncio
import logging
from datetime import datetime, time, timedelta

from config import (
    STATS_ENABLED_CHATS, DAILY_TOP_LIMIT, MONTHLY_TOP_LIMIT,
    DAILY_REPORT_TIME_HOUR, DAILY_REPORT_TIME_MINUTE,
    MONTHLY_REPORT_TIME_HOUR, MONTHLY_REPORT_TIME_MINUTE,
    STATS_LEADERBOARD_LIMIT
)

logger = logging.getLogger(__name__)
activity_routers = Router() # подключение роутеров


async def publish_daily_report(bot: Bot):
    """Публикует ежедневную ведомость активности во все включенные чаты."""
    logger.info("Начинаем публикацию ежедневной ведомости")

    daily_top = get_daily_top(DAILY_TOP_LIMIT)

    if not daily_top:
        logger.info("Нет данных для ежедневной ведомости")
        return

    # Формируем текст ведомости
    report_text = "📊 Опубликована Ежедневная ведомость за день\n\n"
    report_text += "Топ-5 самых активных граждан:\n\n"

    for i, (nickname, activity) in enumerate(daily_top, 1):
        report_text += f"{i}. {nickname} - {activity} сообщений\n"

    # Отдельное сообщение о победителе
    winner_nickname, winner_activity = daily_top[0]
    winner_text = f"🏆 Топ-1 по речевому вкладу — гражданин {winner_nickname}. Партия гордится им!"

    # Отправляем во все чаты
    success_count = 0
    error_count = 0

    for chat_id in STATS_ENABLED_CHATS:
        try:
            await bot.send_message(chat_id=chat_id, text=report_text)
            await bot.send_message(chat_id=chat_id, text=winner_text)
            logger.info(f"Ежедневная ведомость отправлена в чат {chat_id}")
            success_count += 1
        except Exception as e:
            logger.error(f"Ошибка отправки ежедневной ведомости в чат {chat_id}: {e}")
            error_count += 1

    logger.info(f"Ежедневная ведомость отправлена в {success_count} чатов, ошибок: {error_count}")

    # Сбрасываем ежедневную активность
    reset_daily_activity()


async def publish_monthly_report(bot: Bot):
    """Публикует ежемесячную ведомость активности во все включенные чаты."""
    logger.info("Начинаем публикацию ежемесячной ведомости")

    monthly_top = get_monthly_top(MONTHLY_TOP_LIMIT)

    if not monthly_top:
        logger.info("Нет данных для ежемесячной ведомости")
        return

    # Формируем текст ведомости
    report_text = "📈 Опубликована Ежемесячная ведомость за месяц\n\n"
    report_text += "Топ-30 самых активных граждан:\n\n"

    for i, (nickname, activity) in enumerate(monthly_top, 1):
        report_text += f"{i}. {nickname} - {activity} сообщений\n"

    # Отправляем во все чаты
    success_count = 0
    error_count = 0

    for chat_id in STATS_ENABLED_CHATS:
        try:
            await bot.send_message(chat_id=chat_id, text=report_text)
            logger.info(f"Ежемесячная ведомость отправлена в чат {chat_id}")
            success_count += 1
        except Exception as e:
            logger.error(f"Ошибка отправки ежемесячной ведомости в чат {chat_id}: {e}")
            error_count += 1

    logger.info(f"Ежемесячная ведомость отправлена в {success_count} чатов, ошибок: {error_count}")


async def daily_report_task(bot: Bot):
    """Фоновая задача для ежедневной публикации отчета в заданное время."""
    while True:
        try:
            now = datetime.utcnow()

            # Вычисляем время до следующего запуска
            target_time = time(DAILY_REPORT_TIME_HOUR, DAILY_REPORT_TIME_MINUTE, 0)
            next_run = datetime.combine(now.date(), target_time)

            if now.time() >= target_time:
                # Если уже прошло время, ждем до завтра
                next_run = datetime.combine(now.date() + timedelta(days=1), target_time)

            seconds_until_next = (next_run - now).total_seconds()

            logger.info(f"Следующая ежедневная ведомость через {seconds_until_next:.1f} секунд")
            await asyncio.sleep(seconds_until_next)

            # Публикуем ежедневную ведомость
            await publish_daily_report(bot)

        except Exception as e:
            logger.error(f"Ошибка в задаче ежедневной ведомости: {e}")
            await asyncio.sleep(60)  # Ждем минуту перед повторной попыткой


async def monthly_report_task(bot: Bot):
    """Фоновая задача для ежемесячной публикации отчета в последний день месяца в заданное время."""
    while True:
        try:
            now = datetime.utcnow()

            # Вычисляем последний день текущего месяца
            if now.month == 12:
                last_day = datetime(now.year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(now.year, now.month + 1, 1) - timedelta(days=1)

            # Устанавливаем время последнего дня месяца
            target_time = datetime.combine(last_day.date(), time(MONTHLY_REPORT_TIME_HOUR, MONTHLY_REPORT_TIME_MINUTE, 0))

            if now >= target_time:
                # Если уже прошло время публикации, ждем до следующего месяца
                if now.month == 12:
                    next_month = datetime(now.year + 1, 1, 1)
                else:
                    next_month = datetime(now.year, now.month + 1, 1)

                last_day_next = next_month - timedelta(days=1)
                target_time = datetime.combine(last_day_next.date(), time(MONTHLY_REPORT_TIME_HOUR, MONTHLY_REPORT_TIME_MINUTE, 0))

            seconds_until_next = (target_time - now).total_seconds()

            logger.info(f"Следующая ежемесячная ведомость через {seconds_until_next:.1f} секунд")
            await asyncio.sleep(seconds_until_next)

            # Публикуем ежемесячную ведомость
            await publish_monthly_report(bot)

        except Exception as e:
            logger.error(f"Ошибка в задаче ежемесячной ведомости: {e}")
            await asyncio.sleep(3600)  # Ждем час перед повторной попыткой


# Роутер выводит статистику
@activity_routers.message(Command('activity'))
@activity_routers.message(F.text.lower().in_(['статистика','стата','сводка','активность','актив']))
async def show_stats_handler(message: Message):
    # 1. Проверяем, можно ли использовать команду в этом чате
    if message.chat.id not in STATS_ENABLED_CHATS:
        await message.answer("В этом чате статистика отключена.")
        return

    # 2. Получаем данные из БД
    leaderboard = get_chat_leaderboard(STATS_LEADERBOARD_LIMIT)

    if not leaderboard:
        await message.answer("Пока нечего показывать. Статистика пуста.")
        return

    # 3. Формируем красивый ответ
    response_text = "✍️ Сводка народной активности*\n\n"
    
    for i, (nickname, activity) in enumerate(leaderboard, 1):
        response_text += f"{i}. {nickname} - {activity} сообщений\n"
        
    await message.answer(response_text, parse_mode="Markdown")

# Роутер собирающий статистику
@activity_routers.message(F.text & ~F.text.startswith("/"))
async def count_messages(message: Message):
    # 1. Проверяем, находится ли чат в нашем списке
    if message.chat.id not in STATS_ENABLED_CHATS:
        return # Если нет, просто ничего не делаем

    # 2. Если чат в списке, увеличиваем счетчик
    user_id = message.from_user.id
    if not increment_user_activity(user_id):
        logger.error(f"Не удалось увеличить активность пользователя {user_id}")
    # Никакого ответа в чат не посылаем, чтобы не спамить