# __init__.py
from .admin_commands import admin_router
from .user_commands import user_router
from .activity_commands import activity_routers
from .waifu_cat import waifu_cat_router
from .hebao import hebao_router
from .rules import rules_router
from aiogram import Router

main_router = Router() # подключение роутеров

main_router.include_router(admin_router) #Роутеры админ команд
main_router.include_router(user_router) #Роутеры команд граждан
main_router.include_router(waifu_cat_router) #Роутеры waifu/cat
main_router.include_router(hebao_router) #Роутеры хэбао (инвентарь)
main_router.include_router(rules_router) #Роутеры правил чата
main_router.include_router(activity_routers) #Роутеры активности (последними, чтобы не перехватывать команды)
