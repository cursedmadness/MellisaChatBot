#main.py 
from Routers import main_router
from aiogram import Bot, Dispatcher
import asyncio
from database import create_table, add_new_columns
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

TOKEN = '6695001037:AAG2GsxtOZcFFlvQ9jCzLQy3IhNrSkxmV2Y'

bot=Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp=Dispatcher()

dp.include_router(main_router)
    
async def main():
    create_table()
    add_new_columns()
    await dp.start_polling(bot)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Выключено блять.')
