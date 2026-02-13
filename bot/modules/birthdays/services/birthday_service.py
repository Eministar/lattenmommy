import calendar
import json
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
import discord
from bot.modules.birthdays.formatting.birthday_embeds import build_birthday_announcement_view


class BirthdayService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _tz(self, guild_id: int):
        tz_name = str(self.settings.get_guild(guild_id, "birthday.timezone", "UTC") or "UTC")
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return timezone.utc

    def _emoji(self, guild: discord.Guild, key: str, fallback: str):
        from bot.utils.emojis import em
        return em(self.settings, key, guild) or fallback

    def _resolve_emoji(self, guild: discord.Guild | None, token: str | None) -> str:
        from bot.utils.emojis import em
        t = str(token or "").strip()
        if not t:
            return "🏆"
        if t.startswith("<") and t.endswith(">"):
            return t
        key = t[1:-1] if t.startswith(":") and t.endswith(":") else t
        resolved = em(self.settings, key, guild)
        return resolved if resolved else t

    def _embed_color(self, member: discord.Member | None, guild: discord.Guild | None = None) -> int:
        try:
            if member and int(member.color.value) != 0:
                return int(member.color.value)
        except Exception:
            pass
        target_guild = guild or (member.guild if member else None)
        if target_guild:
            raw = self.settings.get_guild(target_guild.id, "design.accent_color", "#B16B91")
        else:
            raw = self.settings.get("design.accent_color", "#B16B91")
        v = str(raw or "").replace("#", "").strip()
        try:
            return int(v, 16)
        except Exception:
            return 0xB16B91

    def _safe_date(self, year: int, month: int, day: int) -> date:
        last_day = calendar.monthrange(year, month)[1]
        return date(int(year), int(month), min(int(day), last_day))

    def _next_occurrence(self, day: int, month: int, today: date) -> date:
        candidate = self._safe_date(today.year, month, day)
        if candidate < today:
            candidate = self._safe_date(today.year + 1, month, day)
        return candidate

    def _collect_guild_birthdays(self, guild: discord.Guild, rows: list[tuple], now: datetime):
        members = {m.id: m for m in guild.members}
        today_entries: list[dict] = []
        all_entries: list[dict] = []
        for row in rows:
            try:
                uid = int(row[0])
                day = int(row[1])
                month = int(row[2])
                year = int(row[3])
            except Exception:
                continue
            if month < 1 or month > 12 or day < 1 or day > 31:
                continue
            member = members.get(uid)
            if not member:
                continue
            entry = {
                "user_id": uid,
                "day": day,
                "month": month,
                "year": year,
                "member": member,
            }
            all_entries.append(entry)
            if day == now.day and month == now.month:
                entry_today = dict(entry)
                entry_today["age"] = now.year - year
                today_entries.append(entry_today)

        today_entries.sort(key=lambda e: (str(e["member"].display_name).lower(), int(e["user_id"])))
        return today_entries, all_entries

    def _build_next_entries(self, entries: list[dict], today: date, limit: int):
        next_entries: list[dict] = []
        for entry in entries:
            next_date = self._next_occurrence(entry["day"], entry["month"], today)
            days_until = int((next_date - today).days)
            if days_until == 0:
                continue
            payload = dict(entry)
            payload["days_until"] = days_until
            payload["next_date"] = next_date
            payload["turns"] = next_date.year - int(entry["year"])
            next_entries.append(payload)
        next_entries.sort(key=lambda e: (int(e["days_until"]), int(e["month"]), int(e["day"]), int(e["user_id"])))
        return next_entries[: max(0, int(limit))]

    async def _resolve_channel(self, guild: discord.Guild, channel_id: int):
        ch = guild.get_channel(int(channel_id))
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return None
        return ch

    async def _delete_announcement_message(self, guild: discord.Guild, channel_id: int | None, message_id: int | None):
        if not channel_id or not message_id:
            return
        ch = await self._resolve_channel(guild, int(channel_id))
        if not ch:
            return
        try:
            msg = await ch.fetch_message(int(message_id))
        except Exception:
            msg = None
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass

    async def set_birthday(self, interaction: discord.Interaction, day: int, month: int, year: int):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        try:
            datetime(int(year), int(month), int(day))
        except Exception:
            return await interaction.response.send_message("Ungültiges Datum.", ephemeral=True)

        await self.db.set_birthday_global(interaction.user.id, int(day), int(month), int(year))
        await self._apply_age_roles(interaction.user, int(year))
        await self._grant_success(interaction.user)
        await interaction.response.send_message("Geburtstag gespeichert. 🎉", ephemeral=True)
        try:
            await self.announce_today(interaction.guild)
        except Exception:
            pass

    async def remove_birthday(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        await self.db.remove_birthday_global(interaction.user.id)
        await interaction.response.send_message("Geburtstag entfernt.", ephemeral=True)
        try:
            await self.announce_today(interaction.guild)
        except Exception:
            pass

    async def handle_member_join(self, member: discord.Member):
        guild = member.guild
        if not guild or member.bot:
            return
        try:
            await self.announce_today(guild)
        except Exception:
            pass

    async def handle_member_remove(self, member: discord.Member):
        guild = member.guild
        if not guild or member.bot:
            return
        try:
            await self.db.remove_birthday(int(guild.id), int(member.id))
        except Exception:
            pass
        try:
            await self.db.remove_birthday_global(int(member.id))
        except Exception:
            pass
        try:
            await self.announce_today(guild)
        except Exception:
            pass

    async def _apply_age_roles(self, member: discord.Member, year: int):
        now = datetime.now(self._tz(member.guild.id))
        age = now.year - int(year)
        under_role_id = self.settings.get_guild_int(member.guild.id, "birthday.under_18_role_id")
        adult_role_id = self.settings.get_guild_int(member.guild.id, "birthday.adult_role_id")
        under_role = member.guild.get_role(under_role_id) if under_role_id else None
        adult_role = member.guild.get_role(adult_role_id) if adult_role_id else None

        if age < 18:
            if under_role and under_role not in member.roles:
                try:
                    await member.add_roles(under_role, reason="Birthday under 18")
                except Exception:
                    pass
            if adult_role and adult_role in member.roles:
                try:
                    await member.remove_roles(adult_role, reason="Birthday under 18")
                except Exception:
                    pass
        else:
            if adult_role and adult_role not in member.roles:
                try:
                    await member.add_roles(adult_role, reason="Birthday 18+")
                except Exception:
                    pass
            if under_role and under_role in member.roles:
                try:
                    await member.remove_roles(under_role, reason="Birthday 18+")
                except Exception:
                    pass

    async def _grant_success(self, member: discord.Member):
        await self._ensure_success_role(member)
        code = "birthday_set"
        await self.db.add_achievement(member.guild.id, member.id, code)
        await self._grant_achievement_role(member, code)
        await self._dm_achievement(member, code)
        await self._ensure_birthday_role(member)

    async def _ensure_success_role(self, member: discord.Member):
        role_id = self.settings.get_guild_int(member.guild.id, "birthday.success_role_id")
        if role_id:
            role = member.guild.get_role(role_id)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Birthday achievement")
                except Exception:
                    pass

    async def ensure_birthday_achievement(self, member: discord.Member) -> bool:
        row = await self.db.get_birthday_global(member.id)
        if not row:
            return False
        day, month, year = int(row[0]), int(row[1]), int(row[2])
        await self._apply_age_roles(member, year)
        await self._ensure_success_role(member)
        await self._ensure_birthday_role(member)

        code = "birthday_set"
        rows = await self.db.list_achievements(member.guild.id, member.id)
        existing = {r[0] for r in rows}
        if code in existing:
            await self._grant_achievement_role(member, code)
            return False
        await self.db.add_achievement(member.guild.id, member.id, code)
        await self._grant_achievement_role(member, code)
        await self._dm_achievement(member, code)
        return True

    async def _ensure_birthday_role(self, member: discord.Member):
        role_id = self.settings.get_guild_int(member.guild.id, "birthday.role_id")
        if not role_id:
            return
        role = member.guild.get_role(role_id)
        if role and role not in member.roles:
            try:
                await member.add_roles(role, reason="Birthday role")
            except Exception:
                pass

    async def ensure_roles(self, guild: discord.Guild):
        if not guild:
            return
        birthday_role_name = str(self.settings.get_guild(guild.id, "birthday.role_name", "🎂 • GEBURTSTAG") or "🎂 • GEBURTSTAG")
        under_name = str(self.settings.get_guild(guild.id, "birthday.under_18_role_name", "🧒 • U18") or "🧒 • U18")
        adult_name = str(self.settings.get_guild(guild.id, "birthday.adult_role_name", "🔞 • 18+") or "🔞 • 18+")
        success_name = str(self.settings.get_guild(guild.id, "birthday.success_role_name", "🏆 • GEBURTSTAG") or "🏆 • GEBURTSTAG")

        await self._ensure_role(guild, "birthday.role_id", birthday_role_name)
        await self._ensure_role(guild, "birthday.under_18_role_id", under_name)
        await self._ensure_role(guild, "birthday.adult_role_id", adult_name)
        await self._ensure_role(guild, "birthday.success_role_id", success_name)

    async def _ensure_role(self, guild: discord.Guild, settings_path: str, name: str):
        role_id = self.settings.get_guild_int(guild.id, settings_path)
        role = guild.get_role(role_id) if role_id else None
        if not role:
            try:
                role = await guild.create_role(name=name, reason="Auto role (birthday)")
            except Exception:
                role = None
            if role:
                await self.settings.set_guild_override(self.db, guild.id, settings_path, int(role.id))
                await self._announce_created_roles(guild, [role], "Geburtstagsrollen")

    async def _announce_created_roles(self, guild: discord.Guild, roles: list[discord.Role], title: str):
        if not roles:
            return
        ch_id = self.settings.get_guild_int(guild.id, "roles.announce_channel_id") or self.settings.get_guild_int(guild.id, "bot.log_channel_id")
        if not ch_id:
            return
        ch = guild.get_channel(ch_id)
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(ch_id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return
        lines = [f"• **{r.name}**\n  ┗ `ID`: `{r.id}`" for r in roles]
        text = "\n".join(lines)
        emb = discord.Embed(
            title=f"🧩 𑁉 {title}",
            description=text,
            color=0xB16B91,
        )
        emb.set_footer(text="Auto-Rollen erstellt und gespeichert")
        try:
            await ch.send(embed=emb)
        except Exception:
            pass

    async def _grant_achievement_role(self, member: discord.Member, code: str):
        achievements = self.settings.get_guild(member.guild.id, "achievements.items", []) or []
        payload = next((a for a in achievements if str(a.get("code")) == code), None)
        if not payload:
            return
        role_id = int(payload.get("role_id", 0) or 0)
        if not role_id:
            return
        role = member.guild.get_role(role_id)
        if role and role not in member.roles:
            try:
                await member.add_roles(role, reason="Achievement unlocked")
            except Exception:
                pass

    async def _dm_achievement(self, member: discord.Member, code: str):
        achievements = self.settings.get_guild(member.guild.id, "achievements.items", []) or []
        payload = next((a for a in achievements if str(a.get("code")) == code), None)
        if not payload:
            return
        msg = str(payload.get("dm_message", "") or "").strip()
        if not msg:
            return
        try:
            emb = self._achievement_dm_embed(member, payload, msg)
            await member.send(embed=emb)
        except Exception:
            pass

    def _achievement_dm_embed(self, member: discord.Member, item: dict, msg: str):
        guild = member.guild if member and member.guild else None
        cheers = self._emoji(guild, "cheers", "🎉")
        arrow2 = self._emoji(guild, "arrow2", "»")
        hearts = self._emoji(guild, "hearts", "💖")
        emoji = self._resolve_emoji(guild, item.get("emoji", "🏆"))
        title = f"{cheers} 𑁉 ERFOLG FREIGESCHALTET"
        desc = (
            f"{arrow2} {msg}\n\n"
            f"┏`🏆` - Erfolg: {emoji} **{item.get('name', item.get('code', 'Erfolg'))}**\n"
            f"┗`💜` - Du bist stark unterwegs! {hearts}"
        )
        emb = discord.Embed(title=title, description=desc, color=self._embed_color(member))
        return emb

    async def announce_today(self, guild: discord.Guild, rows: list[tuple] | None = None):
        channel_id = self.settings.get_guild_int(guild.id, "birthday.channel_id")
        state = await self.db.get_birthday_announcement(guild.id)
        state_channel_id = int(state[0]) if state and state[0] is not None else 0
        state_message_id = int(state[1]) if state and state[1] is not None else 0
        state_date = str(state[2]) if state and state[2] else None
        state_payload = str(state[3]) if state and state[3] else None

        if not channel_id:
            if state_message_id:
                await self._delete_announcement_message(guild, state_channel_id, state_message_id)
            await self.db.clear_birthday_announcement(guild.id)
            await self.db.clear_birthdays_current(guild.id)
            return False

        ch = await self._resolve_channel(guild, channel_id)
        if not ch:
            return False

        now = datetime.now(self._tz(guild.id))
        today = now.date()

        rows = rows if rows is not None else await self.db.list_birthdays_global_all()
        today_entries, all_entries = self._collect_guild_birthdays(guild, rows, now)

        current_rows = [(e["user_id"], e["day"], e["month"], e["year"]) for e in today_entries]
        await self.db.replace_birthdays_current(guild.id, today.isoformat(), current_rows)

        all_entries_sorted = sorted(
            all_entries,
            key=lambda e: (int(e.get("month") or 0), int(e.get("day") or 0), int(e.get("user_id") or 0)),
        )
        total_birthdays = len(all_entries)

        payload = {
            "date": today.isoformat(),
            "today": [
                {"user_id": int(e["user_id"]), "day": int(e["day"]), "month": int(e["month"]), "year": int(e["year"])}
                for e in today_entries
            ],
            "all": [
                {"user_id": int(e["user_id"]), "day": int(e["day"]), "month": int(e["month"]), "year": int(e["year"])}
                for e in all_entries_sorted
            ],
            "total": int(total_birthdays),
        }
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)

        view = build_birthday_announcement_view(
            self.settings,
            guild,
            self._embed_color(None, guild=guild),
            today_entries,
            all_entries_sorted,
            total_birthdays,
        )
        allowed = discord.AllowedMentions(users=True, roles=False, everyone=False)

        if state_message_id and state_channel_id == int(channel_id):
            if state_payload == payload_json:
                return True
            try:
                msg = await ch.fetch_message(int(state_message_id))
            except Exception:
                msg = None
            if msg:
                try:
                    await msg.edit(view=view, allowed_mentions=allowed)
                    await self.db.set_birthday_announcement(
                        guild.id, channel_id, int(state_message_id), today.isoformat(), payload_json
                    )
                    return True
                except Exception:
                    pass

        if state_message_id and state_channel_id != int(channel_id):
            await self._delete_announcement_message(guild, state_channel_id, state_message_id)

        try:
            msg = await ch.send(view=view, allowed_mentions=allowed)
            await self.db.set_birthday_announcement(guild.id, channel_id, int(msg.id), today.isoformat(), payload_json)
        except Exception:
            pass
        return True

    async def tick_midnight(self):
        rows = None
        try:
            rows = await self.db.list_birthdays_global_all()
        except Exception:
            rows = None
        for guild in list(self.bot.guilds):
            if not self.settings.get_guild_bool(guild.id, "birthday.enabled", True):
                continue
            await self.announce_today(guild, rows=rows)

    async def auto_react(self, message: discord.Message):
        if not message.guild:
            return
        channel_id = self.settings.get_guild_int(message.guild.id, "birthday.channel_id")
        if not channel_id or message.channel.id != channel_id:
            return
        emoji = self.settings.get_guild(message.guild.id, "birthday.auto_react_emoji", "❤️")
        try:
            await message.add_reaction(str(emoji))
        except Exception:
            pass

    async def build_dashboard_payload(self, guild: discord.Guild):
        now = datetime.now(self._tz(guild.id))
        rows = await self.db.list_birthdays_global_all()
        today_entries, all_entries = self._collect_guild_birthdays(guild, rows, now)
        next_limit = int(self.settings.get_guild(guild.id, "birthday.next_limit", 6) or 6)
        next_entries = self._build_next_entries(all_entries, now.date(), next_limit)

        today_out = []
        for entry in today_entries:
            member = entry.get("member")
            uid = int(entry.get("user_id") or 0)
            today_out.append({
                "user_id": uid,
                "name": member.name if member else str(uid),
                "display_name": member.display_name if member else str(uid),
                "age": entry.get("age"),
            })

        next_out = []
        for entry in next_entries:
            member = entry.get("member")
            uid = int(entry.get("user_id") or 0)
            next_out.append({
                "user_id": uid,
                "name": member.name if member else str(uid),
                "display_name": member.display_name if member else str(uid),
                "day": int(entry.get("day") or 0),
                "month": int(entry.get("month") or 0),
                "days_until": int(entry.get("days_until") or 0),
                "turns": entry.get("turns"),
            })

        booster_rows = await self.db.list_boosters_for_guild(guild.id, limit=200, offset=0)
        booster_total = await self.db.count_boosters_for_guild(guild.id)
        boosters_out = []
        for row in booster_rows:
            uid = int(row[0])
            member = guild.get_member(uid)
            boosters_out.append({
                "user_id": uid,
                "name": member.name if member else str(uid),
                "display_name": member.display_name if member else str(uid),
                "premium_since": row[1],
                "updated_at": row[2],
            })

        return {
            "date": now.date().isoformat(),
            "timezone": str(self.settings.get_guild(guild.id, "birthday.timezone", "UTC") or "UTC"),
            "today": today_out,
            "next": next_out,
            "total_birthdays": int(len(all_entries)),
            "total_today": int(len(today_out)),
            "total_next": int(len(next_out)),
            "boosters": boosters_out,
            "total_boosters": int(booster_total),
        }

    async def show_birthday(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        member = user or interaction.user
        row = await self.db.get_birthday_global(member.id)
        if not row:
            return await interaction.response.send_message("Kein Geburtstag gespeichert.", ephemeral=True)
        day, month, year = int(row[0]), int(row[1]), int(row[2])
        month_name = calendar.month_name[month]
        await interaction.response.send_message(
            f"{member.mention} hat am **{day}. {month_name} {year}** Geburtstag.",
            ephemeral=True,
        )

    async def build_birthday_list_embed(self, guild: discord.Guild, page: int = 1, per_page: int = 10):
        rows = await self.db.list_birthdays_global_all()
        now = datetime.now(self._tz(guild.id))
        _, all_entries = self._collect_guild_birthdays(guild, rows, now)
        all_entries = sorted(
            all_entries,
            key=lambda e: (int(e.get("month") or 0), int(e.get("day") or 0), int(e.get("user_id") or 0)),
        )

        total = len(all_entries)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page
        page_entries = all_entries[offset : offset + per_page]

        lines = []
        for entry in page_entries:
            uid = int(entry["user_id"])
            day = int(entry["day"])
            month = int(entry["month"])
            year = int(entry["year"])
            member = entry.get("member")
            name = member.mention if member else str(uid)
            month_name = calendar.month_name[month]
            lines.append(f"• {name} — **{day}. {month_name} {year}**")
        text = "\n".join(lines) if lines else "Keine Geburtstage gespeichert."

        cake = self._emoji(guild, "cake", "🎂")
        emb = discord.Embed(
            title=f"{cake} 𑁉 GEBURTSTAGE",
            description=text,
            color=0xB16B91,
        )
        emb.set_footer(text=f"Seite {page}/{total_pages} • {total} Einträge")
        return emb, page, total_pages
