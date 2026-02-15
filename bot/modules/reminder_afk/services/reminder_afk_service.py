from __future__ import annotations

import re
from collections import Counter
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
        self._afk_notice_cache: dict[tuple[int, int, int], float] = {}
        self._afk_set_grace_cache: dict[tuple[int, int], float] = {}

    def enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild(guild_id, "reminder_afk.enabled", True))

    def _afk_notice_cooldown(self, guild_id: int) -> int:
        try:
            return max(5, int(self.settings.get_guild(guild_id, "reminder_afk.afk_notice_cooldown_seconds", 25) or 25))
        except Exception:
            return 25

    def _afk_set_grace_seconds(self, guild_id: int) -> int:
        try:
            return max(0, int(self.settings.get_guild(guild_id, "reminder_afk.afk_set_grace_seconds", 6) or 6))
        except Exception:
            return 6

    def _parse_duration(self, text: str | None) -> int | None:
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

    def _color(self, guild: discord.Guild | None) -> int:
        try:
            val = self.settings.get_guild(guild.id, "design.accent_color", "#B16B91") if guild else self.settings.get("design.accent_color", "#B16B91")
            return int(str(val).replace("#", ""), 16)
        except Exception:
            return 0xB16B91

    def _container_view(self, guild: discord.Guild | None, title: str, blocks: list[str]) -> discord.ui.LayoutView:
        view = discord.ui.LayoutView(timeout=None)
        c = discord.ui.Container(accent_colour=self._color(guild))
        c.add_item(discord.ui.TextDisplay(f"**{title}**"))
        for i, b in enumerate(blocks):
            if i > 0:
                c.add_item(discord.ui.Separator())
            c.add_item(discord.ui.TextDisplay(str(b)[:1900]))
        view.add_item(c)
        return view

    async def set_afk(self, member: discord.Member, reason: str | None, time_text: str | None = None) -> tuple[bool, str, discord.ui.LayoutView | None]:
        text = (reason or "AFK").strip()[:220]
        until_at = None
        if time_text:
            sec = self._parse_duration(time_text)
            if not sec:
                return False, "Zeitformat ungültig. Beispiele: `10m`, `2h`, `1d12h`, `45s`.", None
            until_at = (datetime.now(timezone.utc) + timedelta(seconds=int(sec))).isoformat()
        await self.db.set_afk_status(member.guild.id, member.id, text, until_at=until_at)
        await self.db.clear_afk_mention_events(member.guild.id, member.id)
        self._afk_set_grace_cache[(int(member.guild.id), int(member.id))] = datetime.now(timezone.utc).timestamp()

        set_at = datetime.now(timezone.utc)
        lines = [
            f"┏`👤` - User: {member.mention}",
            f"┣`💬` - Grund: **{text}**",
            f"┣`🕒` - Start: {format_dt(set_at, style='R')}",
        ]
        if until_at:
            try:
                dt = datetime.fromisoformat(until_at)
                lines.append(f"┗`⏳` - Ende: {format_dt(dt, style='R')} ({format_dt(dt, style='f')})")
            except Exception:
                lines.append("┗`⏳` - Ende: gesetzt")
        else:
            lines.append("┗`⏳` - Ende: manuell oder bei nächster Nachricht")
        view = self._container_view(member.guild, "💤 𑁉 AFK AKTIV", ["\n".join(lines)])
        return True, "AFK gesetzt.", view

    async def clear_afk(self, guild_id: int, user_id: int):
        await self.db.clear_afk_status(guild_id, user_id)

    async def clear_afk_with_summary(self, guild: discord.Guild, user: discord.Member) -> tuple[bool, discord.ui.LayoutView | None]:
        row = await self.db.get_afk_status(guild.id, user.id)
        if not row:
            return False, None
        set_at = str(row[3] or "")
        events = await self.db.list_afk_mention_events(guild.id, user.id, limit=600)
        await self.db.clear_afk_status(guild.id, user.id)
        await self.db.clear_afk_mention_events(guild.id, user.id)

        now = datetime.now(timezone.utc)
        duration_text = "unbekannt"
        try:
            started = datetime.fromisoformat(set_at)
            duration_text = format_dt(started, style='R')
            total_seconds = max(0, int((now - started).total_seconds()))
        except Exception:
            total_seconds = 0

        total_mentions = len(events)
        pingers = Counter(int(e[3]) for e in events)
        channels = {int(e[4]) for e in events}
        top = pingers.most_common(5)

        top_lines = []
        for uid, cnt in top:
            top_lines.append(f"• <@{uid}> — **{cnt}x**")
        if not top_lines:
            top_lines = ["• Niemand hat dich erwähnt."]

        recent_lines = []
        for e in events[-5:]:
            ch_id = int(e[4])
            msg_id = int(e[5])
            created = str(e[6] or "")
            when = ""
            try:
                when = format_dt(datetime.fromisoformat(created), style='R')
            except Exception:
                pass
            link = f"https://discord.com/channels/{guild.id}/{ch_id}/{msg_id}"
            recent_lines.append(f"• {when or '—'} in <#{ch_id}> • [Jump]({link})")
        if not recent_lines:
            recent_lines = ["• Keine letzten Erwähnungen vorhanden."]

        summary = [
            f"┏`👋` - Willkommen zurück {user.mention}",
            f"┣`🕒` - AFK seit: {duration_text}",
            f"┣`⏱️` - Dauer: **{total_seconds // 60}m {total_seconds % 60}s**",
            f"┣`🔔` - Erwähnungen: **{total_mentions}**",
            f"┗`🧭` - Kanäle: **{len(channels)}**",
        ]
        view = self._container_view(
            guild,
            "✅ 𑁉 AFK ENTFERNT · ZUSAMMENFASSUNG",
            ["\n".join(summary), "**Top-Pinger**\n" + "\n".join(top_lines), "**Letzte Erwähnungen**\n" + "\n".join(recent_lines)],
        )
        return True, view

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

    async def _tick_expired_afk(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        rows = await self.db.list_expired_afk_status(now_iso, limit=50)
        for row in rows:
            gid = int(row[0])
            uid = int(row[1])
            await self.db.clear_afk_status(gid, uid)
            # Events behalten wir, damit bei nächster Nachricht eine echte Summary kommen kann.

    async def tick(self):
        await self._tick_expired_afk()

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
            grace = self._afk_set_grace_seconds(message.guild.id)
            key_self = (int(message.guild.id), int(message.author.id))
            set_ts = float(self._afk_set_grace_cache.get(key_self, 0.0) or 0.0)
            try:
                db_set_ts = datetime.fromisoformat(str(author_afk[3] or "")).timestamp()
            except Exception:
                db_set_ts = 0.0
            effective_set_ts = max(set_ts, db_set_ts)
            if (datetime.now(timezone.utc).timestamp() - effective_set_ts) > grace:
                ok, summary_view = await self.clear_afk_with_summary(message.guild, message.author)
                if ok and summary_view:
                    self._afk_set_grace_cache.pop(key_self, None)
                    try:
                        await message.reply(view=summary_view, mention_author=False)
                    except Exception:
                        pass

        mentions = [m for m in (message.mentions or []) if isinstance(m, discord.Member) and not m.bot and m.id != message.author.id]
        if not mentions:
            return

        rows = await self.db.list_afk_status_for_users(message.guild.id, [m.id for m in mentions])
        if not rows:
            return

        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        cooldown = self._afk_notice_cooldown(message.guild.id)
        lines = []
        for row in rows:
            uid = int(row[1])
            reason = str(row[2] or "AFK")
            set_at = str(row[3] or "")
            until_at = str(row[4] or "")

            # Expired timed AFK: clear silently.
            if until_at:
                try:
                    until_dt = datetime.fromisoformat(until_at)
                    if until_dt <= now:
                        await self.db.clear_afk_status(message.guild.id, uid)
                        continue
                except Exception:
                    pass

            await self.db.add_afk_mention_event(message.guild.id, uid, message.author.id, message.channel.id, message.id)

            key = (int(message.channel.id), int(message.author.id), uid)
            last = float(self._afk_notice_cache.get(key, 0.0) or 0.0)
            if now_ts - last < cooldown:
                continue
            self._afk_notice_cache[key] = now_ts

            when = ""
            try:
                dt = datetime.fromisoformat(set_at)
                when = f"seit {format_dt(dt, style='R')}"
            except Exception:
                pass
            until_txt = ""
            if until_at:
                try:
                    dt_u = datetime.fromisoformat(until_at)
                    until_txt = f" • Ende {format_dt(dt_u, style='R')}"
                except Exception:
                    pass
            lines.append(f"• <@{uid}> ist AFK ({when}){until_txt}\n┗ Grund: **{reason[:160]}**")

        if lines:
            try:
                view = self._container_view(message.guild, "💤 𑁉 AFK INFO", ["\n".join(lines)])
                await message.reply(view=view, mention_author=False)
            except Exception:
                pass
