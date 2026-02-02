import discord
from discord.ext import tasks

_PRESENCE_TEXT_1 = "💌 𑁉 Schreib mir eine DM für Support"


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

    async def _fetch_sum(self, query: str) -> int:
        return await self._fetch_count(query)

    async def _get_stats(self) -> dict[str, int]:
        driver = getattr(self.db, "_driver", None) or ""
        total_tickets = await self._fetch_count("SELECT COUNT(*) FROM tickets")
        open_tickets = await self._fetch_count("SELECT COUNT(*) FROM tickets WHERE status IS NULL OR status != 'closed'")
        total_users = await self._fetch_count("SELECT COUNT(*) FROM user_stats")
        total_messages = await self._fetch_sum("SELECT COALESCE(SUM(message_count), 0) FROM user_stats")
        total_voice_hours = await self._fetch_sum("SELECT COALESCE(SUM(voice_seconds), 0) FROM user_stats") // 3600
        if driver == "mysql":
            active_users_query = (
                "SELECT COUNT(*) FROM user_stats "
                "WHERE (last_message_at IS NOT NULL AND "
                "STR_TO_DATE(REPLACE(SUBSTRING(last_message_at, 1, 19), 'T', ' '), '%Y-%m-%d %H:%i:%s') "
                ">= DATE_SUB(NOW(), INTERVAL 1 DAY)) "
                "OR (last_voice_at IS NOT NULL AND "
                "STR_TO_DATE(REPLACE(SUBSTRING(last_voice_at, 1, 19), 'T', ' '), '%Y-%m-%d %H:%i:%s') "
                ">= DATE_SUB(NOW(), INTERVAL 1 DAY))"
            )
        else:
            active_users_query = (
                "SELECT COUNT(*) FROM user_stats "
                "WHERE (last_message_at IS NOT NULL AND datetime(last_message_at) >= datetime('now','-1 day')) "
                "OR (last_voice_at IS NOT NULL AND datetime(last_voice_at) >= datetime('now','-1 day'))"
            )
        active_users = await self._fetch_count(active_users_query)
        warns = await self._fetch_count("SELECT COUNT(*) FROM infractions WHERE action = 'warn'")
        giveaways_open = await self._fetch_count("SELECT COUNT(*) FROM giveaways WHERE status = 'open'")
        polls_open = await self._fetch_count("SELECT COUNT(*) FROM polls WHERE status = 'open'")
        applications_open = await self._fetch_count("SELECT COUNT(*) FROM applications WHERE status = 'open'")
        wzs_submissions = await self._fetch_count("SELECT COUNT(*) FROM wzs_submissions")

        return {
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "total_users": total_users,
            "total_messages": total_messages,
            "total_voice_hours": total_voice_hours,
            "active_users": active_users,
            "warns": warns,
            "giveaways_open": giveaways_open,
            "polls_open": polls_open,
            "applications_open": applications_open,
            "wzs_submissions": wzs_submissions,
        }

    @tasks.loop(seconds=20)
    async def _loop(self):
        s = await self._get_stats()

        states = [
            (discord.ActivityType.listening, _PRESENCE_TEXT_1),
            (discord.ActivityType.watching, f"🟢 𑁉 Aktive User (24h): {s['active_users']}"),
            (discord.ActivityType.watching, f"💬 𑁉 Nachrichten gesamt: {s['total_messages']}"),
            (discord.ActivityType.watching, f"🎙️ 𑁉 Voice-Stunden: {s['total_voice_hours']}"),
            (discord.ActivityType.playing, f"🎫 𑁉 Tickets gesamt: {s['total_tickets']}"),
            (discord.ActivityType.watching, f"🟡 𑁉 Offene Tickets: {s['open_tickets']}"),
            (discord.ActivityType.watching, f"⚠️ 𑁉 Warnungen: {s['warns']}"),
            (discord.ActivityType.watching, f"🎁 𑁉 Giveaways offen: {s['giveaways_open']}"),
            (discord.ActivityType.watching, f"📊 𑁉 Umfragen offen: {s['polls_open']}"),
            (discord.ActivityType.watching, f"📝 𑁉 Bewerbungen offen: {s['applications_open']}"),
            (discord.ActivityType.watching, f"📜 𑁉 Weisheiten: {s['wzs_submissions']}"),
            (discord.ActivityType.watching, f"👥 𑁉 User im System: {s['total_users']}"),
        ]

        activity_type, text = states[self._i % len(states)]
        self._i += 1

        activity = discord.Activity(type=activity_type, name=text)
        try:
            await self.bot.change_presence(activity=activity, status=discord.Status.online)
        except Exception:
            pass

    @_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()
