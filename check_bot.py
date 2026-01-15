#!/usr/bin/env python3
"""
Скрипт для проверки конфигурации и работоспособности бота.
Запустите: python check_bot.py
"""

import os
import sys
from dotenv import load_dotenv

def main():
    print("🔍 Диагностика бота MelissaChatBot")
    print("=" * 50)

    # Загружаем переменные окружения
    load_dotenv()

    # Проверка переменных окружения
    print("\n📋 Переменные окружения:")
    token_ok = bool(os.getenv('BOT_TOKEN') or os.getenv('TOKEN'))

    print(f"  BOT_TOKEN (бот):   {'✅' if token_ok else '❌'}")

    # Проверка импортов
    print("\n📦 Проверка модулей:")
    modules_ok = True

    try:
        from config import BOT_TOKEN
        print("  config.py:        ✅")
    except Exception as e:
        print(f"  config.py:        ❌ ({e})")
        modules_ok = False

    try:
        from database import create_connection
        print("  database.py:      ✅")
    except Exception as e:
        print(f"  database.py:      ❌ ({e})")
        modules_ok = False

    try:
        from routers.moderation_commands import moderation_router
        print("  moderation_commands.py: ✅")
    except Exception as e:
        print(f"  moderation_commands.py: ❌ ({e})")
        modules_ok = False

    try:
        from routers import main_router
        print("  routers:          ✅")
    except Exception as e:
        print(f"  routers:          ❌ ({e})")
        modules_ok = False

    # Проверка зависимостей
    print("\n📚 Проверка зависимостей:")
    try:
        import aiogram
        print("  aiogram:          ✅")
    except ImportError:
        print("  aiogram:          ❌ (pip install aiogram)")

    try:
        import aiosqlite
        print("  aiosqlite:        ✅")
    except ImportError:
        print("  aiosqlite:        ❌ (pip install aiosqlite)")

    # Итоговые рекомендации
    print("\n🎯 Статус и рекомендации:")
    print("-" * 30)

    if not token_ok:
        print("❌ BOT_TOKEN не настроен! Добавьте в .env файл:")
        print("   BOT_TOKEN=ваш_токен_бота")
        print()

    if modules_ok and token_ok:
        print("✅ Бот готов к запуску!")
        print("   Команда: python main.py")
        print()
        print("💡 После запуска используйте команду 'статус модерации'")
        print("   для проверки работы системы модерации")
    else:
        print("❌ Есть проблемы с конфигурацией.")
        print("   Исправьте ошибки выше перед запуском.")

    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()