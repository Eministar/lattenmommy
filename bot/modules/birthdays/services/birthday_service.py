import calendar
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import discord


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

    def _embed_color(self, member: discord.Member | None) -> int:
        try:
            if member and int(member.color.value) != 0:
                return int(member.color.value)
        except Exception:
            pass
        v = str(self.settings.get_guild(member.guild.id, "design.accent_color", "#B16B91") or "").replace("#", "").strip()
        try:
            return int(v, 16)
        except Exception:
            return 0xB16B91

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

    async def remove_birthday(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        await self.db.remove_birthday_global(interaction.user.id)
        await interaction.response.send_message("Geburtstag entfernt.", ephemeral=True)

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

    async def announce_today(self, guild: discord.Guild):
        channel_id = self.settings.get_guild_int(guild.id, "birthday.channel_id")
        if not channel_id:
            return False
        ch = guild.get_channel(channel_id)
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return False

        now = datetime.now(self._tz(guild.id))
        rows = await self.db.list_birthdays_for_day_global(now.day, now.month)
        if not rows:
            return True

        cake = self._emoji(guild, "cake", "🎂")
        party = self._emoji(guild, "party", "🎉")
        heart = self._emoji(guild, "hearts", "💖")

        lines = []
        for row in rows:
            uid = int(row[0])
            year = int(row[3])
            age = now.year - year
            lines.append(f"{party} <@{uid}> wird **{age}**!")

        text = f"{cake} **Happy Birthday!** {heart}\n\n" + "\n".join(lines)
        try:
            await ch.send(text)
        except Exception:
            pass
        return True

    async def tick_midnight(self):
        for guild in list(self.bot.guilds):
            if not self.settings.get_guild_bool(guild.id, "birthday.enabled", True):
                continue
            tz = self._tz(guild.id)
            today = datetime.now(tz).date().isoformat()
            last = self.settings.get_guild(guild.id, "birthday.last_announce_date", None)
            if last == today:
                continue
            ok = await self.announce_today(guild)
            if ok:
                await self.settings.set_guild_override(self.db, guild.id, "birthday.last_announce_date", today)

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
        total = await self.db.count_birthdays_global()
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page
        rows = await self.db.list_birthdays_global(limit=per_page, offset=offset)

        lines = []
        for row in rows:
            uid, day, month, year = int(row[0]), int(row[1]), int(row[2]), int(row[3])
            member = guild.get_member(uid)
            name = member.mention if member else f"<@{uid}>"
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
