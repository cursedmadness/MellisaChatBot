# main.py
from routers import main_router
from aiogram import Bot, Dispatcher
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
)
import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from dotenv import load_dotenv

from database import (
    create_table,
    add_new_columns,
    initialize_admins,
    process_daily_rice_distribution,
    initialize_default_ratings,
    get_all_waifus_with_owners,
    get_user_city,
    init_db,
    close_db,
)
from routers.moderation_commands import cleanup_expired_punishments_task
from routers.activity_commands import daily_report_task, monthly_report_task
from routers.weather_service import get_weather_string, close_weather_session
from routers.strings import (
    MORNING_PHRASES,
    NIGHT_PHRASES,
    HUNGER_PHRASES,
    CRITICAL_HUNGER_PHRASES,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import (
    BOT_TOKEN,
    PARSE_MODE,
    LINK_PREVIEW_DISABLED,
    LOG_LEVEL,
    LOG_FORMAT,
    DAILY_RICE_TIME_HOUR,
    ADMIN_IDS,
    DEV_CHAT_ID,
)
import random


# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format=LOG_FORMAT,
)
logger = logging.getLogger(__name__)

# Проверка токена
if not BOT_TOKEN:
    logger.error("Токен бота не найден!")
    raise ValueError("Токен бота не настроен. Проверьте переменную окружения BOT_TOKEN")

# Инициализация бота и диспетчера
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=getattr(ParseMode, PARSE_MODE.upper(), ParseMode.HTML),
        link_preview_is_disabled=LINK_PREVIEW_DISABLED,
    ),
)
dp = Dispatcher()
dp.include_router(main_router)


async def daily_rice_task_runner():
    """Фоновая задача для ежедневной выдачи риса."""
    while True:
        try:
            now = datetime.now(timezone.utc)
            target_time = time(DAILY_RICE_TIME_HOUR, 0, 0)
            next_run = datetime.combine(now.date(), target_time, tzinfo=timezone.utc)

            if now.time() >= target_time:
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            logger.info(
                f"Следующая выдача риса через {wait_seconds:.1f} сек. (в {DAILY_RICE_TIME_HOUR}:00 UTC)"
            )
            await asyncio.sleep(wait_seconds)

            logger.info("Начинается ежедневная выдача риса...")
            distributed = await process_daily_rice_distribution()
            logger.info(
                f"Ежедневная выдача риса завершена. Выдано {distributed} пользователям"
            )

        except Exception as e:
            logger.error(f"Ошибка в задаче ежедневной выдачи риса: {e}")
            await asyncio.sleep(60)


async def waifu_greetings_task(bot: Bot):
    """Фоновая задача для приветствий от кошко-жен в 09:00 и 23:00 МСК."""
    while True:
        try:
            now = datetime.now(timezone.utc)
            # МСК = UTC+3
            # 09:00 MSK = 06:00 UTC
            # 23:00 MSK = 20:00 UTC

            times = [time(6, 0, 0), time(20, 0, 0)]

            next_runs = []
            for t in times:
                run = datetime.combine(now.date(), t, tzinfo=timezone.utc)
                if run <= now:
                    run += timedelta(days=1)
                next_runs.append(run)

            target_run = min(next_runs)
            wait_seconds = (target_run - now).total_seconds()

            logger.info(f"Следующее приветствие кошек через {wait_seconds:.1f} сек.")
            await asyncio.sleep(wait_seconds)

            # Проверяем, какое это время (утро или ночь) в UTC
            # 6 UTC -> Утро МСК, 20 UTC -> Ночь МСК
            is_morning = target_run.hour == 6

            # Генерируем сообщения для каждого владельца
            logger.info(
                f"Начинается рассылка приветствий ({'утро' if is_morning else 'ночь'})"
            )
            waifus = await get_all_waifus_with_owners()

            for w in waifus:
                try:
                    user_id = w["user_id"]
                    cat_name = w["cat_name"] or "кошко-жена"

                    # Выбираем рандомную фразу
                    if is_morning:
                        base_text = random.choice(MORNING_PHRASES)
                    else:
                        base_text = random.choice(NIGHT_PHRASES)

                    # Подставляем имя кошки
                    final_text = base_text.format(cat_name=cat_name)

                    # Добавляем погоду утром
                    if is_morning:
                        city = await get_user_city(user_id)
                        if city:
                            weather_info = await get_weather_string(city)
                            if weather_info:
                                final_text += f"\n\n{weather_info}"

                    # Отправляем сообщение владельцу
                    await bot.send_message(user_id, final_text)
                    await asyncio.sleep(0.05)  # Задержка для соблюдения лимитов
                except TelegramForbiddenError:
                    logger.debug(
                        f"Бот заблокирован пользователем {user_id}, пропускаем"
                    )
                except TelegramBadRequest as e:
                    logger.warning(
                        f"Некорректный запрос при отправке приветствия пользователю {user_id}: {e}"
                    )
                except TelegramAPIError as e:
                    logger.warning(
                        f"Ошибка Telegram API при отправке приветствия пользователю {user_id}: {e}"
                    )
                except Exception as send_err:
                    logger.error(
                        f"Неожиданная ошибка при отправке приветствия пользователю {user_id}: {send_err}"
                    )

        except Exception as e:
            logger.error(f"Ошибка в задаче приветствий кошек: {e}")
            await asyncio.sleep(60)


