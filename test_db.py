import asyncio
from database import get_all_admins, get_user_rating_history

async def test():
    admins = await get_all_admins()
    print("Admins:", admins)
    if admins:
        history = await get_user_rating_history(admins[0][0])
        print("History:", history)

asyncio.run(test())
