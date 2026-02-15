from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import discord
from discord.utils import format_dt

_DURATION_RE = re.compile(r"(\d+)\s*([smhd])", re.IGNORECASE)


class ReminderAfkService:
    def __init__(self, bot, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._afk_mention_notice_cache: dict[tuple[int, int, int], float] = {}

    def enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild(guild_id, "reminder_afk.enabled", True))

    def _parse_duration(self, text: str) -> int | None:
        raw = str(text or "").strip().lower()
        if not raw:
            return None
        parts = list(_DURATION_RE.finditer(raw))
        if not parts:
            return None
        rebuilt = "".join(m.group(0).replace(" ", "") for m in parts)
        if rebuilt != raw.replace(" ", ""):
            return None
        total = 0
        for m in parts:
            n = int(m.group(1))
            unit = m.group(2).lower()
            if unit == "s":
                total += n
            elif unit == "m":
                total += n * 60
            elif unit == "h":
                total += n * 3600
            elif unit == "d":
                total += n * 86400
        max_days = int(self.settings.get("reminder_afk.max_days", 365) or 365)
        return max(1, min(total, max_days * 86400))

    async def set_afk(self, member: discord.Member, reason: str | None) -> str:
        text = (reason or "AFK").strip()[:180]
        await self.db.set_afk_status(member.guild.id, member.id, text)
        return f"Du bist jetzt AFK: **{text}**"

    async def clear_afk(self, guild_id: int, user_id: int):
        await self.db.clear_afk_status(guild_id, user_id)

    async def create_reminder(self, guild: discord.Guild, user: discord.Member, channel_id: int, when_text: str, text: str) -> tuple[bool, str]:
        seconds = self._parse_duration(when_text)
        if not seconds:
            return False, "Zeitformat ungültig. Beispiele: `10m`, `2h`, `1d12h`, `45s`."
        msg = str(text or "").strip()
        if not msg:
            return False, "Reminder-Text fehlt."
        remind_at = (datetime.now(timezone.utc) + timedelta(seconds=int(seconds))).isoformat()
        rid = await self.db.create_reminder(guild.id, user.id, int(channel_id), msg[:800], remind_at)
        dt = datetime.fromisoformat(remind_at)
        return True, f"Reminder erstellt: `#{rid}` • {format_dt(dt, style='R')} ({format_dt(dt, style='f')})"

    async def list_reminders(self, guild_id: int, user_id: int) -> list[str]:
        rows = await self.db.list_active_reminders_for_user(guild_id, user_id, limit=25)
        lines: list[str] = []
        for r in rows:
            rid = int(r[0])
            text = str(r[4])
            remind_at = str(r[5])
            try:
                dt = datetime.fromisoformat(remind_at)
                when = f"{format_dt(dt, style='R')}"
            except Exception:
                when = remind_at
            lines.append(f"`#{rid}` • {when} • {text[:120]}")
        return lines

    async def remove_reminder(self, guild_id: int, user_id: int, reminder_id: int) -> tuple[bool, str]:
        ok = await self.db.delete_active_reminder(guild_id, user_id, reminder_id)
        if not ok:
            return False, "Reminder nicht gefunden oder schon erledigt."
        return True, f"Reminder `#{int(reminder_id)}` gelöscht."

    async def tick(self):
        now = datetime.now(timezone.utc).isoformat()
        rows = await self.db.list_due_reminders(now, limit=50)
        for r in rows:
            rid = int(r[0])
            guild_id = int(r[1])
            user_id = int(r[2])
            channel_id = int(r[3])
            msg = str(r[4])
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                await self.db.mark_reminder_delivered(rid)
                continue
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except Exception:
                    member = None
            delivered = False
            if member is not None:
                try:
                    await member.send(f"⏰ **Reminder**\n{msg}")
                    delivered = True
                except Exception:
                    delivered = False

            channel = guild.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await guild.fetch_channel(channel_id)
                except Exception:
                    channel = None
            if isinstance(channel, discord.abc.Messageable):
                try:
                    await channel.send(f"⏰ {f'<@{user_id}>' if not delivered else ''} **Reminder:** {msg}")
                    delivered = True
                except Exception:
                    pass

            await self.db.mark_reminder_delivered(rid)

    async def handle_message_for_afk(self, message: discord.Message):
        if not message.guild or not isinstance(message.author, discord.Member):
            return
        if not self.enabled(message.guild.id):
            return

        author_afk = await self.db.get_afk_status(message.guild.id, message.author.id)
        if author_afk:
            await self.db.clear_afk_status(message.guild.id, message.author.id)
            set_at = str(author_afk[3] or "")
            back = "Willkommen zurück, AFK wurde entfernt."
            try:
                dt = datetime.fromisoformat(set_at)
                back = f"Willkommen zurück {message.author.mention}, AFK wurde entfernt (seit {format_dt(dt, style='R')})."
            except Exception:
                pass
            try:
                await message.reply(back, mention_author=False)
            except Exception:
                pass

        mentions = [m for m in (message.mentions or []) if isinstance(m, discord.Member) and not m.bot and m.id != message.author.id]
        if not mentions:
            return

        rows = await self.db.list_afk_status_for_users(message.guild.id, [m.id for m in mentions])
        if not rows:
            return

        now_ts = datetime.now(timezone.utc).timestamp()
        lines = []
        for row in rows:
            uid = int(row[1])
            reason = str(row[2] or "AFK")
            set_at = str(row[3] or "")
            key = (int(message.channel.id), int(message.author.id), uid)
            last = float(self._afk_mention_notice_cache.get(key, 0.0) or 0.0)
            if now_ts - last < 25:
                continue
            self._afk_mention_notice_cache[key] = now_ts
            when = ""
            try:
                dt = datetime.fromisoformat(set_at)
                when = f" (seit {format_dt(dt, style='R')})"
            except Exception:
                pass
            lines.append(f"• <@{uid}> ist AFK{when}: **{reason[:120]}**")

        if lines:
            try:
                await message.reply("\n".join(lines), mention_author=False)
            except Exception:
                pass
