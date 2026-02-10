from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import discord

from bot.core.perms import is_staff
from bot.modules.wort_zum_sonntag.formatting.wort_views import build_submission_view
from bot.modules.wort_zum_sonntag.views.info import WortInfoView
from bot.modules.wort_zum_sonntag.views.panel import WortPanelView


@dataclass
class SubmissionData:
    submission_id: int
    user_id: int
    message_id: int
    content: str
    status: str
    created_at: str
    decided_by: int | None
    decided_at: str | None
    posted_at: str | None
    posted_channel_id: int | None
    posted_message_id: int | None
    thread_id: int


class WortSubmitModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title="📖 Wort zum Sonntag einreichen")
        self.service = service
        self.text = discord.ui.TextInput(
            label="Deine Weisheit",
            style=discord.TextStyle.paragraph,
            max_length=800,
            required=True,
            placeholder="Schreib hier deine Weisheit...",
        )
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.submit_wisdom(interaction, str(self.text.value))


class WortZumSonntagService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _gi(self, guild_id: int, key: str, default: int = 0) -> int:
        return int(self.settings.get_guild_int(guild_id, key, default))

    def _g(self, guild_id: int, key: str, default=None):
        return self.settings.get_guild(guild_id, key, default)

    def _review_role_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "wzs.review_role_id", 0)

    def _forum_channel_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "wzs.forum_channel_id", 0)

    def _ping_role_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "wzs.ping_role_id", 0)

    def _panel_thread_name(self, guild_id: int) -> str:
        return str(self._g(guild_id, "wzs.panel_thread_name", "📖 Wort zum Sonntag – Einreichen") or "📖 Wort zum Sonntag – Einreichen")

    def _info_thread_name(self, guild_id: int) -> str:
        return str(self._g(guild_id, "wzs.info_thread_name", "ℹ️ Wort zum Sonntag – Info") or "ℹ️ Wort zum Sonntag – Info")

    def _submission_thread_name(self, user: discord.abc.User) -> str:
        base = str(getattr(user, "display_name", None) or user.name or "User")
        base = base.replace("#", "").strip()
        if not base:
            base = "User"
        return f"💡 Weisheit · {base}"[:100]

    def _status_tag_name(self, status: str) -> str:
        s = str(status or "pending").lower()
        if s == "accepted":
            return "✅ ANGENOMMEN"
        if s == "posted":
            return "📣 GEPOSTET"
        if s == "rejected":
            return "⛔ ABGELEHNT"
        return "⏳ ERWARTET"

    def _status_tag_names(self) -> set[str]:
        legacy = {"erwartet", "angenommen", "abgelehnt", "gepostet"}
        current = {
            self._status_tag_name("pending"),
            self._status_tag_name("accepted"),
            self._status_tag_name("rejected"),
            self._status_tag_name("posted"),
        }
        return {name.lower() for name in (legacy | current)}

    async def _ensure_status_tag(self, forum: discord.ForumChannel, status: str) -> discord.ForumTag | None:
        name = self._status_tag_name(status)
        for tag in forum.available_tags:
            if str(tag.name).lower() == name.lower():
                return tag
        try:
            return await forum.create_tag(name=name)
        except Exception:
            return None

    async def _apply_status_tag(self, thread: discord.Thread, status: str):
        parent = getattr(thread, "parent", None)
        if not isinstance(parent, discord.ForumChannel):
            return
        tag = await self._ensure_status_tag(parent, status)
        if not tag:
            return
        keep = []
        status_names = self._status_tag_names()
        for t in list(getattr(thread, "applied_tags", []) or []):
            if str(t.name).lower() not in status_names:
                keep.append(t)
        if all(int(getattr(t, "id", 0)) != int(tag.id) for t in keep):
            keep.append(tag)
        try:
            await thread.edit(applied_tags=keep)
        except Exception:
            pass

    def _can_review(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True
        role_id = self._review_role_id(member.guild.id)
        if role_id:
            return any(r.id == role_id for r in member.roles)
        return is_staff(self.settings, member)

    async def open_submit_modal(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        await interaction.response.send_modal(WortSubmitModal(self))

    async def configure(
        self,
        guild: discord.Guild,
        forum_channel: discord.ForumChannel,
        review_role: discord.Role | None,
        ping_role: discord.Role | None,
    ):
        await self.settings.set_guild_override(self.db, guild.id, "wzs.forum_channel_id", int(forum_channel.id))
        if review_role:
            await self.settings.set_guild_override(self.db, guild.id, "wzs.review_role_id", int(review_role.id))
        if ping_role:
            await self.settings.set_guild_override(self.db, guild.id, "wzs.ping_role_id", int(ping_role.id))

    async def send_panel(self, interaction: discord.Interaction, forum: discord.ForumChannel | None = None):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        guild = interaction.guild

        forum_channel = forum or await self._get_forum_channel(guild)
        if not forum_channel:
            return await interaction.response.send_message("Forum-Channel ist nicht konfiguriert.", ephemeral=True)

        if forum:
            await self.settings.set_guild_override(self.db, guild.id, "wzs.forum_channel_id", int(forum.id))
        await interaction.response.defer(ephemeral=True)
        await self._ensure_main_thread(guild, forum_channel)
        await self._refresh_all_submissions(guild)
        try:
            await interaction.edit_original_response(content="Info + Panel aktualisiert.")
        except Exception:
            await interaction.followup.send("Info + Panel aktualisiert.", ephemeral=True)

    async def submit_wisdom(self, interaction: discord.Interaction, content: str):
        if not interaction.guild or not interaction.user:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        guild = interaction.guild
        forum_channel = await self._get_forum_channel(guild)
        if not forum_channel:
            return await interaction.response.send_message("Forum-Channel ist nicht konfiguriert.", ephemeral=True)

        text = str(content or "").strip()
        if len(text) < 10:
            return await interaction.response.send_message("Bitte etwas ausführlicher schreiben (min. 10 Zeichen).", ephemeral=True)

        data = {
            "user_id": int(interaction.user.id),
            "content": text,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        view = build_submission_view(self.settings, guild, data)

        pending_tag = await self._ensure_status_tag(forum_channel, "pending")
        thread_kwargs = {
            "name": self._submission_thread_name(interaction.user),
            "view": view,
        }
        if pending_tag:
            thread_kwargs["applied_tags"] = [pending_tag]
        res = await forum_channel.create_thread(**thread_kwargs)

        submission_id = await self.db.create_wzs_submission(
            guild.id,
            int(interaction.user.id),
            int(res.thread.id),
            int(res.message.id),
            text,
        )

        try:
            await res.thread.edit(name=f"💡 Weisheit #{submission_id} · {interaction.user.display_name}"[:100])
        except Exception:
            pass

        await interaction.response.send_message("Danke! Deine Weisheit wurde eingereicht.", ephemeral=True)

    async def set_status(self, interaction: discord.Interaction, status: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not isinstance(interaction.channel, discord.Thread):
            return await interaction.response.send_message("Nur im Weisheits-Thread nutzbar.", ephemeral=True)
        if not self._can_review(interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)

        row = await self.db.get_wzs_submission_by_thread(interaction.guild.id, interaction.channel.id)
        if not row:
            return await interaction.response.send_message("Weisheit nicht gefunden.", ephemeral=True)

        submission_id = int(row[0])
        current_status = str(row[4] or "pending")
        if current_status == status:
            return await interaction.response.send_message("Status ist bereits gesetzt.", ephemeral=True)

        await self.db.set_wzs_status(submission_id, status, interaction.user.id)
        await self._refresh_submission_message(interaction.guild, submission_id)
        await interaction.response.send_message("Status gespeichert.", ephemeral=True)

    async def _get_forum_channel(self, guild: discord.Guild) -> discord.ForumChannel | None:
        channel_id = self._forum_channel_id(guild.id)
        if not channel_id:
            return None
        ch = guild.get_channel(int(channel_id))
        if not ch:
            try:
                ch = await guild.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        return ch if isinstance(ch, discord.ForumChannel) else None

    async def toggle_ping_role(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        role_id = self._ping_role_id(interaction.guild.id)
        if not role_id:
            return await interaction.response.send_message("Ping-Rolle ist nicht konfiguriert.", ephemeral=True)
        role = interaction.guild.get_role(int(role_id))
        if not role:
            return await interaction.response.send_message("Ping-Rolle nicht gefunden.", ephemeral=True)
        member = interaction.user
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="WZS ping role toggle")
            except Exception:
                return await interaction.response.send_message("Konnte Rolle nicht entfernen.", ephemeral=True)
            return await interaction.response.send_message("Ping-Rolle entfernt.", ephemeral=True)
        try:
            await member.add_roles(role, reason="WZS ping role toggle")
        except Exception:
            return await interaction.response.send_message("Konnte Rolle nicht vergeben.", ephemeral=True)
        return await interaction.response.send_message("Ping-Rolle erhalten.", ephemeral=True)

    async def _get_thread(self, guild: discord.Guild, thread_id: int) -> discord.Thread | None:
        thread = guild.get_thread(int(thread_id))
        if thread:
            return thread
        try:
            ch = await guild.fetch_channel(int(thread_id))
        except Exception:
            ch = None
        return ch if isinstance(ch, discord.Thread) else None

    async def _ensure_main_thread(self, guild: discord.Guild, forum: discord.ForumChannel):
        panel_thread_id = self._gi(guild.id, "wzs.panel_thread_id", 0)
        info_thread_id = self._gi(guild.id, "wzs.info_thread_id", 0)
        thread_id = panel_thread_id or info_thread_id
        thread = await self._get_thread(guild, thread_id) if thread_id else None

        if not thread:
            info_view = WortInfoView(self, guild)
            res = await forum.create_thread(name=self._panel_thread_name(guild.id), view=info_view)
            thread = res.thread
            await self.settings.set_guild_override(self.db, guild.id, "wzs.panel_thread_id", int(thread.id))
            await self.settings.set_guild_override(self.db, guild.id, "wzs.info_thread_id", int(thread.id))
            await self.settings.set_guild_override(self.db, guild.id, "wzs.info_message_id", int(res.message.id))

            panel_view = WortPanelView(self, guild)
            panel_msg = await thread.send(view=panel_view)
            await self.settings.set_guild_override(self.db, guild.id, "wzs.panel_message_id", int(panel_msg.id))
            return

        desired_name = self._panel_thread_name(guild.id)
        if desired_name and str(getattr(thread, "name", "")) != str(desired_name):
            try:
                await thread.edit(name=desired_name)
            except Exception:
                pass

        await self.settings.set_guild_override(self.db, guild.id, "wzs.panel_thread_id", int(thread.id))
        await self.settings.set_guild_override(self.db, guild.id, "wzs.info_thread_id", int(thread.id))

        info_message_id = self._gi(guild.id, "wzs.info_message_id", 0)
        info_view = WortInfoView(self, guild)
        if info_message_id:
            try:
                msg = await thread.fetch_message(int(info_message_id))
                await msg.edit(view=info_view)
            except Exception:
                info_message_id = 0
        if not info_message_id:
            msg = await thread.send(view=info_view)
            await self.settings.set_guild_override(self.db, guild.id, "wzs.info_message_id", int(msg.id))

        panel_message_id = self._gi(guild.id, "wzs.panel_message_id", 0)
        panel_view = WortPanelView(self, guild)
        if panel_message_id:
            try:
                msg = await thread.fetch_message(int(panel_message_id))
                await msg.edit(view=panel_view)
            except Exception:
                panel_message_id = 0
        if not panel_message_id:
            msg = await thread.send(view=panel_view)
            await self.settings.set_guild_override(self.db, guild.id, "wzs.panel_message_id", int(msg.id))

    async def _refresh_all_submissions(self, guild: discord.Guild, limit: int = 2000):
        try:
            rows = await self.db.list_wzs_submissions(guild.id, limit=limit)
        except Exception:
            return
        for row in rows:
            if not row:
                continue
            try:
                submission_id = int(row[0])
            except Exception:
                continue
            try:
                await self._refresh_submission_message(guild, submission_id)
            except Exception:
                pass

    async def _refresh_submission_message(self, guild: discord.Guild, submission_id: int):
        row = await self.db.get_wzs_submission(int(submission_id))
        if not row:
            return
        data = SubmissionData(
            submission_id=int(row[0]),
            user_id=int(row[2]),
            thread_id=int(row[3]),
            message_id=int(row[4]),
            content=str(row[5]),
            status=str(row[6]),
            created_at=str(row[7]),
            decided_by=int(row[8]) if row[8] else None,
            decided_at=str(row[9]) if row[9] else None,
            posted_at=str(row[10]) if row[10] else None,
            posted_channel_id=int(row[11]) if row[11] else None,
            posted_message_id=int(row[12]) if row[12] else None,
        )

        thread = await self._get_thread(guild, data.thread_id)
        if not thread:
            return
        try:
            msg = await thread.fetch_message(int(data.message_id))
        except Exception:
            return

        view = build_submission_view(self.settings, guild, {
            "user_id": data.user_id,
            "content": data.content,
            "status": data.status,
            "created_at": data.created_at,
            "decided_by": data.decided_by,
            "decided_at": data.decided_at,
            "posted_at": data.posted_at,
            "posted_channel_id": data.posted_channel_id,
        })
        try:
            await msg.edit(view=view)
        except Exception:
            pass
        await self._apply_status_tag(thread, data.status)
