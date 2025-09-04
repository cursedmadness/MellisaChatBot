from aiogram import Router, F
from aiogram.filters.command import Command
from aiogram.types import Message
# from aiogram.enums import ChatType
# from aiogram.exceptions import TelegramBadRequest
from database import increment_user_activity, get_chat_leaderboard
activity_routers = Router() # подключение роутеров

STATS_ENABLED_CHATS = {-1002059485061, -1003079876973, -1002709445496} #ид чатов где собирается статистика


# Роутер выводит статистику
@activity_routers.message(Command('activity'))
@activity_routers.message(F.text.lower().in_(['статистика','стата']))
async def show_stats_handler(message: Message):
    # 1. Проверяем, можно ли использовать команду в этом чате
    if message.chat.id not in STATS_ENABLED_CHATS:
        await message.answer("В этом чате статистика отключена.")
        return

    # 2. Получаем данные из БД
    leaderboard = get_chat_leaderboard(15) # Возьмем топ-15

    if not leaderboard:
        await message.answer("Пока нечего показывать. Статистика пуста.")
        return

    # 3. Формируем красивый ответ
    response_text = "🏆 **Статистика активности в чате:**\n\n"
    
    for i, (nickname, activity) in enumerate(leaderboard, 1):
        response_text += f"{i}. {nickname} - {activity} сообщений\n"
        
    await message.answer(response_text, parse_mode="Markdown")

# Роутер собирающий статистику
@activity_routers.message(F.text)
async def count_messages(message: Message):
    # 1. Проверяем, находится ли чат в нашем списке
    if message.chat.id not in STATS_ENABLED_CHATS:
        return # Если нет, просто ничего не делаем

    # 2. Если чат в списке, увеличиваем счетчик
    user_id = message.from_user.id
    increment_user_activity(user_id)
    # Никакого ответа в чат не посылаем, чтобы не спамить