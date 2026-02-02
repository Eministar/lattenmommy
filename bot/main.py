import os
import asyncio
import signal
import traceback
from dotenv import load_dotenv

from bot.core.settings import SettingsManager
from bot.core.db import Database
from bot.core.logger import StarryLogger
from bot.core.bot import StarryBot
from bot.web.server import WebServer


def _mask_token(token: str) -> str:
    t = (token or "").strip()
    if len(t) <= 10:
        return "****"
    return t[:4] + "…" + t[-4:]


def _load_token(settings: SettingsManager) -> str:
    cfg_token = str(settings.get("bot.token", "") or "").strip()
    env_token = str(os.getenv("DISCORD_TOKEN", "") or "").strip()

    token = cfg_token if cfg_token else env_token
    if not token:
        raise RuntimeError("Kein Discord Token gefunden. Setz bot.token in config.yml oder DISCORD_TOKEN als Env-Var.")

    if cfg_token:
        print(f"[SECURITY] bot.token wird aus config.yml genutzt ({_mask_token(cfg_token)}). Bitte config.yml NICHT committen.")
    else:
        print(f"[OK] Token wird aus DISCORD_TOKEN genutzt ({_mask_token(env_token)}).")

    return token


async def main():
    load_dotenv()

    settings = SettingsManager(
        config_path="config/config.yml",
        override_path="data/settings.json",
    )
    await settings.load()

    token = _load_token(settings)

    db_type = str(settings.get("database.type", "sqlite") or "sqlite").lower()
    if db_type == "mysql":
        mysql_cfg = settings.get("database.mysql", {}) or {}
        db = Database(mysql=mysql_cfg)
    else:
        sqlite_path = str(settings.get("database.sqlite_path", "data/starry.db") or "data/starry.db")
        db = Database(path=sqlite_path)
    await db.init()
    await settings.load_guild_overrides(db)

    logger = StarryLogger(settings=settings, db=db)

    bot = StarryBot(settings=settings, db=db, logger=logger)

    web = WebServer(settings=settings, db=db, bot=bot)

    stop_event = asyncio.Event()

    def _request_shutdown():
        if not stop_event.is_set():
            stop_event.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _request_shutdown)
            except NotImplementedError:
                pass
    except Exception:
        pass

    await web.start()
    dash_host = settings.get("bot.dashboard.host", "0.0.0.0")
    dash_port = int(settings.get("bot.dashboard.port", 8787))
    print(f"[OK] Dashboard läuft auf {dash_host}:{dash_port}")

    async def _run_bot():
        try:
            await bot.start(token)
        except Exception as exc:
            print(f"[ERROR] Bot-Start fehlgeschlagen ({type(exc).__name__}): {exc}")
            traceback.print_exc()
            raise

    bot_task = asyncio.create_task(_run_bot())
    stop_task = asyncio.create_task(stop_event.wait())

    done, pending = await asyncio.wait(
        {bot_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED
    )

    if bot_task in done:
        try:
            bot_task.result()
        except Exception:
            pass

    if stop_task in done and not bot_task.done():
        try:
            await bot.close()
        except Exception:
            pass

    for task in pending:
        task.cancel()
        try:
            await task
        except Exception:
            pass

    try:
        await web.stop()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
