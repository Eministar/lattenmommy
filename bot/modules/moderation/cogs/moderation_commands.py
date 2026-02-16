from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.perms import is_staff
from bot.modules.moderation.services.mod_service import ModerationService
from bot.modules.moderation.formatting.moderation_embeds import build_channel_access_embed


async def _ephemeral(interaction: discord.Interaction, text: str):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(text, ephemeral=True)
        else:
            await interaction.followup.send(text, ephemeral=True)
    except (discord.InteractionResponded, discord.NotFound, discord.HTTPException):
        try:
            await interaction.followup.send(text, ephemeral=True)
        except Exception:
            pass


async def _defer(interaction: discord.Interaction):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
    except (discord.InteractionResponded, discord.NotFound, discord.HTTPException):
        pass


class ModerationCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = ModerationService(bot, bot.settings, bot.db, getattr(bot, "forum_logs", None))

    def _need_guild(self, interaction: discord.Interaction):
        return interaction.guild and isinstance(interaction.user, discord.Member)

    def _need_ctx(self, ctx: commands.Context) -> bool:
        return bool(ctx.guild and isinstance(ctx.author, discord.Member))

    async def _ctx_reply(self, ctx: commands.Context, text: str):
        try:
            await ctx.reply(text, mention_author=False)
        except Exception:
            try:
                await ctx.send(text)
            except Exception:
                pass

    def _cfg_role_ids(self, guild_id: int, action: str) -> set[int]:
        raw = self.bot.settings.get_guild(guild_id, f"moderation.permissions.{action}_role_ids", []) or []
        if isinstance(raw, (int, str)):
            raw = [raw]
        out: set[int] = set()
        for x in raw:
            try:
                rid = int(x)
            except Exception:
                continue
            if rid > 0:
                out.add(rid)
        return out

    def _has_action_access(self, member: discord.Member, action: str) -> bool:
        if member.guild_permissions.administrator:
            return True
        configured = self._cfg_role_ids(member.guild.id, action)
        if configured:
            return any(r.id in configured for r in member.roles)
        return is_staff(self.bot.settings, member)

    def _parse_lock_mode(self, raw: str | None) -> str:
        x = str(raw or "all").strip().lower()
        if x in {"s", "send", "write", "schreiben", "w"}:
            return "send"
        if x in {"v", "view", "see", "sehen", "read", "r"}:
            return "view"
        return "all"

    async def _apply_channel_lock(
        self,
        guild: discord.Guild,
        actor: discord.Member,
        channel: discord.TextChannel,
        mode: str,
        locked: bool,
    ) -> tuple[bool, str | None]:
        overwrite = channel.overwrites_for(guild.default_role)
        if mode in {"send", "all"}:
            overwrite.send_messages = False if locked else None
        if mode in {"view", "all"}:
            overwrite.view_channel = False if locked else None
        try:
            await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=f"moderation:{'lock' if locked else 'unlock'}:{mode}")
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        try:
            if self.service.forum_logs:
                emb = build_channel_access_embed(self.bot.settings, guild, actor, channel, mode, locked)
                await self.service.forum_logs.emit(guild, "punishments", emb)
        except Exception:
            pass
        return True, None

    @app_commands.command(name="timeout", description="⏳ 𑁉 Timeout setzen")
    @app_commands.describe(user="User", minutes="Minuten (leer = Auto)", reason="Grund")
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, minutes: int | None = None, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.moderate_members:
            return await _ephemeral(interaction, "Dir fehlt `Moderate Members`.")

        ok, err, used_minutes, strikes, case_id = await self.service.timeout(interaction.guild, interaction.user, user, minutes, reason)
        if not ok:
            return await _ephemeral(interaction, f"Timeout ging nicht: {err}")

        return await _ephemeral(interaction, f"Timeout gesetzt: **{used_minutes}min** (Strike **{strikes}**). Case: `{case_id}`")

    @app_commands.command(name="warn", description="⚠️ 𑁉 Warnung vergeben")
    @app_commands.describe(user="User", reason="Grund")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.moderate_members:
            return await _ephemeral(interaction, "Dir fehlt `Moderate Members`.")

        strikes, case_id = await self.service.warn(interaction.guild, interaction.user, user, reason)
        return await _ephemeral(interaction, f"Warnung vergeben. Strikes jetzt: **{strikes}**. Case: `{case_id}`")

    @app_commands.command(name="kick", description="👢 𑁉 User kicken")
    @app_commands.describe(user="User", reason="Grund")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.kick_members:
            return await _ephemeral(interaction, "Dir fehlt `Kick Members`.")

        ok, err, case_id = await self.service.kick(interaction.guild, interaction.user, user, reason)
        if not ok:
            return await _ephemeral(interaction, f"Kick ging nicht: {err}")
        return await _ephemeral(interaction, f"{user.mention} wurde gekickt. Case: `{case_id}`")

    @app_commands.command(name="ban", description="🔨 𑁉 User bannen")
    @app_commands.describe(user="User", delete_days="Lösche Nachrichten der letzten X Tage (0-7)", reason="Grund")
    async def ban(self, interaction: discord.Interaction, user: discord.User, delete_days: int = 0, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.ban_members:
            return await _ephemeral(interaction, "Dir fehlt `Ban Members`.")

        ok, err, dd, case_id = await self.service.ban(interaction.guild, interaction.user, user, delete_days, reason)
        if not ok:
            return await _ephemeral(interaction, f"Ban ging nicht: {err}")
        return await _ephemeral(interaction, f"<@{user.id}> wurde gebannt. (delete_days={dd}) Case: `{case_id}`")

    @app_commands.command(name="purge", description="🧹 𑁉 Nachrichten löschen")
    @app_commands.describe(amount="Wie viele (1-100)", user="Optional: nur dieser User", reason="Optional: interner Grund")
    async def purge(self, interaction: discord.Interaction, amount: int, user: discord.Member | None = None, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not self._has_action_access(interaction.user, "purge"):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.manage_messages:
            return await _ephemeral(interaction, "Dir fehlt `Manage Messages`.")

        if not isinstance(interaction.channel, discord.TextChannel):
            return await _ephemeral(interaction, "Nur in normalen Text-Channels.")

        await _defer(interaction)
        deleted, err, case_id = await self.service.purge(interaction.guild, interaction.user, interaction.channel, amount, user)
        if err:
            return await _ephemeral(interaction, f"Purge ging nicht: {err}")
        return await _ephemeral(interaction, f"Gelöscht: **{deleted}** Nachricht(en). Case: `{case_id}`")

    @app_commands.command(name="untimeout", description="✅ 𑁉 Timeout entfernen")
    @app_commands.describe(user="User", reason="Grund")
    async def untimeout(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.moderate_members:
            return await _ephemeral(interaction, "Dir fehlt `Moderate Members`.")
        try:
            await user.timeout(None, reason=reason or None)
        except Exception as e:
            return await _ephemeral(interaction, f"Timeout entfernen ging nicht: {type(e).__name__}: {e}")
        await _ephemeral(interaction, f"Timeout entfernt für {user.mention}.")

    @app_commands.command(name="unban", description="♻️ 𑁉 User entbannen")
    @app_commands.describe(user_id="User-ID", reason="Grund")
    async def unban(self, interaction: discord.Interaction, user_id: int, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.ban_members:
            return await _ephemeral(interaction, "Dir fehlt `Ban Members`.")
        try:
            await interaction.guild.unban(discord.Object(id=int(user_id)), reason=reason or None)
        except Exception as e:
            return await _ephemeral(interaction, f"Unban ging nicht: {type(e).__name__}: {e}")
        await _ephemeral(interaction, f"<@{user_id}> wurde entbannt.")

    @app_commands.command(name="slowmode", description="🐢 𑁉 Slowmode setzen")
    @app_commands.describe(seconds="Sekunden (0-21600)")
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if not self._need_guild(interaction):
            return
        if not self._has_action_access(interaction.user, "slowmode"):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.manage_channels:
            return await _ephemeral(interaction, "Dir fehlt `Manage Channels`.")
        if not isinstance(interaction.channel, discord.TextChannel):
            return await _ephemeral(interaction, "Nur in Text-Channels.")
        s = max(0, min(21600, int(seconds)))
        try:
            await interaction.channel.edit(slowmode_delay=s)
        except Exception as e:
            return await _ephemeral(interaction, f"Slowmode ging nicht: {type(e).__name__}: {e}")
        await _ephemeral(interaction, f"Slowmode gesetzt: **{s}s**.")

    @app_commands.command(name="lock", description="🔒 𑁉 Channel sperren")
    @app_commands.describe(mode="all | send | view")
    @app_commands.choices(mode=[
        app_commands.Choice(name="all", value="all"),
        app_commands.Choice(name="send", value="send"),
        app_commands.Choice(name="view", value="view"),
    ])
    async def lock(self, interaction: discord.Interaction, mode: app_commands.Choice[str] | None = None):
        if not self._need_guild(interaction):
            return
        if not self._has_action_access(interaction.user, "lock"):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.manage_channels:
            return await _ephemeral(interaction, "Dir fehlt `Manage Channels`.")
        if not isinstance(interaction.channel, discord.TextChannel):
            return await _ephemeral(interaction, "Nur in Text-Channels.")
        m = self._parse_lock_mode(mode.value if mode else "all")
        ok, err = await self._apply_channel_lock(interaction.guild, interaction.user, interaction.channel, m, True)
        if not ok:
            return await _ephemeral(interaction, f"Lock ging nicht: {err}")
        await _ephemeral(interaction, f"Channel gesperrt. Modus: **{m}**")

    @app_commands.command(name="unlock", description="🔓 𑁉 Channel entsperren")
    @app_commands.describe(mode="all | send | view")
    @app_commands.choices(mode=[
        app_commands.Choice(name="all", value="all"),
        app_commands.Choice(name="send", value="send"),
        app_commands.Choice(name="view", value="view"),
    ])
    async def unlock(self, interaction: discord.Interaction, mode: app_commands.Choice[str] | None = None):
        if not self._need_guild(interaction):
            return
        if not self._has_action_access(interaction.user, "unlock"):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.manage_channels:
            return await _ephemeral(interaction, "Dir fehlt `Manage Channels`.")
        if not isinstance(interaction.channel, discord.TextChannel):
            return await _ephemeral(interaction, "Nur in Text-Channels.")
        m = self._parse_lock_mode(mode.value if mode else "all")
        ok, err = await self._apply_channel_lock(interaction.guild, interaction.user, interaction.channel, m, False)
        if not ok:
            return await _ephemeral(interaction, f"Unlock ging nicht: {err}")
        await _ephemeral(interaction, f"Channel entsperrt. Modus: **{m}**")

    @app_commands.command(name="nick", description="🪪 𑁉 Nickname setzen")
    @app_commands.describe(user="User", nickname="Neuer Nickname")
    async def nick(self, interaction: discord.Interaction, user: discord.Member, nickname: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.manage_nicknames:
            return await _ephemeral(interaction, "Dir fehlt `Manage Nicknames`.")
        try:
            await user.edit(nick=nickname or None)
        except Exception as e:
            return await _ephemeral(interaction, f"Nick ging nicht: {type(e).__name__}: {e}")
        await _ephemeral(interaction, f"Nickname gesetzt für {user.mention}.")

    @app_commands.command(name="role-add", description="➕ 𑁉 Rolle hinzufügen")
    @app_commands.describe(user="User", role="Rolle")
    async def role_add(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.manage_roles:
            return await _ephemeral(interaction, "Dir fehlt `Manage Roles`.")
        try:
            await user.add_roles(role)
        except Exception as e:
            return await _ephemeral(interaction, f"Rolle hinzufügen ging nicht: {type(e).__name__}: {e}")
        await _ephemeral(interaction, f"{role.mention} zu {user.mention} hinzugefügt.")

    @app_commands.command(name="role-remove", description="➖ 𑁉 Rolle entfernen")
    @app_commands.describe(user="User", role="Rolle")
    async def role_remove(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.manage_roles:
            return await _ephemeral(interaction, "Dir fehlt `Manage Roles`.")
        try:
            await user.remove_roles(role)
        except Exception as e:
            return await _ephemeral(interaction, f"Rolle entfernen ging nicht: {type(e).__name__}: {e}")
        await _ephemeral(interaction, f"{role.mention} von {user.mention} entfernt.")

    @app_commands.command(name="softban", description="🧼 𑁉 Softban (ban + unban)")
    @app_commands.describe(user="User", delete_days="Lösche Nachrichten der letzten X Tage (0-7)", reason="Grund")
    async def softban(self, interaction: discord.Interaction, user: discord.User, delete_days: int = 1, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.ban_members:
            return await _ephemeral(interaction, "Dir fehlt `Ban Members`.")
        ok, err, case_id = await self.service.softban(interaction.guild, interaction.user, user, delete_days, reason)
        if not ok:
            return await _ephemeral(interaction, f"Softban ging nicht: {err}")
        await _ephemeral(interaction, f"<@{user.id}> softbanned. Case: `{case_id}`")

    @app_commands.command(name="mass-timeout", description="⏳ 𑁉 Timeout für Rolle")
    @app_commands.describe(role="Zielrolle", minutes="Minuten", reason="Grund")
    async def mass_timeout(self, interaction: discord.Interaction, role: discord.Role, minutes: int, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.moderate_members:
            return await _ephemeral(interaction, "Dir fehlt `Moderate Members`.")
        await _defer(interaction)
        ok_count = 0
        fail_count = 0
        for member in role.members:
            ok, err, used, strikes, case_id = await self.service.timeout(interaction.guild, interaction.user, member, minutes, reason)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
        await _ephemeral(interaction, f"Mass-Timeout fertig. OK: **{ok_count}**, Fehler: **{fail_count}**.")

    @app_commands.command(name="warns", description="📂 𑁉 Warn-History anzeigen")
    @app_commands.describe(user="User", limit="Wie viele (max 20)")
    async def warns(self, interaction: discord.Interaction, user: discord.Member, limit: int = 10):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        n = max(1, min(20, int(limit)))
        rows = await self.bot.db.list_infractions(interaction.guild.id, user.id, limit=n)
        if not rows:
            return await _ephemeral(interaction, "Keine Einträge.")
        lines = []
        for r in rows:
            cid, action, dur, reason, created_at, mod_id = r
            if str(action) not in {"warn", "timeout"}:
                continue
            lines.append(f"• Case `{cid}` • {action} • {reason or '—'}")
        text = "\n".join(lines) if lines else "Keine Warns/Timeouts."
        await _ephemeral(interaction, text)

    @app_commands.command(name="case", description="📁 𑁉 Case anzeigen")
    @app_commands.describe(case_id="Case-ID")
    async def case(self, interaction: discord.Interaction, case_id: int):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        row = await self.bot.db.get_infraction(interaction.guild.id, int(case_id))
        if not row:
            return await _ephemeral(interaction, "Case nicht gefunden.")
        cid, action, dur, reason, created_at, mod_id, user_id = row
        text = (
            f"┏`🆔` - Case: `{cid}`\n"
            f"┣`👤` - User: <@{user_id}>\n"
            f"┣`🧑‍⚖️` - Moderator: <@{mod_id}>\n"
            f"┣`⚙️` - Action: **{action}**\n"
            f"┣`⏳` - Dauer: **{dur or 0}**\n"
            f"┗`📝` - Grund: {reason or '—'}"
        )
        await _ephemeral(interaction, text)

    @app_commands.command(name="note", description="📝 𑁉 Mod-Notiz hinzufügen")
    @app_commands.describe(user="User", note="Notiz")
    async def note(self, interaction: discord.Interaction, user: discord.Member, note: str):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        case_id = await self.service.add_note(interaction.guild, interaction.user, user, note)
        await _ephemeral(interaction, f"Notiz gespeichert. Case: `{case_id}`")

    @app_commands.command(name="notes", description="🗒️ 𑁉 Mod-Notizen anzeigen")
    @app_commands.describe(user="User", limit="Wie viele (max 20)")
    async def notes(self, interaction: discord.Interaction, user: discord.Member, limit: int = 10):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        n = max(1, min(20, int(limit)))
        rows = await self.bot.db.list_infractions(interaction.guild.id, user.id, limit=n)
        lines = []
        for r in rows:
            cid, action, dur, reason, created_at, mod_id = r
            if str(action) != "note":
                continue
            lines.append(f"• Case `{cid}` • {reason or '—'}")
        text = "\n".join(lines) if lines else "Keine Notizen."
        await _ephemeral(interaction, text)

    @app_commands.command(name="unwarn", description="🧹 𑁉 Letzte Warns/Timeouts entfernen")
    @app_commands.describe(user="User", amount="Anzahl (1-20)")
    async def unwarn(self, interaction: discord.Interaction, user: discord.Member, amount: int = 1):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        n = max(1, min(20, int(amount)))
        removed = await self.service.unwarn(interaction.guild, interaction.user, user, n)
        await _ephemeral(interaction, f"Entfernt: **{removed}** Warn/Timeout-Einträge.")

    @app_commands.command(name="case-reason", description="🛠️ 𑁉 Case-Grund ändern")
    @app_commands.describe(case_id="Case-ID", reason="Neuer Grund")
    async def case_reason(self, interaction: discord.Interaction, case_id: int, reason: str):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        ok, err = await self.service.update_case_reason(interaction.guild, interaction.user, int(case_id), str(reason))
        if not ok:
            return await _ephemeral(interaction, "Case nicht gefunden oder Update fehlgeschlagen.")
        await _ephemeral(interaction, f"Case `{int(case_id)}` aktualisiert.")

    @app_commands.command(name="clearnotes", description="🧽 𑁉 Mod-Notizen löschen")
    @app_commands.describe(user="User", amount="Anzahl (1-50)")
    async def clear_notes(self, interaction: discord.Interaction, user: discord.Member, amount: int = 10):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        n = max(1, min(50, int(amount)))
        removed = await self.service.clear_notes(interaction.guild, interaction.user, user, n)
        await _ephemeral(interaction, f"Entfernt: **{removed}** Notiz(en).")

    @commands.command(name="timeout")
    async def p_timeout(self, ctx: commands.Context, user: discord.Member, minutes: int | None = None, *, reason: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.moderate_members:
            return await self._ctx_reply(ctx, "Dir fehlt `Moderate Members`.")
        ok, err, used_minutes, strikes, case_id = await self.service.timeout(ctx.guild, ctx.author, user, minutes, reason)
        if not ok:
            return await self._ctx_reply(ctx, f"Timeout ging nicht: {err}")
        await self._ctx_reply(ctx, f"Timeout gesetzt: **{used_minutes}min** (Strike **{strikes}**). Case: `{case_id}`")

    @commands.command(name="warn")
    async def p_warn(self, ctx: commands.Context, user: discord.Member, *, reason: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.moderate_members:
            return await self._ctx_reply(ctx, "Dir fehlt `Moderate Members`.")
        strikes, case_id = await self.service.warn(ctx.guild, ctx.author, user, reason)
        await self._ctx_reply(ctx, f"Warnung vergeben. Strikes jetzt: **{strikes}**. Case: `{case_id}`")

    @commands.command(name="kick")
    async def p_kick(self, ctx: commands.Context, user: discord.Member, *, reason: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.kick_members:
            return await self._ctx_reply(ctx, "Dir fehlt `Kick Members`.")
        ok, err, case_id = await self.service.kick(ctx.guild, ctx.author, user, reason)
        if not ok:
            return await self._ctx_reply(ctx, f"Kick ging nicht: {err}")
        await self._ctx_reply(ctx, f"{user.mention} wurde gekickt. Case: `{case_id}`")

    @commands.command(name="ban")
    async def p_ban(self, ctx: commands.Context, user: discord.User, delete_days: int = 0, *, reason: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.ban_members:
            return await self._ctx_reply(ctx, "Dir fehlt `Ban Members`.")
        ok, err, dd, case_id = await self.service.ban(ctx.guild, ctx.author, user, delete_days, reason)
        if not ok:
            return await self._ctx_reply(ctx, f"Ban ging nicht: {err}")
        await self._ctx_reply(ctx, f"<@{user.id}> wurde gebannt. (delete_days={dd}) Case: `{case_id}`")

    @commands.command(name="purge", aliases=["clear", "prune"])
    async def p_purge(self, ctx: commands.Context, amount: int, user: discord.Member | None = None):
        if not self._need_ctx(ctx):
            return
        if not self._has_action_access(ctx.author, "purge"):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.manage_messages:
            return await self._ctx_reply(ctx, "Dir fehlt `Manage Messages`.")
        if not isinstance(ctx.channel, discord.TextChannel):
            return await self._ctx_reply(ctx, "Nur in normalen Text-Channels.")
        deleted, err, case_id = await self.service.purge(ctx.guild, ctx.author, ctx.channel, amount, user)
        if err:
            return await self._ctx_reply(ctx, f"Purge ging nicht: {err}")
        await self._ctx_reply(ctx, f"Gelöscht: **{deleted}** Nachricht(en). Case: `{case_id}`")

    @commands.command(name="untimeout")
    async def p_untimeout(self, ctx: commands.Context, user: discord.Member, *, reason: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.moderate_members:
            return await self._ctx_reply(ctx, "Dir fehlt `Moderate Members`.")
        try:
            await user.timeout(None, reason=reason or None)
        except Exception as e:
            return await self._ctx_reply(ctx, f"Timeout entfernen ging nicht: {type(e).__name__}: {e}")
        await self._ctx_reply(ctx, f"Timeout entfernt für {user.mention}.")

    @commands.command(name="unban")
    async def p_unban(self, ctx: commands.Context, user_id: int, *, reason: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.ban_members:
            return await self._ctx_reply(ctx, "Dir fehlt `Ban Members`.")
        try:
            await ctx.guild.unban(discord.Object(id=int(user_id)), reason=reason or None)
        except Exception as e:
            return await self._ctx_reply(ctx, f"Unban ging nicht: {type(e).__name__}: {e}")
        await self._ctx_reply(ctx, f"<@{user_id}> wurde entbannt.")

    @commands.command(name="slowmode")
    async def p_slowmode(self, ctx: commands.Context, seconds: int):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.manage_channels:
            return await self._ctx_reply(ctx, "Dir fehlt `Manage Channels`.")
        if not isinstance(ctx.channel, discord.TextChannel):
            return await self._ctx_reply(ctx, "Nur in Text-Channels.")
        s = max(0, min(21600, int(seconds)))
        try:
            await ctx.channel.edit(slowmode_delay=s)
        except Exception as e:
            return await self._ctx_reply(ctx, f"Slowmode ging nicht: {type(e).__name__}: {e}")
        await self._ctx_reply(ctx, f"Slowmode gesetzt: **{s}s**.")

    @commands.command(name="lock", aliases=["lockall"])
    async def p_lock(self, ctx: commands.Context, mode: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not self._has_action_access(ctx.author, "lock"):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.manage_channels:
            return await self._ctx_reply(ctx, "Dir fehlt `Manage Channels`.")
        if not isinstance(ctx.channel, discord.TextChannel):
            return await self._ctx_reply(ctx, "Nur in Text-Channels.")
        m = self._parse_lock_mode(mode or "all")
        ok, err = await self._apply_channel_lock(ctx.guild, ctx.author, ctx.channel, m, True)
        if not ok:
            return await self._ctx_reply(ctx, f"Lock ging nicht: {err}")
        await self._ctx_reply(ctx, f"Channel gesperrt. Modus: **{m}**")

    @commands.command(name="unlock", aliases=["unlockall"])
    async def p_unlock(self, ctx: commands.Context, mode: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not self._has_action_access(ctx.author, "unlock"):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.manage_channels:
            return await self._ctx_reply(ctx, "Dir fehlt `Manage Channels`.")
        if not isinstance(ctx.channel, discord.TextChannel):
            return await self._ctx_reply(ctx, "Nur in Text-Channels.")
        m = self._parse_lock_mode(mode or "all")
        ok, err = await self._apply_channel_lock(ctx.guild, ctx.author, ctx.channel, m, False)
        if not ok:
            return await self._ctx_reply(ctx, f"Unlock ging nicht: {err}")
        await self._ctx_reply(ctx, f"Channel entsperrt. Modus: **{m}**")

    @commands.command(name="lockw", aliases=["locksend", "lockwrite"])
    async def p_lock_w(self, ctx: commands.Context):
        await self.p_lock(ctx, mode="send")

    @commands.command(name="unlockw", aliases=["unlocksend", "unlockwrite"])
    async def p_unlock_w(self, ctx: commands.Context):
        await self.p_unlock(ctx, mode="send")

    @commands.command(name="locks", aliases=["lockview", "locksee"])
    async def p_lock_s(self, ctx: commands.Context):
        await self.p_lock(ctx, mode="view")

    @commands.command(name="unlocks", aliases=["unlockview", "unlocksee"])
    async def p_unlock_s(self, ctx: commands.Context):
        await self.p_unlock(ctx, mode="view")

    @commands.command(name="nick")
    async def p_nick(self, ctx: commands.Context, user: discord.Member, *, nickname: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.manage_nicknames:
            return await self._ctx_reply(ctx, "Dir fehlt `Manage Nicknames`.")
        try:
            await user.edit(nick=nickname or None)
        except Exception as e:
            return await self._ctx_reply(ctx, f"Nick ging nicht: {type(e).__name__}: {e}")
        await self._ctx_reply(ctx, f"Nickname gesetzt für {user.mention}.")

    @commands.command(name="roleadd")
    async def p_role_add(self, ctx: commands.Context, user: discord.Member, role: discord.Role):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.manage_roles:
            return await self._ctx_reply(ctx, "Dir fehlt `Manage Roles`.")
        try:
            await user.add_roles(role)
        except Exception as e:
            return await self._ctx_reply(ctx, f"Rolle hinzufügen ging nicht: {type(e).__name__}: {e}")
        await self._ctx_reply(ctx, f"{role.mention} zu {user.mention} hinzugefügt.")

    @commands.command(name="roleremove")
    async def p_role_remove(self, ctx: commands.Context, user: discord.Member, role: discord.Role):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.manage_roles:
            return await self._ctx_reply(ctx, "Dir fehlt `Manage Roles`.")
        try:
            await user.remove_roles(role)
        except Exception as e:
            return await self._ctx_reply(ctx, f"Rolle entfernen ging nicht: {type(e).__name__}: {e}")
        await self._ctx_reply(ctx, f"{role.mention} von {user.mention} entfernt.")

    @commands.command(name="softban")
    async def p_softban(self, ctx: commands.Context, user: discord.User, delete_days: int = 1, *, reason: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.ban_members:
            return await self._ctx_reply(ctx, "Dir fehlt `Ban Members`.")
        ok, err, case_id = await self.service.softban(ctx.guild, ctx.author, user, delete_days, reason)
        if not ok:
            return await self._ctx_reply(ctx, f"Softban ging nicht: {err}")
        await self._ctx_reply(ctx, f"<@{user.id}> softbanned. Case: `{case_id}`")

    @commands.command(name="masstimeout")
    async def p_mass_timeout(self, ctx: commands.Context, role: discord.Role, minutes: int, *, reason: str | None = None):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        if not ctx.author.guild_permissions.moderate_members:
            return await self._ctx_reply(ctx, "Dir fehlt `Moderate Members`.")
        ok_count = 0
        fail_count = 0
        for member in role.members:
            ok, err, used, strikes, case_id = await self.service.timeout(ctx.guild, ctx.author, member, minutes, reason)
            if ok:
                ok_count += 1
            else:
                fail_count += 1
        await self._ctx_reply(ctx, f"Mass-Timeout fertig. OK: **{ok_count}**, Fehler: **{fail_count}**.")

    @commands.command(name="warns")
    async def p_warns(self, ctx: commands.Context, user: discord.Member, limit: int = 10):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        n = max(1, min(20, int(limit)))
        rows = await self.bot.db.list_infractions(ctx.guild.id, user.id, limit=n)
        if not rows:
            return await self._ctx_reply(ctx, "Keine Einträge.")
        lines = []
        for r in rows:
            cid, action, dur, reason, created_at, mod_id = r
            if str(action) not in {"warn", "timeout"}:
                continue
            lines.append(f"• Case `{cid}` • {action} • {reason or '—'}")
        await self._ctx_reply(ctx, "\n".join(lines) if lines else "Keine Warns/Timeouts.")

    @commands.command(name="case")
    async def p_case(self, ctx: commands.Context, case_id: int):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        row = await self.bot.db.get_infraction(ctx.guild.id, int(case_id))
        if not row:
            return await self._ctx_reply(ctx, "Case nicht gefunden.")
        cid, action, dur, reason, created_at, mod_id, user_id = row
        text = (
            f"┏`🆔` - Case: `{cid}`\n"
            f"┣`👤` - User: <@{user_id}>\n"
            f"┣`🧑‍⚖️` - Moderator: <@{mod_id}>\n"
            f"┣`⚙️` - Action: **{action}**\n"
            f"┣`⏳` - Dauer: **{dur or 0}**\n"
            f"┗`📝` - Grund: {reason or '—'}"
        )
        await self._ctx_reply(ctx, text)

    @commands.command(name="note")
    async def p_note(self, ctx: commands.Context, user: discord.Member, *, note: str):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        case_id = await self.service.add_note(ctx.guild, ctx.author, user, note)
        await self._ctx_reply(ctx, f"Notiz gespeichert. Case: `{case_id}`")

    @commands.command(name="notes")
    async def p_notes(self, ctx: commands.Context, user: discord.Member, limit: int = 10):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        n = max(1, min(20, int(limit)))
        rows = await self.bot.db.list_infractions(ctx.guild.id, user.id, limit=n)
        lines = []
        for r in rows:
            cid, action, dur, reason, created_at, mod_id = r
            if str(action) != "note":
                continue
            lines.append(f"• Case `{cid}` • {reason or '—'}")
        await self._ctx_reply(ctx, "\n".join(lines) if lines else "Keine Notizen.")

    @commands.command(name="unwarn")
    async def p_unwarn(self, ctx: commands.Context, user: discord.Member, amount: int = 1):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        n = max(1, min(20, int(amount)))
        removed = await self.service.unwarn(ctx.guild, ctx.author, user, n)
        await self._ctx_reply(ctx, f"Entfernt: **{removed}** Warn/Timeout-Einträge.")

    @commands.command(name="casereason")
    async def p_case_reason(self, ctx: commands.Context, case_id: int, *, reason: str):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        ok, err = await self.service.update_case_reason(ctx.guild, ctx.author, int(case_id), str(reason))
        if not ok:
            return await self._ctx_reply(ctx, "Case nicht gefunden oder Update fehlgeschlagen.")
        await self._ctx_reply(ctx, f"Case `{int(case_id)}` aktualisiert.")

    @commands.command(name="clearnotes")
    async def p_clear_notes(self, ctx: commands.Context, user: discord.Member, amount: int = 10):
        if not self._need_ctx(ctx):
            return
        if not is_staff(self.bot.settings, ctx.author):
            return await self._ctx_reply(ctx, "Keine Rechte.")
        n = max(1, min(50, int(amount)))
        removed = await self.service.clear_notes(ctx.guild, ctx.author, user, n)
        await self._ctx_reply(ctx, f"Entfernt: **{removed}** Notiz(en).")