async def waifu_hunger_notifier_task(bot: Bot):
    """
    Фоновая задача для уведомления владельцев, чьи кошки голодны.
    Проверка каждые 2 часа. Уведомления зависят от уровня сытости:
    - < 15%: критический голод (CRITICAL_HUNGER_PHRASES)
    - < 30%: обычный голод (HUNGER_PHRASES)
    """
    while True:
        try:
            # Проверка каждые 2 часа
            await asyncio.sleep(2 * 3600)

            waifus = await get_all_waifus_with_owners()
            for w in waifus:
                user_id = w["user_id"]
                cat_name = w["cat_name"] or "кошко-жена"

                # Применяем декремент сытости по времени
                from routers.waifu_cat import _apply_satiety_decay

                await _apply_satiety_decay(w)

                # Перечитываем актуальные данные из БД после обновления
                from database import get_waifu_by_user

                waifu_fresh = await get_waifu_by_user(user_id)
                if not waifu_fresh:
                    continue

                # Отправляем уведомление в зависимости от уровня сытости
                current_satiety = waifu_fresh.get("satiety") or 0

                if current_satiety < 15:
                    # Критический голод
                    phrases = CRITICAL_HUNGER_PHRASES
                elif current_satiety < 30:
                    # Обычный голод
                    phrases = HUNGER_PHRASES
                else:
                    # Сытость нормальная, уведомление не нужно
                    continue

                try:
                    mention = f"<a href='tg://user?id={user_id}'>хозяин</a>"
                    phrase = random.choice(phrases).format(
                        mention=mention, cat_name=cat_name
                    )
                    await bot.send_message(user_id, phrase)
                    await asyncio.sleep(0.05)
                except (TelegramForbiddenError, TelegramBadRequest):
                    # Пользователь заблокировал бота или чат недоступен
                    pass
                except Exception as e:
                    logger.debug(
                        f"Не удалось отправить уведомление о голоде пользователю {user_id}: {e}"
                    )
        except Exception as e:
            logger.error(f"Ошибка в задаче уведомлений о голоде: {e}")
            await asyncio.sleep(60)


async def waifu_random_rp_task(bot: Bot):
    """Фоновая задача для рандомных RP сообщений от кошко-жены в течение дня."""
    from routers.waifu_rp import generate_waifu_rp_message

    # Сначала немного подождем при старте (например 5 минут), чтобы не спамить сразу
    await asyncio.sleep(300)

    while True:
        try:
            now_utc = datetime.now(timezone.utc)
            # Приблизительное МСК (+3)
            now_msk_hour = (now_utc.hour + 3) % 24

            # Отправляем только днём и вечером (с 10:00 до 22:00)
            if 10 <= now_msk_hour < 22:
                waifus = await get_all_waifus_with_owners()
                for w in waifus:
                    # Шанс 10% на каждый 1 час получить РП-милость (в среднем 1 сообщение в день-два)
                    if random.random() < 0.10:
                        user_id = w["user_id"]
                        cat_name = w["cat_name"] or "кошко-жена"

                        try:
                            msg = await generate_waifu_rp_message(user_id, cat_name)
                            await bot.send_message(user_id, msg, parse_mode="HTML")
                            await asyncio.sleep(0.05)
                        except (TelegramForbiddenError, TelegramBadRequest):
                            # Пользователь заблокировал бота или чат недоступен
                            pass
                        except Exception as e:
                            logger.debug(
                                f"Не удалось отправить RP сообщение {user_id}: {e}"
                            )

            # Спим час до следующей проверки
            await asyncio.sleep(3600)
        except Exception as e:
            logger.error(f"Ошибка в задаче RP сообщений: {e}")
            await asyncio.sleep(60)


async def main():
    try:
        logger.info("Инициализация базы данных...")
        await init_db()
        await create_table()
        await add_new_columns()
        await initialize_admins(ADMIN_IDS)

        initialized_count = await initialize_default_ratings(100)
        if initialized_count > 0:
            logger.info(
                f"Инициализировано {initialized_count} граждан с базовым рейтингом 100"
            )

        logger.info("База данных готова.")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")
        raise

    # Запускаем фоновые задачи
    tasks = [
        asyncio.create_task(daily_rice_task_runner()),
        asyncio.create_task(cleanup_expired_punishments_task(bot)),
        asyncio.create_task(daily_report_task(bot)),
        asyncio.create_task(monthly_report_task(bot)),
        asyncio.create_task(waifu_greetings_task(bot)),
        asyncio.create_task(waifu_hunger_notifier_task(bot)),
        asyncio.create_task(waifu_random_rp_task(bot)),
    ]

    logger.info("Запуск бота MellisaChatBot...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)

        # Уведомление о запуске (дебаг)
        if DEV_CHAT_ID:
            try:
                await bot.send_message(
                    chat_id=DEV_CHAT_ID,
                    text=f"<b>Бот запущен и готов к работе!</b>\n\n"
                    f" Время запуска: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n",
                )
                logger.info(f"Уведомление о запуске отправлено в чат {DEV_CHAT_ID}")
            except Exception as startup_err:
                logger.warning(
                    f"Не удалось отправить уведомление о запуске: {startup_err}"
                )

        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при поллинге: {e}")
    finally:
        # Отменяем фоновые задачи при выходе
        for task in tasks:
            task.cancel()
        await close_db()
        await close_weather_session()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
