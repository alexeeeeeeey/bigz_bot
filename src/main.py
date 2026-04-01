import asyncio
import logging


from core.bot import bot
from core.db import init_db
from handlers.book import router as book_router
from handlers.start import router as start_router


async def main():
    logging.basicConfig()
    logging.getLogger("aiomax.bot").setLevel(logging.DEBUG)
    await init_db()
    bot.add_router(start_router)
    bot.add_router(book_router)
    await bot.start_polling()


asyncio.run(main())
