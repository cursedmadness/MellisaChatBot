import aiohttp
import logging
import os
from dotenv import load_dotenv

load_dotenv()

YANDEX_WEATHER_API_KEY = os.getenv("YANDEX_WEATHER_API_KEY")
YANDEX_GEOCODER_API_KEY = os.getenv("YANDEX_GEOCODER_API_KEY")

logger = logging.getLogger(__name__)

async def get_coordinates(city_name: str):
    """Преобразует название города в координаты (lat, lon) через Yandex Geocoder."""
    if not YANDEX_GEOCODER_API_KEY:
        logger.warning("YANDEX_GEOCODER_API_KEY не установлен")
        return None, None
    
    url = "https://geocode-maps.yandex.ru/1.x/"
    params = {
        "apikey": YANDEX_GEOCODER_API_KEY,
        "geocode": city_name,
        "format": "json",
        "results": 1
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    feature_member = data["response"]["GeoObjectCollection"]["featureMember"]
                    if feature_member:
                        point = feature_member[0]["GeoObject"]["Point"]["pos"]
                        lon, lat = map(float, point.split())
                        return lat, lon
                    else:
                        logger.warning(f"Город '{city_name}' не найден")
                else:
                    logger.error(f"Ошибка Геокодера: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при запросе к Геокодеру: {e}")
    
    return None, None

async def get_weather(lat: float, lon: float):
    """Получает данные о погоде через Yandex Weather API."""
    if not YANDEX_WEATHER_API_KEY:
        logger.warning("YANDEX_WEATHER_API_KEY не установлен")
        return None
    
    url = "https://api.weather.yandex.ru/v2/forecast"
    headers = {"X-Yandex-API-Key": YANDEX_WEATHER_API_KEY}
    params = {"lat": lat, "lon": lon, "lang": "ru_RU", "limit": 1}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Ошибка Яндекс Погоды: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при запросе к Яндекс Погоде: {e}")
    
    return None

def format_weather_message(weather_data: dict, concise: bool = False) -> str:
    """Форматирует данные о погоде в красивую строку."""
    try:
        fact = weather_data["fact"]
        temp = fact["temp"]
        feels_like = fact["feels_like"]
        condition = fact["condition"]
        
        # Словарь условий (упрощенный)
        conditions = {
            "clear": "Ясно ☀️",
            "partly-cloudy": "Малооблачно ⛅",
            "cloudy": "Облачно с прояснениями 🌥️",
            "overcast": "Пасмурно ☁️",
            "drizzle": "Морось 🌦️",
            "light-rain": "Небольшой дождь 🌧️",
            "rain": "Дождь 🌧️",
            "moderate-rain": "Умеренно сильный дождь 🌧️",
            "heavy-rain": "Сильный дождь 🌧️",
            "continuous-heavy-rain": "Длительный сильный дождь 🌧️",
            "showers": "Ливень 🌊",
            "wet-snow": "Дождь со снегом 🌨️",
            "light-snow": "Небольшой снег ❄️",
            "snow": "Снег ❄️",
            "snow-showers": "Снегопад ❄️",
            "hail": "Град 🌨️",
            "thunderstorm": "Гроза ⚡",
            "thunderstorm-with-rain": "Дождь с грозой ⛈️",
            "thunderstorm-with-hail": "Гроза с градом ⛈️",
        }
        
        cond_text = conditions.get(condition, condition)
        
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

        if concise:
            return f"{temp_emoji} {temp}°C, {cond_text}"

        return f"\n📍 Погода сегодня:\n{temp_emoji} {temp}°C (ощущается как {feels_like}°C)\n✨ {cond_text}"
    except Exception as e:
        logger.error(f"Ошибка при форматировании погоды: {e}")
        return ""

async def get_weather_string(city_name: str, concise: bool = False) -> str:
    """Полный цикл получения погоды для города."""
    lat, lon = await get_coordinates(city_name)
    if lat is not None:
        weather_data = await get_weather(lat, lon)
        if weather_data:
            return format_weather_message(weather_data, concise=concise)
    return ""
