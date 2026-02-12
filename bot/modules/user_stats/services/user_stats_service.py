import re
import json
import math
from datetime import datetime, timezone
import discord
from bot.utils.emojis import em
from bot.utils.assets import Banners


class UserStatsService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._welcome_re = self._build_welcome_regex()

    def _build_welcome_regex(self):
        patterns = self.settings.get("user_stats.welcome_patterns", None) or [
            "welcome",
            "willkommen",
            "herzlich willkommen",
            "wb",
            "wilkommen",
        ]
        escaped = [re.escape(str(p).strip()) for p in patterns if str(p).strip()]
        if not escaped:
            escaped = [re.escape("welcome")]
        pattern = r"(" + "|".join(escaped) + r")"
        return re.compile(pattern, re.IGNORECASE)

    def _xp_per_message(self) -> int:
        return int(self.settings.get("user_stats.xp.per_message", 5) or 0)

    def _xp_per_voice_minute(self) -> int:
        return int(self.settings.get("user_stats.xp.per_voice_minute", 2) or 0)

    def _level_base(self) -> float:
        return float(self.settings.get("user_stats.level_curve.base", 100) or 100)

    def _level_exponent(self) -> float:
        return float(self.settings.get("user_stats.level_curve.exponent", 1.35) or 1.35)

    def _quick_levels(self) -> int:
        return int(self.settings.get("user_stats.level_curve.quick_levels", 15) or 15)

    def _quick_multiplier(self) -> float:
        return float(self.settings.get("user_stats.level_curve.quick_multiplier", 0.6) or 0.6)

    def _xp_for_level(self, level: int) -> int:
        if level <= 0:
            return 0
        base = self._level_base()
        exponent = self._level_exponent()
        mult = self._quick_multiplier() if level <= self._quick_levels() else 1.0
        return max(1, int(base * (level ** exponent) * mult))

    def _total_xp_for_level(self, level: int) -> int:
        if level <= 0:
            return 0
        total = 0
        for lvl in range(1, level + 1):
            total += self._xp_for_level(lvl)
        return total

    def _level_for_xp(self, xp: int, max_level: int = 200) -> int:
        xp = int(xp or 0)
        level = 0
        while level < max_level:
            need = self._total_xp_for_level(level + 1)
            if xp < need:
                break
            level += 1
        return level

    def _level_progress(self, xp: int) -> tuple[int, int, int]:
        level = self._level_for_xp(xp)
        current_total = self._total_xp_for_level(level)
        next_total = self._total_xp_for_level(level + 1)
        return level, current_total, next_total

    def _vanity_match(self, member: discord.Member) -> bool:
        needles = self.settings.get_guild(member.guild.id, "user_stats.vanity_status_contains", []) or []
        needles = [str(n).lower() for n in needles if str(n).strip()]
        return self._status_contains(member, needles)

    def _role_rules(self, guild_id: int):
        return self.settings.get_guild(int(guild_id), "user_stats.roles", []) or []

    def _level_roles(self, guild_id: int | None = None):
        raw = self.settings.get_guild(int(guild_id), "user_stats.level_roles", {}) if guild_id else self.settings.get("user_stats.level_roles", {})
        raw = raw or {}
        out = {}
        for k, v in raw.items():
            try:
                out[int(k)] = int(v)
            except Exception:
                pass
        return out

    async def ensure_roles(self, guild: discord.Guild):
        if not guild:
            return
        await self._ensure_level_roles(guild)
        await self._ensure_achievement_roles(guild)
        if bool(self.settings.get_guild(guild.id, "user_stats.auto_sort_roles", False)):
            await self._sort_managed_roles(guild)

    async def rescan_guild(self, guild: discord.Guild, birthday_service=None) -> dict:
        scanned = 0
        new_achievements = 0
        new_birthday = 0
        if not guild:
            return {"scanned": 0, "achievements_new": 0, "birthday_new": 0}
        for member in guild.members:
            if member.bot:
                continue
            scanned += 1
            await self.db.upsert_user_stats(guild.id, member.id)
            row = await self.db.get_user_stats(guild.id, member.id)
            if not row:
                continue
            stats = self._row_to_stats(row)
            await self._sync_level(member, stats, announce=False)
            await self._evaluate_rules(member, stats)
            before_rows = await self.db.list_achievements(guild.id, member.id)
            before = {r[0] for r in before_rows}
            await self._check_achievements(member, stats)
            if birthday_service:
                try:
                    added = await birthday_service.ensure_birthday_achievement(member)
                    if added:
                        new_birthday += 1
                except Exception:
                    pass
            after_rows = await self.db.list_achievements(guild.id, member.id)
            after = {r[0] for r in after_rows}
            new_achievements += len(after - before)
        return {"scanned": scanned, "achievements_new": new_achievements, "birthday_new": new_birthday}

    async def _ensure_level_roles(self, guild: discord.Guild):
        raw = self.settings.get_guild(guild.id, "user_stats.level_roles", {}) or {}
        updated = dict(raw)
        created = []
        for level_str, role_id in raw.items():
            try:
                level = int(level_str)
            except Exception:
                continue
            rid = int(role_id or 0)
            role = guild.get_role(rid) if rid else None
            if not role:
                name_fmt = str(self.settings.get_guild(guild.id, "user_stats.level_role_name_format", "⭐ • LEVEL {level}") or "")
                name = name_fmt.format(level=level)
                try:
                    role = await guild.create_role(name=name, reason="Auto role (level)")
                except Exception:
                    role = None
                if role:
                    updated[str(level)] = int(role.id)
                    created.append(role)
            else:
                updated[str(level)] = int(role.id)
        if updated != raw:
            await self.settings.set_guild_override(self.db, guild.id, "user_stats.level_roles", updated)
            await self._announce_created_roles(guild, created, "Level-Rollen")

    async def _ensure_achievement_roles(self, guild: discord.Guild):
        items = self.settings.get_guild(guild.id, "achievements.items", []) or []
        updated = []
        created = []
        for item in items:
            item = dict(item)
            rid = int(item.get("role_id", 0) or 0)
            role = guild.get_role(rid) if rid else None
            if not role:
                role_name = str(item.get("role_name", "") or "").strip()
                if not role_name:
                    prefix = str(self.settings.get_guild(guild.id, "achievements.role_name_prefix", "🏆 • ") or "🏆 • ")
                    role_name = f"{prefix}{item.get('name', item.get('code', 'Erfolg'))}"
                try:
                    role = await guild.create_role(name=role_name, reason="Auto role (achievement)")
                except Exception:
                    role = None
                if role:
                    item["role_id"] = int(role.id)
                    created.append(role)
            updated.append(item)
        if updated != items:
            await self.settings.set_guild_override(self.db, guild.id, "achievements.items", updated)
            await self._announce_created_roles(guild, created, "Erfolgsrollen")

    async def _sort_managed_roles(self, guild: discord.Guild):
        managed = []
        birthday_names = set()
        birthday_role_name = str(self.settings.get_guild(guild.id, "birthday.role_name", "🎂 • GEBURTSTAG") or "🎂 • GEBURTSTAG")
        under_name = str(self.settings.get_guild(guild.id, "birthday.under_18_role_name", "🧒 • U18") or "🧒 • U18")
        adult_name = str(self.settings.get_guild(guild.id, "birthday.adult_role_name", "🔞 • 18+") or "🔞 • 18+")
        success_name = str(self.settings.get_guild(guild.id, "birthday.success_role_name", "🏆 • GEBURTSTAG") or "🏆 • GEBURTSTAG")
        birthday_names.update([birthday_role_name, under_name, adult_name, success_name])

        for role in guild.roles:
            if role.managed or role.is_default():
                continue
            if role.name in birthday_names:
                managed.append(role)
        for item in self.settings.get_guild(guild.id, "achievements.items", []) or []:
            rid = int(item.get("role_id", 0) or 0)
            role = guild.get_role(rid) if rid else None
            if role and role not in managed:
                managed.append(role)
        for lvl, rid in self._level_roles(guild.id).items():
            role = guild.get_role(int(rid)) if rid else None
            if role and role not in managed:
                managed.append(role)

        if not managed:
            return

        bot_member = guild.me
        if not bot_member:
            return
        managed = [r for r in managed if r.position < bot_member.top_role.position]
        if not managed:
            return

        base = bot_member.top_role.position - 1
        positions = {}
        for idx, role in enumerate(managed):
            positions[role] = max(1, base - idx)
        try:
            await guild.edit_role_positions(positions=positions)
        except Exception:
            pass

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

    async def _apply_role(self, member: discord.Member, role_id: int, should_have: bool):
        role = member.guild.get_role(int(role_id)) if role_id else None
        if not role:
            return
        has_role = role in member.roles
        if should_have and not has_role:
            try:
                await member.add_roles(role, reason="User stats rule matched")
            except Exception:
                pass
        if not should_have and has_role:
            try:
                await member.remove_roles(role, reason="User stats rule no longer matched")
            except Exception:
                pass

    async def _evaluate_rules(self, member: discord.Member, stats: dict):
        days_on_server = 0
        if member.joined_at:
            days_on_server = int((datetime.now(timezone.utc) - member.joined_at).total_seconds() // 86400)
        vanity_match = self._vanity_match(member)

        for rule in self._role_rules(member.guild.id):
            role_id = int(rule.get("role_id", 0) or 0)
            if not role_id:
                continue
            rule_type = str(rule.get("type", "") or "").strip()
            threshold = int(rule.get("threshold", 0) or 0)

            ok = False
            if rule_type == "days_on_server":
                ok = days_on_server >= threshold
            elif rule_type == "messages":
                ok = int(stats.get("message_count", 0)) >= threshold
            elif rule_type == "welcomes":
                ok = int(stats.get("welcome_count", 0)) >= threshold
            elif rule_type == "voice_hours":
                ok = int(stats.get("voice_seconds", 0)) >= (threshold * 3600)
            elif rule_type == "vanity_status":
                contains = str(rule.get("contains", "") or "").lower().strip()
                if contains:
                    ok = self._status_contains(member, [contains])
                else:
                    ok = vanity_match

            await self._apply_role(member, role_id, ok)

        level_roles = self._level_roles(member.guild.id)
        user_level = int(stats.get("level", 0))
        eligible_levels = sorted([int(lvl) for lvl in level_roles.keys() if int(lvl) <= user_level])
        target_level = eligible_levels[-1] if eligible_levels else None
        target_role_id = int(level_roles.get(target_level)) if target_level is not None else 0
        for lvl, role_id in level_roles.items():
            rid = int(role_id or 0)
            if not rid:
                continue
            await self._apply_role(member, rid, rid == target_role_id)

    def _current_status_texts(self, member: discord.Member) -> list[str]:
        texts = []
        for act in member.activities:
            try:
                if act.type == discord.ActivityType.custom:
                    texts.append(str(getattr(act, "state", "") or ""))
                else:
                    texts.append(str(getattr(act, "name", "") or ""))
            except Exception:
                pass
        return texts

    def _status_contains(self, member: discord.Member, needles: list[str]) -> bool:
        needles = [str(n).lower() for n in needles if str(n).strip()]
        if not needles:
            return False
        texts = self._current_status_texts(member)
        for text in texts:
            low = str(text).lower()
            if any(n in low for n in needles):
                return True
        return False

    async def _post_levelup(self, member: discord.Member, level: int, xp: int):
        channel_id = self.settings.get_guild_int(member.guild.id, "user_stats.levelup_channel_id")
        if not channel_id:
            return
        ch = member.guild.get_channel(channel_id)
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return
        _, current_total, next_total = self._level_progress(xp)
        pct = 0
        if next_total > current_total:
            pct = int(((xp - current_total) / (next_total - current_total)) * 100)
        roles_remaining = 0
        for rule in self._role_rules(member.guild.id):
            role_id = int(rule.get("role_id", 0) or 0)
            if role_id and not member.get_role(role_id):
                roles_remaining += 1
        cheers = em(self.settings, "cheers", member.guild) or "🎉"
        arrow2 = em(self.settings, "arrow2", member.guild) or "»"
        chat = em(self.settings, "chat", member.guild) or "💬"
        wait = em(self.settings, "wait", member.guild) or "⏳"
        book = em(self.settings, "book", member.guild) or "📚"

        next_role_level = None
        for lvl in sorted(self._level_roles(member.guild.id).keys()):
            if int(lvl) > int(level):
                next_role_level = int(lvl)
                break

        next_role_text = "Alle Levelrollen erreicht."
        effort_text = "—"
        if next_role_level:
            levels_left = max(1, int(next_role_level) - int(level))
            xp_needed = max(0, self._total_xp_for_level(next_role_level) - int(xp))
            msgs_per = max(1, self._xp_per_message())
            voice_per = max(1, self._xp_per_voice_minute())
            msg_need = math.ceil(xp_needed / msgs_per) if xp_needed > 0 else 0
            voice_need = math.ceil(xp_needed / voice_per) if xp_needed > 0 else 0
            next_role_text = f"Level **{next_role_level}** (noch {levels_left} Level)"
            effort_text = f"~ {chat} **{msg_need}** Nachrichten oder {wait} **{voice_need}** Voice-Min."

        title = f"{cheers} 𑁉 LEVEL UP"
        desc = (
            f"{arrow2} {member.mention} hat Level **{level}** erreicht!\n\n"
            f"┏`⭐` - Level: **{level}**\n"
            f"┣`📈` - Fortschritt: **{pct}%** bis Level {level + 1}\n"
            f"┣`🏆` - Rollen übrig: **{roles_remaining}**\n"
            f"┣`🧭` - Nächste Rolle: {next_role_text}\n"
            f"┗`📚` - Benötigt: {effort_text}"
        )
        emb = discord.Embed(title=title, description=desc, color=self._embed_color(member))
        try:
            await ch.send(embed=emb)
        except Exception:
            pass

    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        guild_id = message.guild.id
        author = message.author
        if not isinstance(author, discord.Member):
            return
        self._welcome_re = self._build_welcome_regex()
        await self.db.increment_message(guild_id, author.id, message.channel.id, self._xp_per_message())
        if self._welcome_re.search(message.content or ""):
            await self.db.increment_welcome(guild_id, author.id)
        stats_row = await self.db.get_user_stats(guild_id, author.id)
        if not stats_row:
            return
        stats = self._row_to_stats(stats_row)
        await self._sync_level(author, stats)
        await self._evaluate_rules(author, stats)
        await self._check_achievements(author, stats)

    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if not after.guild:
            return
        row = await self.db.get_user_stats(after.guild.id, after.id)
        if not row:
            return
        stats = self._row_to_stats(row)
        await self._evaluate_rules(after, stats)
        await self._check_achievements(after, stats)

    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not after.guild:
            return
        if before.premium_since != after.premium_since:
            await self.sync_booster(after)
        row = await self.db.get_user_stats(after.guild.id, after.id)
        if not row:
            return
        stats = self._row_to_stats(row)
        await self._evaluate_rules(after, stats)
        await self._check_achievements(after, stats)

    async def on_member_remove(self, member: discord.Member):
        if not member.guild:
            return
        await self.remove_booster(member)

    async def sync_booster(self, member: discord.Member):
        if not member.guild or member.bot:
            return
        if member.premium_since:
            try:
                since = member.premium_since.isoformat()
            except Exception:
                since = None
            await self.db.upsert_booster(member.guild.id, member.id, since)
        else:
            await self.db.remove_booster(member.guild.id, member.id)

    async def remove_booster(self, member: discord.Member):
        if not member.guild or member.bot:
            return
        await self.db.remove_booster(member.guild.id, member.id)

    async def seed_boosters(self, guild: discord.Guild):
        if not guild:
            return
        updated_at = await self.db.now_iso()
        rows = []
        for member in guild.members:
            if member.bot or not member.premium_since:
                continue
            try:
                since = member.premium_since.isoformat()
            except Exception:
                since = None
            rows.append((int(guild.id), int(member.id), since, updated_at))
        await self.db.replace_boosters_for_guild(guild.id, rows)

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not member.guild or member.bot:
            return
        guild_id = member.guild.id
        if before.channel is None and after.channel is not None:
            await self.db.set_voice_session(guild_id, member.id, after.channel.id, datetime.now(timezone.utc).isoformat())
            return

        if before.channel is not None and after.channel is None:
            await self._close_voice_session(member, guild_id)
            return

        if before.channel and after.channel and before.channel.id != after.channel.id:
            await self._close_voice_session(member, guild_id)
            await self.db.set_voice_session(guild_id, member.id, after.channel.id, datetime.now(timezone.utc).isoformat())

    async def _close_voice_session(self, member: discord.Member, guild_id: int):
        row = await self.db.get_voice_session(guild_id, member.id)
        if not row:
            return
        _, joined_at = row
        try:
            joined = datetime.fromisoformat(str(joined_at))
        except Exception:
            joined = None
        if joined:
            seconds = int((datetime.now(timezone.utc) - joined).total_seconds())
            if seconds > 0:
                minutes = max(1, seconds // 60)
                xp = minutes * self._xp_per_voice_minute()
                await self.db.add_voice_seconds(guild_id, member.id, seconds, xp)
        await self.db.clear_voice_session(guild_id, member.id)
        stats_row = await self.db.get_user_stats(guild_id, member.id)
        if stats_row:
            stats = self._row_to_stats(stats_row)
            await self._sync_level(member, stats)
            await self._evaluate_rules(member, stats)
            await self._check_achievements(member, stats)

    async def _sync_level(self, member: discord.Member, stats: dict, announce: bool = True):
        xp = int(stats.get("xp", 0))
        current_level = int(stats.get("level", 0))
        new_level = self._level_for_xp(xp)
        if new_level > current_level:
            await self.db.set_user_level(member.guild.id, member.id, new_level)
            stats["level"] = new_level
            if announce:
                await self._post_levelup(member, new_level, xp)

    def _row_to_stats(self, row):
        return {
            "guild_id": int(row[0]),
            "user_id": int(row[1]),
            "message_count": int(row[2]),
            "voice_seconds": int(row[3]),
            "welcome_count": int(row[4]),
            "xp": int(row[5]),
            "level": int(row[6]),
            "last_message_at": row[7],
            "last_voice_at": row[8],
            "invite_count": int(row[9]) if len(row) > 9 else 0,
            "invite_left_count": int(row[10]) if len(row) > 10 else 0,
        }

    async def _check_achievements(self, member: discord.Member, stats: dict):
        items = self.settings.get_guild(member.guild.id, "achievements.items", []) or []
        if not items:
            return
        rows = await self.db.list_achievements(member.guild.id, member.id)
        existing = {r[0] for r in rows}
        msg_count = int(stats.get("message_count", 0))
        welcome_count = int(stats.get("welcome_count", 0))
        voice_hours = int(stats.get("voice_seconds", 0)) // 3600
        level = int(stats.get("level", 0))
        days_on_server = 0
        if member.joined_at:
            days_on_server = int((datetime.now(timezone.utc) - member.joined_at).total_seconds() // 86400)
        is_booster = bool(member.premium_since)

        for item in items:
            code = str(item.get("code", "") or "").strip()
            if not code or code in existing:
                continue
            a_type = str(item.get("type", "") or "").strip()
            threshold = int(item.get("threshold", 0) or 0)
            if a_type == "messages" and msg_count >= threshold:
                await self._unlock_achievement(member, code, item)
            elif a_type == "welcomes" and welcome_count >= threshold:
                await self._unlock_achievement(member, code, item)
            elif a_type == "voice_hours" and voice_hours >= threshold:
                await self._unlock_achievement(member, code, item)
            elif a_type == "level" and level >= threshold:
                await self._unlock_achievement(member, code, item)
            elif a_type == "days_on_server" and days_on_server >= threshold:
                await self._unlock_achievement(member, code, item)
            elif a_type == "booster" and is_booster:
                await self._unlock_achievement(member, code, item)

    async def _unlock_achievement(self, member: discord.Member, code: str, item: dict):
        await self.db.add_achievement(member.guild.id, member.id, code)
        role_id = int(item.get("role_id", 0) or 0)
        if role_id:
            role = member.guild.get_role(role_id)
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason="Achievement unlocked")
                except Exception:
                    pass
        msg = str(item.get("dm_message", "") or "").strip()
        if msg:
            try:
                emb = self._achievement_dm_embed(member, item, msg)
                await member.send(embed=emb)
            except Exception:
                pass

    def _achievement_dm_embed(self, member: discord.Member, item: dict, msg: str):
        guild = member.guild if member and member.guild else None
        cheers = em(self.settings, "cheers", guild) or "🎉"
        arrow2 = em(self.settings, "arrow2", guild) or "»"
        hearts = em(self.settings, "hearts", guild) or "💖"
        emoji = self._resolve_emoji(guild, item.get("emoji", "🏆"))
        title = f"{cheers} 𑁉 ERFOLG FREIGESCHALTET"
        desc = (
            f"{arrow2} {msg}\n\n"
            f"┏`🏆` - Erfolg: {emoji} **{item.get('name', item.get('code', 'Erfolg'))}**\n"
            f"┗`💜` - Du bist stark unterwegs! {hearts}"
        )
        emb = discord.Embed(title=title, description=desc, color=member.color or 0xB16B91)
        emb.set_image(url=Banners.ACHIEVEMENT_COMPLETE)
        return emb

    async def build_me_embed(self, member: discord.Member):
        await self.db.upsert_user_stats(member.guild.id, member.id)
        row = await self.db.get_user_stats(member.guild.id, member.id)
        stats = self._row_to_stats(row) if row else {}
        total_users = await self.db.count_users_in_stats(member.guild.id)
        total_users = max(1, total_users)
        top_msg = await self.db.count_users_with_messages_at_least(member.guild.id, int(stats.get("message_count", 0)))
        top_voice = await self.db.count_users_with_voice_at_least(member.guild.id, int(stats.get("voice_seconds", 0)))
        msg_top_pct = int((top_msg / total_users) * 100)
        voice_top_pct = int((top_voice / total_users) * 100)

        channel_rows = await self.db.list_user_channel_stats(member.guild.id, member.id, limit=1)
        top_channel = "—"
        if channel_rows:
            ch_id = int(channel_rows[0][0])
            ch = member.guild.get_channel(ch_id)
            top_channel = ch.mention if ch else f"`{ch_id}`"

        tickets = await self.db.get_ticket_count(member.id)
        voice_hours = int(stats.get("voice_seconds", 0)) // 3600
        voice_days = round(int(stats.get("voice_seconds", 0)) / 86400, 2)
        msg_count = int(stats.get("message_count", 0))
        welcome_count = int(stats.get("welcome_count", 0))
        invite_count = int(stats.get("invite_count", 0))
        invite_left_count = int(stats.get("invite_left_count", 0))
        invite_net = max(0, invite_count - invite_left_count)
        level = int(stats.get("level", 0))
        xp = int(stats.get("xp", 0))
        _, current_total, next_total = self._level_progress(xp)
        pct = 0
        if next_total > current_total:
            pct = int(((xp - current_total) / (next_total - current_total)) * 100)

        ach_rows = await self.db.list_achievements(member.guild.id, member.id)
        achieved = len(ach_rows)
        total_achievements = len(self.settings.get_guild(member.guild.id, "achievements.items", []) or [])

        role_lines = []
        total_members = max(1, member.guild.member_count or 1)
        for rule in self._role_rules(member.guild.id):
            role_id = int(rule.get("role_id", 0) or 0)
            role = member.guild.get_role(role_id) if role_id else None
            if role and role in member.roles:
                role_pct = int((len(role.members) / total_members) * 100)
                role_lines.append(f"• {role.mention} ({role_pct}%)")
        for lvl, role_id in sorted(self._level_roles(member.guild.id).items()):
            role = member.guild.get_role(role_id)
            if role and role in member.roles:
                role_pct = int((len(role.members) / total_members) * 100)
                role_lines.append(f"• {role.mention} ({role_pct}%)")

        role_text = "\n".join(role_lines) if role_lines else "—"

        embed = discord.Embed(
            title=f"📊 𑁉 USER-STATS • {member.display_name}",
            color=self._embed_color(member),
            description=(
                f"┏`💬` - Nachrichten: **{msg_count}** (Top {msg_top_pct}%)\n"
                f"┣`🎙️` - Voice: **{voice_hours}h** ({voice_days} Tage) (Top {voice_top_pct}%)\n"
                f"┣`👋` - Welcome: **{welcome_count}**\n"
                f"┣`📨` - Invites: **{invite_count}** (Left {invite_left_count} • Net {invite_net})\n"
                f"┣`🎫` - Tickets: **{tickets}**\n"
                f"┣`📌` - Aktivster Channel: {top_channel}\n"
                f"┣`⭐` - Level: **{level}** (XP {xp}/{next_total} • {pct}%)\n"
                f"┣`🏆` - Erfolge: **{achieved}/{total_achievements}**\n"
                f"┗`🏷️` - Rollen: \n{role_text}"
            ),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_image(url=Banners.ACHIEVEMENT)
        return embed

    async def build_achievements_embed(self, member: discord.Member, page: int = 1, per_page: int = 8):
        items = self.settings.get_guild(member.guild.id, "achievements.items", []) or []
        total = len(items)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = start + per_page
        items_page = items[start:end]

        await self.db.upsert_user_stats(member.guild.id, member.id)
        row = await self.db.get_user_stats(member.guild.id, member.id)
        stats = self._row_to_stats(row) if row else {}
        rows = await self.db.list_achievements(member.guild.id, member.id)
        unlocked = {r[0] for r in rows}

        days_on_server = 0
        if member.joined_at:
            days_on_server = int((datetime.now(timezone.utc) - member.joined_at).total_seconds() // 86400)

        msg_count = int(stats.get("message_count", 0))
        welcome_count = int(stats.get("welcome_count", 0))
        voice_hours = int(stats.get("voice_seconds", 0)) // 3600
        level = int(stats.get("level", 0))
        is_booster = bool(member.premium_since)
        has_birthday = False
        try:
            bday = await self.db.get_birthday(member.guild.id, member.id)
            has_birthday = bool(bday)
        except Exception:
            has_birthday = False

        lines = []
        total_members = max(1, member.guild.member_count or 1)
        for item in items_page:
            code = str(item.get("code", "") or "")
            name = str(item.get("name", code) or code)
            desc = str(item.get("description", "") or "").strip()
            emoji = self._resolve_emoji(member.guild, item.get("emoji", "🏆"))
            a_type = str(item.get("type", "") or "")
            threshold = int(item.get("threshold", 1) or 1)
            got = code in unlocked
            current = 0
            if a_type == "messages":
                current = msg_count
            elif a_type == "welcomes":
                current = welcome_count
            elif a_type == "voice_hours":
                current = voice_hours
            elif a_type == "level":
                current = level
            elif a_type == "days_on_server":
                current = days_on_server
            elif a_type == "booster":
                current = 1 if is_booster else 0
            elif a_type == "birthday_set":
                current = 1 if has_birthday else 0

            if threshold <= 0:
                threshold = 1
            progress_pct = min(100, int((current / threshold) * 100)) if threshold else 0
            count_have = await self.db.count_achievement(member.guild.id, code)
            percent_have = int((count_have / total_members) * 100)
            status = (em(self.settings, "green", member.guild) or "✅") if got else (em(self.settings, "red", member.guild) or "🔒")
            rarity = "Legendär" if percent_have <= 5 else "Selten" if percent_have <= 15 else "Ungewöhnlich" if percent_have <= 35 else "Häufig"
            bar_full = "█" * max(1, int(progress_pct / 10))
            bar_empty = "░" * (10 - len(bar_full))
            bar = f"`{bar_full}{bar_empty}` {progress_pct}%"
            req_label = f"{current}/{threshold}" if not got else f"{threshold}/{threshold}"
            if got:
                line = (
                    f"{status} {emoji} **{name}**\n"
                    f"  ┣ {desc if desc else '—'}\n"
                    f"  ┣ Fortschritt: {bar}\n"
                    f"  ┗ Besitzer: **{count_have}/{total_members}** ({percent_have}%) • {rarity}"
                )
            else:
                line = (
                    f"{status} {emoji} **{name}**\n"
                    f"  ┣ {desc if desc else '—'}\n"
                    f"  ┣ Fortschritt: {bar} ({req_label})\n"
                    f"  ┗ Besitzer: **{count_have}/{total_members}** ({percent_have}%) • {rarity}"
                )
            lines.append(line)

        text = "\n\n".join(lines) if lines else "Keine Erfolge konfiguriert."
        emb = discord.Embed(
            title=f"🏆 𑁉 ERFOLGE • {member.display_name}",
            description=(
                "Hier siehst du deine freigeschalteten Erfolge, deinen Fortschritt "
                "und wie viele andere sie bereits haben.\n\n" + text
            ),
            color=self._embed_color(member),
        )
        emb.set_image(url=Banners.ACHIEVEMENT)
        emb.set_footer(text=f"Seite {page}/{total_pages} • {len(unlocked)}/{total} freigeschaltet")
        return emb, page, total_pages

    def _resolve_emoji(self, guild: discord.Guild | None, token: str | None) -> str:
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

    async def seed_voice_sessions(self, guild: discord.Guild):
        for member in guild.members:
            if member.bot:
                continue
            if not member.voice or not member.voice.channel:
                continue
            existing = await self.db.get_voice_session(guild.id, member.id)
            if not existing:
                await self.db.set_voice_session(
                    guild.id,
                    member.id,
                    member.voice.channel.id,
                    datetime.now(timezone.utc).isoformat(),
                )
