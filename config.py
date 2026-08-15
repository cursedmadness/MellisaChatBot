"""
Конфигурационный файл для бота
"""

import os
from typing import Set
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройки времени
DAILY_RICE_TIME_HOUR = 9  # Час ежедневной выдачи риса (UTC)
DAILY_REPORT_TIME_HOUR = 0  # Час ежедневного отчета активности (UTC)
DAILY_REPORT_TIME_MINUTE = 0  # Минута ежедневного отчета
MONTHLY_REPORT_TIME_HOUR = 23  # Час ежемесячного отчета
MONTHLY_REPORT_TIME_MINUTE = 59  # Минута ежемесячного отчета

# Лимиты
MAX_RICE_PER_USER = 6  # Максимальное количество риса у пользователя
DAILY_TOP_LIMIT = 5  # Количество участников в ежедневном топе
MONTHLY_TOP_LIMIT = 30  # Количество участников в ежемесячном топе
STATS_LEADERBOARD_LIMIT = 15  # Количество участников в команде /activity

# Настройки чатов
STATS_ENABLED_CHATS: Set[int] = {
    -1002059485061,
    -1003079876973,
    -1002709445496,
}  # ID чатов для сбора статистики активности

# Настройки администраторов
# Настройки администраторов. Загружаются из переменной ADMIN_IDS (через запятую)
_admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(i.strip()) for i in _admin_ids_str.split(",") if i.strip().isdigit()]

# Чат для уведомлений о запуске/остановке бота (опционально)
DEV_CHAT_ID = int(os.getenv("DEV_CHAT_ID", "0")) or None

# Настройки базы данных
DB_NAME = "users.db"  # Имя файла базы данных

# Настройки логирования
LOG_LEVEL = "INFO"  # Уровень логирования
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"  # Формат логов

# Настройки бота
BOT_TOKEN = os.getenv("TOKEN")  # Токен бота из переменной окружения
PARSE_MODE = "HTML"  # Режим парсинга сообщений
LINK_PREVIEW_DISABLED = True  # Отключить превью ссылок

# Pyrogram настройки для модерации (получить на https://my.telegram.org/)
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

# Настройки кормления кошки
SATISFACTION_DECAY_HOURS = 5  # Часы до уменьшения сытости
SATISFACTION_DECAY_AMOUNT = 10  # Количество сытости, теряемое за период

# Настройки возраста кошки
AGE_UPDATE_CHECK_HOURS = 24  # Проверка возраста каждый день
