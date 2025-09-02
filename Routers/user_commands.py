from aiogram import Router, F
from aiogram.filters.command import Command
from aiogram.types import Message
from aiogram.enums import ChatType
import os
from deep_translator import GoogleTranslator
from pydub import AudioSegment
import time, datetime
from Routers.admin_commands import ADMIN_IDS
from database import get_all_admins

user_router = Router()

"""AudioSegment.converter = "D:\\bots\\coder\\ffmpeg.exe"
AudioSegment.ffmpeg = "D:\\bots\\coder\\ffmpeg.exe"
AudioSegment.ffprobe = "D:\\bots\\coder\\ffprobe.exe" """

# Роутер-пинг. банально.
@user_router.message(Command('ping'))
@user_router.message(F.text.lower().in_(['пинг','социальный пинг-понг']))
async def ping_bot(message: Message): # type: ignore
    ev = (datetime.datetime.now(tz=datetime.timezone.utc) - message.date).microseconds / 1000000
    sent_message = await message.answer("🤖 Измеряю пинг...")
     # Устанавливаем порог для пинга
    ping_threshold = 50 

    # Проверяем значение пинга и выбираем текст ответа
    if ev < ping_threshold:
        out = f"🏓 Партия выиграла в пинг-понг за <code>{ev}</code> с"
    else:
        out = f"🏓 Партия проиграла в пинг-понг за <code>{ev}</code> с"
    
    # Редактируем сообщение с окончательным ответом
    await sent_message.edit_text(out)
    
# Роутер вывода списка администраторов
@user_router.message(Command("adminlist"))
@user_router.message(F.text.lower().in_(['кто админ','админы','кто администратор','кто смотритель','.партия']))
async def admin_list_command(message: Message):
    # Получаем список администраторов
    admins = get_all_admins()
    if not admins:
        await message.answer("Список администраторов пуст.")
        return

    # Формируем ответ с HTML-разметкой
    admin_list_text = "<b>🎓 Наши смотрители:</b>\n"
    for user_id, first_name in admins:
        admin_list_text += f"- <a href='tg://user?id={user_id}'>{first_name}</a> (ID: {user_id})\n"

    await message.answer(admin_list_text, parse_mode='HTML')

# Роутер для перевода гс(захейчен Каем)
"""@user_router.message(Command('voice'))
@user_router.message(F.text.lower().in_('войс'), F.chat.type == ChatType.GROUP)
async def voice_message(message: Message):
    if not message.reply_to_message:
        await message.reply(f'Вы не попали на голосовое/видео- сообщение.')

    if ((not message.reply_to_message.voice) and (not message.reply_to_message.video_note) and
            (not message.reply_to_message.video)):
        await message.reply(f'Ответное смс не является голосовым/видео сообщением.')

    if message.reply_to_message.voice:
        audio_file_path_ogg = 'voice.ogg'
        audio_file_path_mp3 = 'voice.mp3'
        process_message = await message.reply_to_message.reply('📝 Процесс перевода голосового '
                                                               'сообщения запущен!\n🕐 Ожидайте. . .')
        file_info = await message.reply_to_message.bot.get_file(message.reply_to_message.voice.file_id)
        file_path = file_info.file_path
        file = await message.reply_to_message.bot.download_file(file_path)
        voice_time = message.reply_to_message.voice.duration

        with open(audio_file_path_ogg, 'wb') as audio_file:
            audio_file.write(file.read())
        audio_segment = AudioSegment.from_ogg(audio_file_path_ogg)
        audio_segment.export(audio_file_path_mp3, format='mp3')

        def format_time(voice_time):
            minutes = voice_time // 60
            seconds = voice_time % 60
            return f"{minutes:02}:{seconds:02}"

        with open(audio_file_path_mp3, 'rb') as audio_file_mp3:
            voice_time_formatted = format_time(voice_time)
            transcription = user_router.audio.transcriptions.create(model='whisper-large-v3', file=audio_file_mp3)
            traslated = GoogleTranslator(source='auto', target='ru').translate(transcription.text)
            await process_message.edit_text(f"🕐 <b>{voice_time_formatted}</b>:\n{traslated}")
        os.remove(audio_file_path_ogg)
        os.remove(audio_file_path_mp3)

    elif message.reply_to_message.video_note:
        video_file_path_mp4 = 'video.mp4'
        audio_file_path_mp3 = 'voice.mp3'
        process_message = await message.reply_to_message.reply('📝 Процесс перевода кружочка '
                                                               'запущен!\n🕐 Ожидайте. . .')
        file_info = await message.reply_to_message.bot.get_file(message.reply_to_message.video_note.file_id)
        file_path = file_info.file_path
        file = await message.reply_to_message.bot.download_file(file_path)
        voice_time = message.reply_to_message.video_note.duration

        with open(video_file_path_mp4, 'wb') as audio_file:
            audio_file.write(file.read())
        audio_segment = AudioSegment.from_file(video_file_path_mp4)
        audio_segment.export(audio_file_path_mp3, format='mp3')

        def format_time(voice_time):
            minutes = voice_time // 60
            seconds = voice_time % 60
            return f"{minutes:02}:{seconds:02}"

        with open(audio_file_path_mp3, 'rb') as audio_file_mp3:
            voice_time_formatted = format_time(voice_time)
            transcription = user_router.audio.transcriptions.create(model='whisper-large-v3', file=audio_file_mp3)
            traslated = GoogleTranslator(source='auto', target='ru').translate(transcription.text)
            await process_message.edit_text(f"🕐 <b>{voice_time_formatted}</b>:\n{traslated}")
        os.remove(video_file_path_mp4)
        os.remove(audio_file_path_mp3)

    elif message.reply_to_message.video:
        video_file_path_mp4 = 'video.mp4'
        audio_file_path_mp3 = 'voice.mp3'
        process_message = await message.reply_to_message.reply('📝 Процесс перевода видео сообщения '
                                                               'запущен!\n🕐 Ожидайте. . .')
        file_info = await message.reply_to_message.bot.get_file(message.reply_to_message.video.file_id)
        file_path = file_info.file_path
        file = await message.reply_to_message.bot.download_file(file_path)
        voice_time = message.reply_to_message.video.duration

        with open(video_file_path_mp4, 'wb') as audio_file:
            audio_file.write(file.read())
        audio_segment = AudioSegment.from_file(video_file_path_mp4)
        audio_segment.export(audio_file_path_mp3, format='mp3')

        def format_time(voice_time):
            minutes = voice_time // 60
            seconds = voice_time % 60
            return f"{minutes:02}:{seconds:02}"

        with open(audio_file_path_mp3, 'rb') as audio_file_mp3:
            voice_time_formatted = format_time(voice_time)
            transcription = user_router.audio.transcriptions.create(model='whisper-large-v3', file=audio_file_mp3)
            traslated = GoogleTranslator(source='auto', target='ru').translate(transcription.text)
            await process_message.edit_text(f"🕐 <b>{voice_time_formatted}</b>:\n{traslated}")
        os.remove(video_file_path_mp4)
        os.remove(audio_file_path_mp3)"""
