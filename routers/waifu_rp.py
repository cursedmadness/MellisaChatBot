import random
import logging
from routers.weather_service import get_coordinates, get_weather
from database import get_user_nickname, get_user_city

logger = logging.getLogger(__name__)

RP_TEMPLATES_GENERAL = [
    "*{cat_name}* подкралась сзади, нежно обняла Вас и прошептала: «Успехов тебе сегодня, {nickname}! Я всегда рядом~» 🐾",
    "*{cat_name}* легонько куснула Вас за ушко: «Эй, {nickname}, не перетруждайся там! Отдохни со мной немного~» 🌸",
    "*{cat_name}* потерлась щечкой о Ваше плечо и мурлыкнула: «{nickname}, ты самый лучший хозяин на свете...» ❤️",
    "Неожиданно *{cat_name}* запрыгнула к Вам на колени, свернулась клубочком и уснула, тихо промурчав Ваше имя... ✨",
    "*{cat_name}* поцеловала Вас в щеку и радостно произнесла: «Пусть твой день будет таким же чудесным, как ты сам, {nickname}! 💖»",
]

RP_TEMPLATES_HOT = [
    "*{cat_name}* обмахивает Вас веером и мурлычет: «Сегодня в городе {city} так жарко... Пей больше водички, {nickname}, чтобы не получить тепловой удар! ☀️»",
    "*{cat_name}* принесла холодный лимонад: «На улице настоящее пекло! Держи прохладное, {nickname}~ 🧊»",
]

RP_TEMPLATES_COLD = [
    "*{cat_name}* укрыла Вас пледом и прижалась поближе: «В городе {city} сегодня такой мороз... Давай греться вместе, {nickname}? ❄️»",
    "*{cat_name}* протянула Вам горячую кружку чая: «Там очень холодно, {nickname}. Выпей чаю и давай останемся дома~ ☕»",
]

RP_TEMPLATES_RAIN = [
    "*{cat_name}* смотрит в окно на дождь и вздыхает: «В городе {city} так сыро и дождливо... Как хорошо, что мы дома в тепле, {nickname}~ 🌧️»",
    "*{cat_name}* стряхнула капли воды с ушек и заботливо произнесла: «Если пойдешь гулять по улице, не забудь зонтик, {nickname}! ☔»",
]

RP_TEMPLATES_NICE = [
    "*{cat_name}* радостно машет хвостиком: «Сегодня в городе {city} очень солнечно, ведь такое солнышко, как ты, живет в этом городе, {nickname}! ☀️»",
    "*{cat_name}* открыла окно, впуская свежий ветерок: «Погода просто чудесная! Прямо как ты, {nickname}~ 🌸»",
]

async def generate_waifu_rp_message(user_id: int, cat_name: str) -> str:
    """Генерирует рандомное RP сообщение от кошки, учитывая погоду и город."""
    nickname = await get_user_nickname(user_id) or "хозяин"
    city = await get_user_city(user_id)
    
    templates = list(RP_TEMPLATES_GENERAL)
    
    if city:
        try:
            lat, lon = await get_coordinates(city)
            if lat and lon:
                weather_data = await get_weather(lat, lon)
                if weather_data:
                    temp_value = weather_data["main"]["temp"]
                    weather_id = weather_data["weather"][0]["id"]
                    
                    # Анализируем погоду
                    if 200 <= weather_id < 600:  # Гроза, Дождь, Морось
                        templates.extend(RP_TEMPLATES_RAIN)
                        templates.extend(RP_TEMPLATES_RAIN) # Увеличиваем шанс
                    elif weather_id == 800: # Ясно
                        templates.extend(RP_TEMPLATES_NICE)
                        templates.extend(RP_TEMPLATES_NICE)
                        
                    if temp_value >= 25:
                        templates.extend(RP_TEMPLATES_HOT)
                        templates.extend(RP_TEMPLATES_HOT)
                    elif temp_value <= 5:
                        templates.extend(RP_TEMPLATES_COLD)
                        templates.extend(RP_TEMPLATES_COLD)
        except Exception as e:
            logger.error(f"Ошибка при получении погоды для RP: {e}")

    # Выбираем шаблон
    template = random.choice(templates)
    
    # Экранируем HTML чтобы парсер не ругался (или тут мы используем markdown/HTML)
    c_name = f"<b>{cat_name}</b>"
    
    city_str = str(city).capitalize() if city else "твоём городе"
    
    return template.format(cat_name=c_name, nickname=nickname, city=city_str)
