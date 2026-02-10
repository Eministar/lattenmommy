from __future__ import annotations

from datetime import datetime, timezone
import discord
from bot.utils.assets import Banners


class InviteService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._cache: dict[int, dict[str, tuple[int, int]]] = {}

    def _enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(guild_id, "invites.enabled", True))

    def _log_channel_id(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(guild_id, "invites.log_channel_id", 0))

    async def _get_channel(self, guild: discord.Guild, channel_id: int) -> discord.TextChannel | None:
        if not channel_id:
            return None
        ch = guild.get_channel(int(channel_id))
        if not ch:
            try:
                ch = await guild.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        return ch if isinstance(ch, discord.TextChannel) else None

    def _color(self, guild: discord.Guild | None) -> int:
        gid = guild.id if guild else 0
        v = str(self.settings.get_guild(gid, "design.accent_color", "#B16B91") or "").replace("#", "").strip()
        try:
            return int(v, 16)
        except Exception:
            return 0xB16B91

    async def _send_join_log(
        self,
        guild: discord.Guild,
        member: discord.Member,
        inviter_id: int,
        invite_code: str,
    ):
        ch = await self._get_channel(guild, self._log_channel_id(guild.id))
        if not ch:
            return
        arrow2 = "»"
        info = "ℹ️"
        try:
            from bot.utils.emojis import em
            arrow2 = em(self.settings, "arrow2", guild) or arrow2
            info = em(self.settings, "info", guild) or info
        except Exception:
            pass

        inviter = guild.get_member(int(inviter_id)) if inviter_id else None
        inviter_line = inviter.mention if inviter else ("Vanity" if invite_code == "vanity" else "Unbekannt")
        code_line = invite_code if invite_code else "—"
        now = datetime.now(timezone.utc)
        desc = (
            f"{arrow2} Neues Mitglied beigetreten.\n\n"
            f"┏`👤` - Member: {member.mention} ({member.id})\n"
            f"┣`🤝` - Eingeladen von: {inviter_line}\n"
            f"┣`🔗` - Invite: `{code_line}`\n"
            f"┗`⏰` - Zeitpunkt: {discord.utils.format_dt(now, style='f')}"
        )
        header = f"**{info} 𑁉 INVITE – JOIN**"
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=self._color(guild))
        try:
            gallery = discord.ui.MediaGallery()
            gallery.add_item(media=Banners.INVITE)
            container.add_item(gallery)
            container.add_item(discord.ui.Separator())
        except Exception:
            pass
        container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
        view.add_item(container)
        try:
            await ch.send(view=view)
        except Exception:
            pass

    async def _fetch_invites(self, guild: discord.Guild) -> dict[str, tuple[int, int]]:
        invites = {}
        try:
            rows = await guild.invites()
        except Exception:
            return invites
        for inv in rows:
            try:
                inviter_id = int(inv.inviter.id) if inv.inviter else 0
                invites[str(inv.code)] = (int(inv.uses or 0), inviter_id)
            except Exception:
                continue
        return invites

    async def seed_cache(self, guild: discord.Guild):
        if not guild or not self._enabled(guild.id):
            return
        self._cache[guild.id] = await self._fetch_invites(guild)

    async def refresh_cache(self, guild: discord.Guild):
        if not guild or not self._enabled(guild.id):
            return {}
        current = await self._fetch_invites(guild)
        self._cache[guild.id] = current
        return current

    async def on_invite_create(self, invite: discord.Invite):
        guild = invite.guild
        if not guild or not self._enabled(guild.id):
            return
        cache = self._cache.setdefault(guild.id, {})
        try:
            inviter_id = int(invite.inviter.id) if invite.inviter else 0
            cache[str(invite.code)] = (int(invite.uses or 0), inviter_id)
        except Exception:
            pass

    async def on_invite_delete(self, invite: discord.Invite):
        guild = invite.guild
        if not guild or not self._enabled(guild.id):
            return
        cache = self._cache.setdefault(guild.id, {})
        try:
            cache.pop(str(invite.code), None)
        except Exception:
            pass

    async def on_member_join(self, member: discord.Member):
        if not member.guild or member.bot or not self._enabled(member.guild.id):
            return
        guild = member.guild
        before = dict(self._cache.get(guild.id, {}))
        current = await self._fetch_invites(guild)
        self._cache[guild.id] = current

        used_code = None
        inviter_id = 0
        best_delta = 0
        for code, (uses, inviter) in current.items():
            old_uses = before.get(code, (0, 0))[0]
            delta = int(uses) - int(old_uses)
            if delta > best_delta:
                best_delta = delta
                used_code = code
                inviter_id = int(inviter or 0)

        if used_code and inviter_id:
            try:
                await self.db.increment_invite(guild.id, inviter_id)
            except Exception:
                pass
            try:
                await self.db.add_invite_join(guild.id, member.id, inviter_id, used_code)
            except Exception:
                pass
            try:
                await self._send_join_log(guild, member, inviter_id, used_code)
            except Exception:
                pass
            return

        code = "vanity" if guild.vanity_url_code else "unknown"
        try:
            await self.db.add_invite_join(guild.id, member.id, 0, code)
        except Exception:
            pass
        try:
            await self._send_join_log(guild, member, 0, code)
        except Exception:
            pass

    async def on_member_remove(self, member: discord.Member):
        if not member.guild or member.bot or not self._enabled(member.guild.id):
            return
        row = await self.db.get_invite_join(member.guild.id, member.id)
        if not row:
            return
        inviter_id = int(row[2])
        left_at = row[5]
        if left_at:
            return
        await self.db.mark_invite_left(member.guild.id, member.id)
        if inviter_id:
            try:
                await self.db.increment_invite_left(member.guild.id, inviter_id)
            except Exception:
                pass
