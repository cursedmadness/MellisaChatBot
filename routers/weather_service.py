import aiohttp
import asyncio
import logging
import os
from dotenv import load_dotenv

load_dotenv()

OWM_API_KEY = os.getenv("OWM_API_KEY")

logger = logging.getLogger(__name__)

# Глобальная сессия для переиспользования соединений
_weather_session: aiohttp.ClientSession | None = None


async def get_weather_session() -> aiohttp.ClientSession:
    """Возвращает глобальную aiohttp сессию для погодных запросов."""
    global _weather_session
    if _weather_session is None or _weather_session.closed:
        timeout = aiohttp.ClientTimeout(total=10)
        _weather_session = aiohttp.ClientSession(timeout=timeout)
    return _weather_session


async def close_weather_session():
    """Закрывает глобальную сессию погодных запросов."""
    global _weather_session
    if _weather_session and not _weather_session.closed:
        await _weather_session.close()
        _weather_session = None


async def get_coordinates(city_name: str):
    """Преобразует название города в координаты (lat, lon) через OpenWeatherMap Geocoding API."""
    if not OWM_API_KEY:
        logger.warning("OWM_API_KEY не установлен")
        return None, None

    url = "https://api.openweathermap.org/geo/1.0/direct"
    params = {
        "q": city_name,
        "limit": 1,
        "appid": OWM_API_KEY,
    }

    try:
        session = await get_weather_session()
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data:
                    return data[0]["lat"], data[0]["lon"]
                else:
                    logger.warning(f"Город '{city_name}' не найден")
            else:
                logger.error(f"Ошибка Геокодера OWM: {response.status}")
    except asyncio.TimeoutError:
        logger.error(f"Таймаут запроса к Геокодеру OWM для города '{city_name}'")
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при запросе к Геокодеру OWM: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при запросе к Геокодеру OWM: {e}")

    return None, None


async def get_weather(lat: float, lon: float):
    """Получает данные о погоде через OpenWeatherMap API."""
    if not OWM_API_KEY:
        logger.warning("OWM_API_KEY не установлен")
        return None

    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": OWM_API_KEY,
        "units": "metric",
        "lang": "ru",
    }

    try:
        session = await get_weather_session()
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
            else:
                logger.error(f"Ошибка OpenWeatherMap: {response.status}")
    except asyncio.TimeoutError:
        logger.error(f"Таймаут запроса к OpenWeatherMap для координат ({lat}, {lon})")
    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при запросе к OpenWeatherMap: {e}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка при запросе к OpenWeatherMap: {e}")

    return None


def format_weather_message(
    weather_data: dict, city_name: str = "", concise: bool = False
) -> str:
    """Форматирует данные о погоде в красивую строку."""
    try:
        temp = round(weather_data["main"]["temp"])
        feels_like = round(weather_data["main"]["feels_like"])
        humidity = weather_data["main"]["humidity"]
        wind_speed = weather_data["wind"]["speed"]
        weather_id = weather_data["weather"][0]["id"]
        description = weather_data["weather"][0]["description"].capitalize()

        # Маппинг OWM weather condition codes → эмодзи + текст
        conditions = {
            # Group 2xx: Thunderstorm
            range(200, 210): "Гроза ⚡",
            range(210, 220): "Гроза ⚡",
            range(220, 233): "Гроза с дождём ⛈️",
            # Group 3xx: Drizzle
            range(300, 322): "Морось 🌦️",
            # Group 5xx: Rain
            range(500, 501): "Небольшой дождь 🌧️",
            range(501, 502): "Дождь 🌧️",
            range(502, 505): "Сильный дождь 🌧️",
            range(520, 532): "Ливень 🌊",
            # Group 6xx: Snow
            range(600, 601): "Небольшой снег ❄️",
            range(601, 602): "Снег ❄️",
            range(602, 603): "Снегопад ❄️",
            range(611, 617): "Дождь со снегом 🌨️",
            range(620, 623): "Снегопад ❄️",
            # Group 7xx: Atmosphere
            range(701, 782): "Туман 🌫️",
            # Group 800: Clear
            range(800, 801): "Ясно ☀️",
            # Group 80x: Clouds
            range(801, 802): "Малооблачно ⛅",
            range(802, 803): "Облачно с прояснениями 🌥️",
            range(803, 805): "Пасмурно ☁️",
        }

        cond_text = description
        for id_range, text in conditions.items():
            if weather_id in id_range:
                cond_text = text
                break

        # Кастомизация по температуре
        if temp >= 30:
            temp_emoji = "🔥"
        elif temp >= 20:
            temp_emoji = "☀️"
        elif temp >= 10:
            temp_emoji = "🌤️"
        elif temp >= 0:
            temp_emoji = "☁️"
        elif temp >= -10:
            temp_emoji = "❄️"
        else:
            temp_emoji = "🥶"

        city_display = city_name.capitalize() if city_name else "вашем городе"
        header = (
            f"🏛 Исходя из погодных сводок Партии погода в городе <b>{city_display}</b>:"
        )

        if concise:
            return (
                f"{header}\n"
                f"├ {temp_emoji} {temp}°C · {cond_text}\n"
                f"└ 💨 {wind_speed} м/с · 💧 {humidity}%"
            )

        return (
            f"{header}\n\n"
            f"🌡 Температура: <b>{temp}°C</b> (ощущается как {feels_like}°C)\n"
            f"✨ Условия: {cond_text}\n"
            f"💨 Ветер: {wind_speed} м/с\n"
            f"💧 Влажность: {humidity}%"
        )
    except Exception as e:
        logger.error(f"Ошибка при форматировании погоды: {e}")
        return ""


async def get_weather_string(city_name: str, concise: bool = False) -> str:
    """Полный цикл получения погоды для города."""
    lat, lon = await get_coordinates(city_name)
    if lat is not None:
        weather_data = await get_weather(lat, lon)
        if weather_data:
            return format_weather_message(
                weather_data, city_name=city_name, concise=concise
            )
    return ""
