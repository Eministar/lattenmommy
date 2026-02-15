from __future__ import annotations

import json
import re

import discord

_CUSTOM_EMOJI_RE = re.compile(r"^<a?:[A-Za-z0-9_]{1,32}:(\d{15,21})>$")
_CUSTOM_EMOJI_SHORT_RE = re.compile(r"^:([A-Za-z0-9_]{2,32}):$")


class CustomRoleService:
    def __init__(self, bot, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    @staticmethod
    def parse_color(value: str | None) -> discord.Colour:
        raw = str(value or "").strip().replace("#", "")
        if not raw:
            return discord.Colour(0xB16B91)
        try:
            return discord.Colour(int(raw, 16))
        except Exception:
            return discord.Colour(0xB16B91)

    @staticmethod
    def parse_emojis(raw: str | None) -> list[str]:
        text = str(raw or "").replace(",", " ").strip()
        if not text:
            return []
        return [p.strip() for p in text.split() if p.strip()]

    def _cfg(self, guild_id: int, key: str, default):
        new_key = f"custom_roles.{key}"
        legacy_key = f"roles.custom_role.{key}"
        value = self.settings.get_guild(int(guild_id), new_key, None)
        if value is not None:
            return value
        return self.settings.get_guild(int(guild_id), legacy_key, default)

    def enabled(self, guild_id: int) -> bool:
        return bool(self._cfg(int(guild_id), "enabled", True))

    def default_reactions(self, guild_id: int) -> list[str]:
        raw = self._cfg(int(guild_id), "default_reactions", ["🔥", "✨", "💫"]) or []
        out: list[str] = []
        for item in raw:
            s = str(item or "").strip()
            if s:
                out.append(s)
        return out or ["🔥", "✨", "💫"]

    async def member_level(self, member: discord.Member) -> int:
        row = await self.db.get_user_stats(member.guild.id, member.id)
        if not row:
            return 0
        try:
            return int(row[6] or 0)
        except Exception:
            return 0

    async def perks(self, member: discord.Member) -> dict:
        gid = int(member.guild.id)
        level = await self.member_level(member)
        is_booster = bool(member.premium_since)

        rewards = self._cfg(gid, "rewards", None) or [
            {"min_level": 0, "max_emojis": 3},
            {"min_level": 10, "max_emojis": 5},
            {"min_level": 25, "max_emojis": 7},
        ]
        tiers: list[tuple[int, int]] = []
        for r in rewards:
            if not isinstance(r, dict):
                continue
            try:
                tiers.append((int(r.get("min_level", 0) or 0), int(r.get("max_emojis", 3) or 3)))
            except Exception:
                continue
        if not tiers:
            tiers = [(0, 3), (10, 5)]
        tiers.sort(key=lambda t: t[0])

        max_emojis = tiers[0][1]
        for min_level, amount in tiers:
            if level >= min_level:
                max_emojis = amount

        booster_unlock_level = int(self._cfg(gid, "booster_unlock_level", 10) or 10)
        booster_max = int(self._cfg(gid, "booster_max_emojis", 5) or 5)
        if is_booster and max_emojis < booster_max:
            max_emojis = booster_max

        icon_unlock_level = int(self._cfg(gid, "icon_unlock_level", 10) or 10)
        booster_unlocks_icon = bool(self._cfg(gid, "booster_unlocks_icon", True))
        can_icon = bool(level >= icon_unlock_level or (is_booster and booster_unlocks_icon))

        emoji_upload_unlock_level = int(self._cfg(gid, "emoji_upload_unlock_level", 10) or 10)
        allow_user_emoji_upload = bool(self._cfg(gid, "allow_user_emoji_upload", True))
        can_upload_emoji = bool(
            allow_user_emoji_upload and (level >= emoji_upload_unlock_level or is_booster)
        )

        return {
            "level": int(level),
            "is_booster": bool(is_booster),
            "max_emojis": max(1, min(20, int(max_emojis))),
            "can_icon": can_icon,
            "booster_unlock_level": int(booster_unlock_level),
            "can_upload_emoji": bool(can_upload_emoji),
        }

    @staticmethod
    def _emoji_id(token: str) -> int | None:
        m = _CUSTOM_EMOJI_RE.match(str(token or "").strip())
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def sanitize_emojis(self, guild: discord.Guild, emojis: list[str], max_emojis: int) -> tuple[list[str], list[str]]:
        valid: list[str] = []
        invalid: list[str] = []
        guild_emoji_by_name = {str(e.name): e for e in (guild.emojis or [])}
        for token in emojis:
            t = str(token or "").strip()
            if not t:
                continue
            eid = self._emoji_id(t)
            if eid is not None:
                e = guild.get_emoji(int(eid))
                if e is None:
                    invalid.append(t)
                    continue
                valid.append(str(e))
                continue
            m_short = _CUSTOM_EMOJI_SHORT_RE.match(t)
            if m_short:
                by_name = guild_emoji_by_name.get(str(m_short.group(1)))
                if by_name is None:
                    invalid.append(t)
                    continue
                valid.append(str(by_name))
                continue
            valid.append(t)
        out = valid[: max(1, min(20, int(max_emojis)))]
        return out, invalid

    async def load_icon_bytes(self, icon: discord.Attachment | None) -> tuple[bytes | None, str | None]:
        if not icon:
            return None, None
        content_type = str(getattr(icon, "content_type", "") or "").lower()
        if content_type and not content_type.startswith("image/"):
            return None, "Icon muss ein Bild sein."
        try:
            data = await icon.read()
        except Exception:
            return None, "Icon konnte nicht gelesen werden."
        if not data:
            return None, "Icon ist leer."
        if len(data) > 256 * 1024:
            return None, "Icon ist zu groß (max. 256KB)."
        return data, None

    async def upsert_member_role(
        self,
        member: discord.Member,
        name: str,
        color: discord.Colour,
        emojis: list[str],
        max_emojis: int,
        icon_data: bytes | None,
        can_icon: bool,
    ) -> tuple[bool, str]:
        guild = member.guild
        bot_member = guild.me
        if not bot_member or not guild.me.guild_permissions.manage_roles:
            return False, "Bot braucht `Manage Roles`."

        row = await self.db.get_custom_role(guild.id, member.id)
        role = None
        if row:
            try:
                role = guild.get_role(int(row[2] or 0))
            except Exception:
                role = None

        if role and role.position >= bot_member.top_role.position:
            return False, "Deine Custom-Rolle ist über meiner Bot-Rolle."

        display_icon = icon_data if (icon_data and can_icon) else None
        if icon_data and not can_icon:
            return False, "Role-Icon ist erst ab Level 10 oder als Booster verfügbar."
        if display_icon and "ROLE_ICONS" not in (guild.features or []):
            return False, "Dieser Server unterstützt keine Rollen-Icons."

        try:
            if role is None:
                role = await guild.create_role(
                    name=name[:100],
                    colour=color,
                    mentionable=True,
                    display_icon=display_icon,
                    reason=f"Custom role for {member.id}",
                )
            else:
                await role.edit(
                    name=name[:100],
                    colour=color,
                    mentionable=True,
                    display_icon=display_icon if icon_data else role.display_icon,
                    reason=f"Custom role update for {member.id}",
                )
        except Exception as e:
            return False, f"Rolle konnte nicht erstellt/aktualisiert werden: `{type(e).__name__}`"

        if role not in member.roles:
            try:
                await member.add_roles(role, reason="Custom role assign")
            except Exception:
                pass

        cleaned, invalid = self.sanitize_emojis(guild, emojis, max_emojis)
        if not cleaned:
            return False, "Keine gültigen Emojis. Erlaubt sind Unicode oder Server-Custom-Emojis."
        try:
            await self.db.upsert_custom_role(
                guild.id,
                member.id,
                int(role.id),
                str(role.name),
                json.dumps(cleaned, ensure_ascii=False),
                int(max_emojis),
            )
        except Exception as e:
            return False, f"Speichern fehlgeschlagen: `{type(e).__name__}`"
        if invalid:
            return True, f"Custom-Rolle aktiv: {role.mention} | Emojis: **{len(cleaned)}/{max_emojis}** (ignoriert: {len(invalid)})"
        return True, f"Custom-Rolle aktiv: {role.mention} | Emojis: **{len(cleaned)}/{max_emojis}**"

    async def set_member_emojis(self, member: discord.Member, emojis: list[str], max_emojis: int) -> tuple[bool, str]:
        row = await self.db.get_custom_role(member.guild.id, member.id)
        if not row:
            return False, "Du hast noch keine Custom-Rolle. Nutze zuerst `/custom-role create`."
        if not emojis:
            return False, "Bitte mindestens ein Emoji angeben."
        try:
            role_id = int(row[2] or 0)
            role_name = str(row[3] or "Custom Role")
        except Exception:
            return False, "Dein gespeicherter Custom-Role-Datensatz ist ungültig."
        cleaned, invalid = self.sanitize_emojis(member.guild, emojis, max_emojis)
        if not cleaned:
            return False, "Keine gültigen Emojis. Erlaubt sind Unicode oder Server-Custom-Emojis."
        try:
            await self.db.upsert_custom_role(
                member.guild.id,
                member.id,
                role_id,
                role_name,
                json.dumps(cleaned, ensure_ascii=False),
                int(max_emojis),
            )
        except Exception as e:
            return False, f"Speichern fehlgeschlagen: `{type(e).__name__}`"
        if invalid:
            return True, f"Reaktions-Emojis gesetzt: **{len(cleaned)}/{max_emojis}** (ignoriert: {len(invalid)})"
        return True, f"Reaktions-Emojis gesetzt: **{len(cleaned)}/{max_emojis}**"

    async def read_reactions(self, guild_id: int, user_id: int) -> tuple[list[str], int]:
        row = await self.db.get_custom_role(int(guild_id), int(user_id))
        if not row:
            return [], 0
        try:
            emojis = json.loads(str(row[4] or "[]"))
        except Exception:
            emojis = []
        if not isinstance(emojis, list):
            emojis = []
        out = [str(e).strip() for e in emojis if str(e).strip()]
        try:
            max_emojis = int(row[5] or 3)
        except Exception:
            max_emojis = 3
        max_emojis = max(1, min(20, max_emojis))
        return out[:max_emojis], max_emojis

    async def remove_member_role(self, member: discord.Member) -> tuple[bool, str]:
        row = await self.db.get_custom_role(member.guild.id, member.id)
        if not row:
            return False, "Du hast keine Custom-Rolle gespeichert."

        role = None
        try:
            role = member.guild.get_role(int(row[2] or 0))
        except Exception:
            role = None
        if role:
            try:
                await role.delete(reason=f"Custom role remove by {member.id}")
            except Exception:
                pass
        await self.db.delete_custom_role(member.guild.id, member.id)
        return True, "Deine Custom-Rolle wurde entfernt."

    async def upload_guild_emoji(self, guild: discord.Guild, actor: discord.Member, name: str, image: bytes) -> tuple[bool, str, str | None]:
        if not guild.me or not guild.me.guild_permissions.manage_emojis_and_stickers:
            return False, "Bot braucht `Manage Emojis and Stickers`.", None
        safe_name = re.sub(r"[^A-Za-z0-9_]", "", str(name or "").strip())[:32]
        if len(safe_name) < 2:
            return False, "Emoji-Name ist ungültig (mind. 2 Zeichen, nur A-Z 0-9 _).", None
        try:
            emoji = await guild.create_custom_emoji(
                name=safe_name,
                image=image,
                reason=f"Custom role emoji upload by {actor.id}",
            )
        except Exception as e:
            return False, f"Emoji-Upload fehlgeschlagen: `{type(e).__name__}`", None
        return True, f"Emoji hochgeladen: {emoji}", str(emoji)
