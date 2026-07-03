import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from bot.config import BOT_TOKEN
from bot.db import init_db
from bot.handlers import routers

logging.basicConfig(level=logging.INFO)


async def _start_health_server() -> None:
    """Bind the PORT Render assigns so Web Service deploys pass the port scan.

    Without this, Render kills the process ("Timed Out") and restarts it,
    causing TelegramConflictError between the old and new instances.
    """
    port = os.getenv("PORT")
    if not port:
        return

    async def health(_request):
        return web.Response(text="Rashid Help bot is running")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(port))
    await site.start()
    logging.info("Health server listening on port %s", port)


async def run() -> None:
    await init_db()
    await _start_health_server()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message.middleware()
    async def register_group_middleware(handler, message, data):
        if message.chat.type in ("group", "supergroup"):
            from bot.db import ensure_group
            await ensure_group(message.chat.id, message.chat.title or "")
        return await handler(message, data)

    for router in routers:
        dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
