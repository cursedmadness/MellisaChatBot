from aiogram import Router, F
from aiogram.filters.command import Command
from aiogram.types import Message
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest

ADMIN_IDS = [123456789, 987654321, 555555555]

admin_router = Router()
admin_router.message.filter(F.from_user.id.in_(ADMIN_IDS))



@admin_router.message(Command('ban'))
@admin_router.message(F.text.lower().startswith(['бан']), F.chat.type == ChatType.GROUP)
async def ban_user(message: Message, bot: 'Bot'): # type: ignore
        banned_user = None
    
        # 1. Проверяем, есть ли ответ на сообщение
        if message.reply_to_message:
            banned_user = message.reply_to_message.from_user
        # 2. Проверяем, есть ли упоминание @username в команде
        else:
            args = message.text.split()
            if len(args) < 2:
                await message.answer("Укажите пользователя для бана, ответив на его сообщение или указав @username.")
                return

            username = args[1]
            if username.startswith('@'):
                username = username[1:]  # Убираем @

                try:
                    # Пытаемся найти пользователя в чате по username
                    chat_members = await bot.get_chat_member(chat_id=message.chat.id, user_id=username)
                    banned_user = chat_members.user
                except TelegramBadRequest:
                    await message.answer(f"Пользователь @{username} не найден в этом чате.")
                    return
            else:
                await message.answer("Пожалуйста, укажите @username или ответьте на сообщение пользователя.")
                return

        # Проверяем, что banned_user найден
        if not banned_user:
            await message.answer("Не удалось определить пользователя для бана.")
            return

        # Проверяем, что пользователь не пытается забанить сам себя
        if banned_user.id == message.from_user.id:
            await message.answer("Вы не можете забанить самого себя!")
            return

        # Выполняем бан
        try:
            await bot.ban_chat_member(chat_id=message.chat.id, user_id=banned_user.id)
        except TelegramBadRequest as e:
            await message.answer(f"Ошибка при бане пользователя: {str(e)}")
            return

        # Отправляем сообщение с HTML-разметкой
        await message.answer(
            f'Пользователь <a href="tg://user?id={banned_user.id}">{banned_user.first_name}</a> '
            f'был забанен пользователем <a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a>',
            )

