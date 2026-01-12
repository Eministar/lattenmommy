import discord
from discord.ext import tasks

_PRESENCE_TEXT_1 = "💌 Schreib mir eine DM für Support"
_PRESENCE_TOTAL_FMT = "🎫 Tickets insgesamt: {total}"
_PRESENCE_OPEN_FMT = "🟢 Offene Tickets: {open}"


class PresenceRotator:
    def __init__(self, bot: discord.Client, db, interval_seconds: int = 20):
        self.bot = bot
        self.db = db
        self._i = 0
        self._loop.change_interval(seconds=max(12, int(interval_seconds)))

    def start(self):
        if not self._loop.is_running():
            self._loop.start()

    def stop(self):
        if self._loop.is_running():
            self._loop.cancel()

    async def _fetch_count(self, query: str) -> int:
        conn = (
            getattr(self.db, "conn", None)
            or getattr(self.db, "_conn", None)
            or getattr(self.db, "connection", None)
        )

        if conn is not None:
            cur = await conn.execute(query)
            row = await cur.fetchone()
            try:
                await cur.close()
            except Exception:
                pass
            return int(row[0]) if row and row[0] is not None else 0

        if hasattr(self.db, "execute"):
            cur = await self.db.execute(query)
            row = await cur.fetchone()
            try:
                await cur.close()
            except Exception:
                pass
            return int(row[0]) if row and row[0] is not None else 0

        return 0

    async def _get_stats(self) -> tuple[int, int]:
        total = await self._fetch_count("SELECT COUNT(*) FROM tickets")
        open_ = await self._fetch_count("SELECT COUNT(*) FROM tickets WHERE status IS NULL OR status != 'closed'")
        return total, open_

    @tasks.loop(seconds=20)
    async def _loop(self):
        total, open_ = await self._get_stats()

        states = [
            _PRESENCE_TEXT_1,
            _PRESENCE_TOTAL_FMT.format(total=total),
            _PRESENCE_OPEN_FMT.format(open=open_),
        ]

        text = states[self._i % len(states)]
        self._i += 1

        activity = discord.Activity(type=discord.ActivityType.watching, name=text)
        try:
            await self.bot.change_presence(activity=activity, status=discord.Status.online)
        except Exception:
            pass

    @_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()
