#main.py
from routers import main_router
from aiogram import Bot, Dispatcher
import asyncio
from database import create_table, add_new_columns, initialize_admins, process_daily_rice_distribution, initialize_default_ratings
from routers.moderation_commands import start_moderation_bot, stop_moderation_bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import (
    BOT_TOKEN, PARSE_MODE, LINK_PREVIEW_DISABLED, LOG_LEVEL, LOG_FORMAT,
    DAILY_RICE_TIME_HOUR, ADMIN_IDS
)
import logging
from datetime import datetime, time, timedelta
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format=LOG_FORMAT,
)
logger = logging.getLogger(__name__)

# Проверка токена бота
if not BOT_TOKEN:
    logger.error("Токен бота не найден! Установите переменную окружения TOKEN")
    logger.error("Пример: export TOKEN='ваш_токен_бота'")
    raise ValueError("Токен бота не настроен. Проверьте переменную окружения TOKEN")

# Проверка pyrogram настроек
from config import API_ID, API_HASH
if not API_ID or not API_HASH:
    logger.warning("Pyrogram настройки (API_ID и API_HASH) не найдены!")
    logger.warning("Команды модерации (/бан, /мут, /варн) будут недоступны")
    logger.warning("Получите API_ID и API_HASH на https://my.telegram.org/")

# Инициализация бота
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=getattr(ParseMode, PARSE_MODE.upper(), ParseMode.HTML),
        link_preview_is_disabled=LINK_PREVIEW_DISABLED
    )
)
dp = Dispatcher()
dp.include_router(main_router)


async def daily_rice_task():
    """
    Фоновая задача для ежедневной выдачи риса в заданное время по UTC.
    """
    while True:
        try:
            now = datetime.utcnow()

            # Вычисляем время до следующего запуска
            target_time = time(DAILY_RICE_TIME_HOUR, 0, 0)
            next_run = datetime.combine(now.date(), target_time)

            if now.time() >= target_time:
                # Если уже прошло время, ждем до завтра
                next_run = datetime.combine(now.date() + timedelta(days=1), target_time)

            seconds_until_next = (next_run - now).total_seconds()

            logger.info(f"Следующая выдача риса через {seconds_until_next:.1f} секунд (в {DAILY_RICE_TIME_HOUR}:00 UTC)")
            await asyncio.sleep(seconds_until_next)

            # Выполняем ежедневную выдачу риса
            logger.info("Начинается ежедневная выдача риса...")
            distributed = process_daily_rice_distribution()
            logger.info(f"Ежедневная выдача риса завершена. Выдано {distributed} пользователям")

        except Exception as e:
            logger.error(f"Ошибка в задаче ежедневной выдачи риса: {e}")
            await asyncio.sleep(60)  # Ждем минуту перед повторной попыткой


async def main():
    try:
        logger.info("Инициализация бота...")
        create_table()
        add_new_columns()
        initialize_admins(ADMIN_IDS)

        # Инициализируем рейтинг по умолчанию для существующих пользователей
        initialized_count = initialize_default_ratings(100)
        if initialized_count > 0:
            logger.info(f"Инициализировано {initialized_count} граждан с рейтингом 100")

        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        raise

    # Запускаем фоновые задачи
    asyncio.create_task(daily_rice_task())

    # Запускаем pyrogram бота для модерации
    await start_moderation_bot()

    # Импортируем функции для отчетов активности
    from routers.activity_commands import daily_report_task, monthly_report_task
    asyncio.create_task(daily_report_task(bot))
    asyncio.create_task(monthly_report_task(bot))

    logger.info("Starting bot polling…")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        raise


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Выключено пользователем (KeyboardInterrupt)")
        # Останавливаем pyrogram бота
        asyncio.run(stop_moderation_bot())
