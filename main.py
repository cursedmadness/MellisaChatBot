# main.py
from routers import main_router
from aiogram import Bot, Dispatcher
import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from dotenv import load_dotenv

from database import (
    create_table, 
    add_new_columns, 
    initialize_admins, 
    process_daily_rice_distribution, 
    initialize_default_ratings
)
from routers.moderation_commands import cleanup_expired_punishments_task
from routers.activity_commands import daily_report_task, monthly_report_task
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import (
    BOT_TOKEN, PARSE_MODE, LINK_PREVIEW_DISABLED, LOG_LEVEL, LOG_FORMAT,
    DAILY_RICE_TIME_HOUR, ADMIN_IDS
)

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format=LOG_FORMAT,
)
logger = logging.getLogger(__name__)

# Проверка токена
if not BOT_TOKEN:
    logger.error("Токен бота не найден!")
    raise ValueError("Токен бота не настроен. Проверьте переменную окружения BOT_TOKEN")

# Инициализация бота и диспетчера
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=getattr(ParseMode, PARSE_MODE.upper(), ParseMode.HTML),
        link_preview_is_disabled=LINK_PREVIEW_DISABLED
    )
)
dp = Dispatcher()
dp.include_router(main_router)

async def daily_rice_task_runner():
    """Фоновая задача для ежедневной выдачи риса."""
    while True:
        try:
            now = datetime.now(timezone.utc)
            target_time = time(DAILY_RICE_TIME_HOUR, 0, 0)
            next_run = datetime.combine(now.date(), target_time, tzinfo=timezone.utc)

            if now.time() >= target_time:
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            logger.info(f"Следующая выдача риса через {wait_seconds:.1f} сек. (в {DAILY_RICE_TIME_HOUR}:00 UTC)")
            await asyncio.sleep(wait_seconds)

            logger.info("Начинается ежедневная выдача риса...")
            distributed = await process_daily_rice_distribution()
            logger.info(f"Ежедневная выдача риса завершена. Выдано {distributed} пользователям")

        except Exception as e:
            logger.error(f"Ошибка в задаче ежедневной выдачи риса: {e}")
            await asyncio.sleep(60)

async def main():
    try:
        logger.info("Инициализация базы данных...")
        await create_table()
        await add_new_columns()
        await initialize_admins(ADMIN_IDS)

        initialized_count = await initialize_default_ratings(100)
        if initialized_count > 0:
            logger.info(f"Инициализировано {initialized_count} граждан с базовым рейтингом 100")

        logger.info("База данных готова.")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        raise

    # Запускаем фоновые задачи
    tasks = [
        asyncio.create_task(daily_rice_task_runner()),
        asyncio.create_task(cleanup_expired_punishments_task()),
        asyncio.create_task(daily_report_task(bot)),
        asyncio.create_task(monthly_report_task(bot))
    ]

    logger.info("Запуск бота MellisaChatBot...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при поллинге: {e}")
    finally:
        # Отменяем фоновые задачи при выходе
        for task in tasks:
            task.cancel()
        await bot.session.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
