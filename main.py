#main.py 
from routers import main_router
from aiogram import Bot, Dispatcher
import asyncio
from database import create_table, add_new_columns, initialize_admins
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from routers.admin_commands import ADMIN_IDS
from dotenv import load_dotenv
import os
import logging

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
    
async def main():
    create_table()
    add_new_columns()
    initialize_admins(ADMIN_IDS)
    logger.info("Starting bot polling…")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Выключено пользователем (KeyboardInterrupt)")
