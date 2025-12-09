#main.py
from routers import main_router
from aiogram import Bot, Dispatcher
import asyncio
from database import create_table, add_new_columns, initialize_admins, process_daily_rice_distribution
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from routers.admin_commands import ADMIN_IDS
from dotenv import load_dotenv
import os
import logging
from datetime import datetime, time, timedelta

load_dotenv()
token=os.getenv('TOKEN')

bot=Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True)) #type: ignore
# Подключение бота(с оформлением смс)
dp=Dispatcher()

dp.include_router(main_router) # Подключение всех роутеров

# Базовая настройка логов
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def daily_rice_task():
    """
    Фоновая задача для ежедневной выдачи риса в 9:00 утра по UTC.
    """
    while True:
        now = datetime.utcnow()

        # Вычисляем время до следующего 9:00 UTC
        target_time = time(9, 0, 0)  # 9:00 UTC
        next_run = datetime.combine(now.date(), target_time)

        if now.time() >= target_time:
            # Если уже прошло 9:00, ждем до завтра
            next_run = datetime.combine(now.date() + timedelta(days=1), target_time)

        seconds_until_next = (next_run - now).total_seconds()

        logger.info(".1f")
        await asyncio.sleep(seconds_until_next)

        # Выполняем ежедневную выдачу риса
        logger.info("Начинается ежедневная выдача риса...")
        distributed = process_daily_rice_distribution()
        logger.info(f"Ежедневная выдача риса завершена. Выдано {distributed} пользователям")


async def main():
    create_table()
    add_new_columns()
    initialize_admins(ADMIN_IDS)

    # Запускаем фоновую задачу для ежедневной выдачи риса
    asyncio.create_task(daily_rice_task())

    logger.info("Starting bot polling…")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Выключено пользователем (KeyboardInterrupt)")
