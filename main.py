#main.py 
from Routers import main_router
from aiogram import Bot, Dispatcher
import asyncio
from database import create_table, add_new_columns, initialize_admins
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from Routers.admin_commands import ADMIN_IDS


TOKEN = '6695001037:AAG2GsxtOZcFFlvQ9jCzLQy3IhNrSkxmV2Y' # Изучить .env для защиты

bot=Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) # Подключение бота(с оформлением смс)
dp=Dispatcher()

dp.include_router(main_router) # Подключение всех роутеров
    
async def main():
    create_table()
    add_new_columns()
    initialize_admins(ADMIN_IDS)
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Выключено блять.')
