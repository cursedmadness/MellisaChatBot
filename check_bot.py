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
    token_ok = bool(os.getenv('TOKEN'))
    api_id_ok = bool(os.getenv('API_ID'))
    api_hash_ok = bool(os.getenv('API_HASH'))

    print(f"  TOKEN (бот):     {'✅' if token_ok else '❌'}")
    print(f"  API_ID (pyrogram): {'✅' if api_id_ok else '❌'}")
    print(f"  API_HASH (pyrogram): {'✅' if api_hash_ok else '❌'}")

    # Проверка импортов
    print("\n📦 Проверка модулей:")
    modules_ok = True

    try:
        from config import BOT_TOKEN, API_ID, API_HASH
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
        from routers.moderation_commands import moderation_app
        print("  moderation_commands.py: ✅")
        print(f"  pyrogram client:  {'✅' if moderation_app else '❌'}")
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
        import pyrogram
        print("  pyrogram:         ✅")
    except ImportError:
        print("  pyrogram:         ❌ (pip install pyrogram)")

    try:
        import TgCrypto
        print("  TgCrypto:         ✅")
    except ImportError:
        print("  TgCrypto:         ❌ (pip install TgCrypto)")

    # Итоговые рекомендации
    print("\n🎯 Статус и рекомендации:")
    print("-" * 30)

    if not token_ok:
        print("❌ TOKEN не настроен! Добавьте в .env файл:")
        print("   TOKEN=ваш_токен_бота")
        print()

    if not api_id_ok or not api_hash_ok:
        print("⚠️  API_ID и API_HASH не настроены!")
        print("   Команды модерации (/бан, /мут, /варн) будут недоступны")
        print("   Инструкция по получению:")
        print("   1. Перейдите на https://my.telegram.org/")
        print("   2. Авторизуйтесь")
        print("   3. Создайте приложение")
        print("   4. Добавьте в .env:")
        print("      API_ID=ваш_api_id")
        print("      API_HASH=ваш_api_hash")
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