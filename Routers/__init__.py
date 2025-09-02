# __init__.py
from .admin_commands import admin_router
from .user_commands import user_router
from .reg_commands import reg_router
from .activity_commands import activity_routers
from aiogram import Router

main_router = Router()

main_router.include_router(admin_router) #Роутеры админ команд
main_router.include_router(user_router) #Роутеры пользовательских команд
main_router.include_router(reg_router) #Роутеры регистрационных команд
main_router.include_router(activity_routers) #Роутеры активности